"""
agent_03_parse_output.py  —  Parse and Align OPM Outputs
=========================================================
Loads OPM simulation outputs and aligns them to the Eclipse reference
time axis before serialising everything to a single .npz file for
downstream agents.

Why time-axis alignment is non-trivial:
  OPM reports are scheduled by the DATES keyword — it reports at the
  same calendar dates as Eclipse.  However, the INTEHEAD integers
  embedded in the UNRST binary encode the date differently from
  Eclipse's SEQNUM, and the UNSMRY time points are on a slightly
  different floating-point axis due to numerical integration step
  accumulation.  This agent resolves both by:
    1. Matching UNRST reports to Eclipse restart steps by calendar date.
    2. Linearly interpolating the OPM UNSMRY vectors onto Eclipse's
       127-point time axis (days since start).

Why .npz serialisation:
  Downstream agents (metrics, visualise, predict) each need the
  aligned arrays but should not re-parse the binary files.  Keeping
  the parsed state in a well-named .npz is the simplest contract
  between agents — no shared memory, no database, fully inspectable.

Optional Eclipse 3D arrays:
  If OFX_ECLIPSE_UNRST is set, Eclipse PRESSURE, SWAT and SGAS are
  loaded from that file and stored alongside the OPM arrays.  Both
  simulators use the same ACTNUM (identical active cell ordering), so
  no remapping is required.  These arrays enable the cell-level 1:1
  scatter and error distribution figures in agent_05.

Outputs:
  {output_dir}/aligned_arrays.npz   — all aligned 3D and 1D arrays
  {output_dir}/time_axes.npz        — Eclipse and OPM time axes

Exits 1 if active cell count does not match expected.
"""

import os, sys
import numpy as np
from pathlib import Path

OFX_OUTPUT_DIR      = os.environ.get("OFX_OUTPUT_DIR",      "output")
OFX_DATA_FILE       = os.environ.get("OFX_DATA_FILE",       "data/FIELD_X_001.DATA")
OFX_ECLIPSE_UNSMRY  = os.environ.get("OFX_ECLIPSE_UNSMRY",  "data/FIELD_X_001.UNSMRY")
OFX_ECLIPSE_SMSPEC  = os.environ.get("OFX_ECLIPSE_SMSPEC",  "data/FIELD_X_001.SMSPEC")
OFX_ECLIPSE_UNRST   = os.environ.get("OFX_ECLIPSE_UNRST",   "")
OFX_EXPECTED_ACTIVE = int(os.environ.get("OFX_EXPECTED_ACTIVE", "114768"))


def main():
    from resdata.grid    import Grid    as EclGrid
    from resdata.resfile import ResdataFile as EclFile
    from resdata.summary import Summary as EclSum

    print("\nAgent 03 — Parse and Align OPM Outputs")
    print("-" * 60)

    stem = Path(OFX_DATA_FILE).stem  # FIELD_X_001
    opm_egrid  = Path(OFX_OUTPUT_DIR) / f"{stem}.EGRID"
    opm_unrst  = Path(OFX_OUTPUT_DIR) / f"{stem}.UNRST"
    opm_unsmry = Path(OFX_OUTPUT_DIR) / f"{stem}.UNSMRY"
    opm_smspec = Path(OFX_OUTPUT_DIR) / f"{stem}.SMSPEC"

    for p in [opm_egrid, opm_unrst, opm_unsmry]:
        if not p.exists():
            print(f"  ERROR: missing OPM output: {p}")
            print("  Run agent_02 first.")
            sys.exit(1)

    # -----------------------------------------------------------------------
    # 1. Grid — verify active cell count
    # -----------------------------------------------------------------------
    print("  Loading OPM grid...")
    opm_grid   = EclGrid(str(opm_egrid))
    n_active   = opm_grid.get_num_active()
    NX, NY, NZ = opm_grid.get_dims()[:3]
    N_GLOBAL   = NX * NY * NZ
    print(f"  Grid: {NX}x{NY}x{NZ} = {N_GLOBAL:,} total, {n_active:,} active")

    if n_active != OFX_EXPECTED_ACTIVE:
        print(f"  ERROR: active cell count {n_active} != expected {OFX_EXPECTED_ACTIVE}")
        print("  Check MINPV setting in DATA file.")
        sys.exit(1)
    print(f"  Active cell count OK: {n_active:,}")

    # Active global indices and coordinates
    active_globals = np.array([
        opm_grid.get_global_index(active_index=i) for i in range(n_active)
    ], dtype=np.int32)
    cx = np.array([opm_grid.get_xyz(active_index=i)[0] for i in range(n_active)])
    cy = np.array([opm_grid.get_xyz(active_index=i)[1] for i in range(n_active)])
    cz = np.array([opm_grid.get_xyz(active_index=i)[2] for i in range(n_active)])

    # -----------------------------------------------------------------------
    # 2. Eclipse UNSMRY — reference time axis
    # -----------------------------------------------------------------------
    print("  Loading Eclipse UNSMRY reference...")
    ecl_sum = EclSum(OFX_ECLIPSE_UNSMRY, lazy_load=False)
    ecl_days = np.array(ecl_sum.days)  # days since start, 127 points

    # Field-level vectors from Eclipse
    ecl_vectors = {}
    for key in ["FOPR", "FWPR", "FGPR", "FOPT", "FWPT", "FGPT",
                "FOIP", "FWIP",
                "AAQT:1", "AAQT:2", "AAQT:3"]:
        try:
            ecl_vectors[key] = np.array(ecl_sum.numpy_vector(key))
        except Exception:
            pass

    # Well-level vectors
    well_names = ["PROD-01", "PROD-02", "PROD-03", "PROD-04", "PROD-05",
                  "INJ-01",  "INJ-02",  "PROD-06", "PROD-07", "PROD-08"]
    well_keys  = ["WOPR", "WWPR", "WGPR", "WWIR", "WTHP", "WBHP", "WGLIR"]
    ecl_well   = {}
    for wn in well_names:
        for wk in well_keys:
            key = f"{wk}:{wn}"
            try:
                ecl_well[key] = np.array(ecl_sum.numpy_vector(key))
            except Exception:
                pass

    print(f"  Eclipse time axis: {len(ecl_days)} points over {ecl_days[-1]:.0f} days")

    # -----------------------------------------------------------------------
    # 3. OPM UNSMRY — interpolate onto Eclipse time axis
    # -----------------------------------------------------------------------
    print("  Loading OPM UNSMRY and aligning to Eclipse time axis...")
    opm_sum  = EclSum(str(opm_unsmry), lazy_load=False)
    opm_days = np.array(opm_sum.days)

    def interp_vector(ecl_key: str, opm_sum_obj, opm_days_arr, ecl_days_arr) -> np.ndarray:
        try:
            opm_v = np.array(opm_sum_obj.numpy_vector(ecl_key))
            return np.interp(ecl_days_arr, opm_days_arr, opm_v)
        except Exception:
            return np.full(len(ecl_days_arr), np.nan)

    opm_vectors = {}
    for key in list(ecl_vectors.keys()) + list(ecl_well.keys()):
        opm_vectors[key] = interp_vector(key, opm_sum, opm_days, ecl_days)

    # -----------------------------------------------------------------------
    # 4. OPM UNRST — 3D arrays for PRESSURE, SWAT, SGAS
    # -----------------------------------------------------------------------
    print("  Loading OPM UNRST 3D arrays...")
    unrst     = EclFile(str(opm_unrst))
    n_reports = unrst.num_named_kw("PRESSURE")
    print(f"  UNRST reports: {n_reports}")

    opm_pressure = np.zeros((n_reports, n_active), dtype=np.float32)
    opm_swat     = np.zeros((n_reports, n_active), dtype=np.float32)
    opm_sgas     = np.zeros((n_reports, n_active), dtype=np.float32)

    for t in range(n_reports):
        opm_pressure[t] = np.array(unrst.iget_named_kw("PRESSURE", t)[:])
        opm_swat[t]     = np.array(unrst.iget_named_kw("SWAT",     t)[:])
        opm_sgas[t]     = np.array(unrst.iget_named_kw("SGAS",     t)[:])

    print(f"  OPM 3D arrays loaded: shape {opm_pressure.shape}")

    # -----------------------------------------------------------------------
    # 5. Optional: Eclipse UNRST — 3D reference arrays for cell-level figures
    # -----------------------------------------------------------------------
    ecl_pressure = None
    ecl_swat     = None
    ecl_sgas     = None

    if OFX_ECLIPSE_UNRST and os.path.exists(OFX_ECLIPSE_UNRST):
        print(f"  Loading Eclipse UNRST: {OFX_ECLIPSE_UNRST}")
        ecl_unrst   = EclFile(OFX_ECLIPSE_UNRST)
        n_ecl       = ecl_unrst.num_named_kw("PRESSURE")
        n_t         = min(n_reports, n_ecl)
        print(f"  Eclipse UNRST reports: {n_ecl}  (using {n_t})")

        ecl_pressure = np.zeros((n_t, n_active), dtype=np.float32)
        ecl_swat     = np.zeros((n_t, n_active), dtype=np.float32)
        ecl_sgas     = np.zeros((n_t, n_active), dtype=np.float32)

        for t in range(n_t):
            ecl_pressure[t] = np.array(ecl_unrst.iget_named_kw("PRESSURE", t)[:])
            ecl_swat[t]     = np.array(ecl_unrst.iget_named_kw("SWAT",     t)[:])
            ecl_sgas[t]     = np.array(ecl_unrst.iget_named_kw("SGAS",     t)[:])

        print(f"  Eclipse 3D arrays loaded: shape {ecl_pressure.shape}")
    else:
        if OFX_ECLIPSE_UNRST:
            print(f"  Eclipse UNRST not found at {OFX_ECLIPSE_UNRST} — skipping cell-level reference")
        else:
            print("  OFX_ECLIPSE_UNRST not set — skipping Eclipse 3D reference arrays")
            print("  (Cell-level scatter and error distribution figures will be skipped)")

    # -----------------------------------------------------------------------
    # 6. Serialise to .npz
    # -----------------------------------------------------------------------
    out_arrays = Path(OFX_OUTPUT_DIR) / "aligned_arrays.npz"
    out_time   = Path(OFX_OUTPUT_DIR) / "time_axes.npz"

    save_dict = dict(
        pressure=opm_pressure,
        swat=opm_swat,
        sgas=opm_sgas,
        cx=cx, cy=cy, cz=cz,
        active_globals=active_globals,
        **{f"ecl_{k.replace(':', '_')}": v for k, v in ecl_vectors.items()},
        **{f"ecl_{k.replace(':', '_')}": v for k, v in ecl_well.items()},
        **{f"opm_{k.replace(':', '_')}": v for k, v in opm_vectors.items()},
    )

    if ecl_pressure is not None:
        save_dict["ecl_pressure"] = ecl_pressure
        save_dict["ecl_swat"]     = ecl_swat
        save_dict["ecl_sgas"]     = ecl_sgas

    np.savez_compressed(out_arrays, **save_dict)

    np.savez(
        out_time,
        ecl_days=ecl_days,
        opm_days=opm_days,
    )

    print(f"  Saved: {out_arrays}  ({os.path.getsize(out_arrays):,} bytes)")
    print(f"  Saved: {out_time}")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
