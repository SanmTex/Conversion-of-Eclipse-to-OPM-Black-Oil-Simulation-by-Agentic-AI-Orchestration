"""
agent_07_predict.py  —  Extend Simulation +1 Year
===================================================
Takes the clean OPM deck from agent_06, extends the SCHEDULE section by
1 year beyond the validation end date, runs OPM Flow, and regenerates
the headline comparison figure with three clearly annotated time regions:

  1. Eclipse history     (solid line,  years 2000-2011)
  2. OPM validation match (dashed,    years 2000-2011)
  3. OPM +1yr prediction  (dotted + shaded band, 2011-2012)

Why this step is the natural conclusion:
  Validating that OPM matches Eclipse over the known history is
  necessary but not sufficient for practical use.  The real value of
  a validated open-source simulator is forward prediction — running
  the model beyond the historical period without paying for an Eclipse
  licence.  This agent demonstrates that capability with a minimal 1-
  year extension using the same well constraints.

  The prediction makes no claims about future reservoir management
  decisions.  Wells continue under their final WCONPROD constraints
  with no new wells, no workovers, no rate optimisation.  It is a
  pure extrapolation intended to show the simulator is capable of
  continued stable operation beyond the validated window.

Simulation end dates (anonymised, shifted -8 yr from real):
  Validation end : 1 JAN 2011
  Prediction end : 1 JAN 2012

Outputs:
  {output_dir}/FIELD_X_001_PREDICT.DATA         — extended DATA deck
  {output_dir}/predict/                          — OPM prediction outputs
  {output_dir}/figures/field_comparison_with_prediction.png

Exits 1 on OPM failure or missing prerequisites.
"""

import os, re, subprocess, sys, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OFX_OUTPUT_DIR = os.environ.get("OFX_OUTPUT_DIR", "output")
OFX_DATA_FILE  = os.environ.get("OFX_DATA_FILE",  "data/FIELD_X_001.DATA")
OMP_THREADS    = os.environ.get("OFX_OMP_THREADS", "4")

# Anonymised dates (real dates shifted -8yr)
PREDICT_END_YEAR  = 2012
PREDICT_END_MONTH = "JAN"
PREDICT_END_DAY   = 1
VALIDATION_END    = 2011   # year at which Eclipse reference ends


def win_to_wsl(win_path: str) -> str:
    from pathlib import Path
    p = Path(win_path).resolve()
    drive = p.drive.lower().rstrip(":")
    rest  = str(p.relative_to(p.anchor)).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def extend_schedule(text: str) -> str:
    """
    Append monthly DATES steps from FEB 2011 through JAN 2012 before END.
    Covers the 1-year prediction window beyond the validation end date.
    """
    months = ["JAN","FEB","MAR","APR","MAY","JUN",
              "JUL","AUG","SEP","OCT","NOV","DEC"]

    # If prediction end is already in the deck (uncommented), nothing to do
    if f"'{PREDICT_END_MONTH}' {PREDICT_END_YEAR}" in text:
        return text

    # Attempt to un-comment lines like "-- 1 'FEB' 2011  /"
    # Covers commented prediction dates in either 2011 or 2012
    text = re.sub(
        r"--\s+([0-9]+\s+'[A-Z]+'\s+201[12])\s*/",
        r" \1 /",
        text
    )

    # Fallback: insert a fresh DATES block before END
    if f"'{PREDICT_END_MONTH}' {PREDICT_END_YEAR}" not in text:
        new_dates = "\nDATES\n"
        # FEB 2011 → JAN 2012 (12 monthly steps)
        yr, mo_idx = VALIDATION_END, 1   # start: FEB 2011 (index 1)
        while True:
            mo = months[mo_idx]
            new_dates += f" 1 '{mo}' {yr}  /\n"
            if yr == PREDICT_END_YEAR and mo == PREDICT_END_MONTH:
                break
            mo_idx += 1
            if mo_idx == 12:
                mo_idx = 0
                yr += 1
        new_dates += "/\n"
        text = re.sub(r'\nEND\s*\n', new_dates + "\nEND\n", text)

    return text


def run_opm(data_path: Path, out_dir: Path) -> bool:
    out_dir.mkdir(parents=True, exist_ok=True)
    wsl_data   = win_to_wsl(str(data_path))
    wsl_outdir = win_to_wsl(str(out_dir))

    cmd = [
        "wsl",
        f"OMP_NUM_THREADS={OMP_THREADS}",
        "flow",
        f"--output-dir={wsl_outdir}",
        "--parsing-strictness=low",
        "--max-single-precision-days=0",
        wsl_data,
    ]
    print(f"  Running OPM prediction: {wsl_data}")
    print(f"  Output dir: {wsl_outdir}")
    t0 = time.time()
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    proc.wait()
    elapsed = time.time() - t0
    print(f"  OPM exit code: {proc.returncode}  ({elapsed:.1f}s)")
    return proc.returncode == 0


def make_prediction_figure(ecl_days, ecl_fopr, ecl_fwpr, ecl_fgpr,
                           opm_val_days, opm_val_fopr, opm_val_fwpr, opm_val_fgpr,
                           pred_days, pred_fopr, pred_fwpr, pred_fgpr,
                           ecl_fopt, ecl_fwpt, ecl_fgpt,
                           val_fopt, val_fwpt, val_fgpt,
                           pred_fopt, pred_fwpt, pred_fgpt,
                           out_path: Path):
    """
    Three-region comparison figure with secondary cumulative axis:
      - Eclipse history (solid blue)
      - OPM validation match (dashed red, same time range)
      - OPM +1yr prediction (dotted green + shaded band)
      - Cumulative volumes on right-hand secondary y-axis (lighter lines)
    """
    def to_year(days):
        # START = 1 JUL 2000 = year 2000.5; day 3836 (1 JAN 2011) → 2011.0
        return 2000.5 + np.asarray(days) / 365.25

    ecl_yr  = to_year(ecl_days)
    val_yr  = to_year(opm_val_days)
    pred_yr = to_year(pred_days)
    val_end_yr = to_year(float(ecl_days[-1]))

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    rate_rows = [
        (ecl_fopr, opm_val_fopr, pred_fopr,
         ecl_fopt, val_fopt,     pred_fopt,
         "Oil Rate (STB/d)",   "Cum. Oil (MSTB)",   axes[0]),
        (ecl_fwpr, opm_val_fwpr, pred_fwpr,
         ecl_fwpt, val_fwpt,     pred_fwpt,
         "Water Rate (STB/d)", "Cum. Water (MSTB)", axes[1]),
        (ecl_fgpr, opm_val_fgpr, pred_fgpr,
         ecl_fgpt, val_fgpt,     pred_fgpt,
         "Gas Rate (Mscf/d)",  "Cum. Gas (MMscf)",  axes[2]),
    ]

    for (ecl_v, val_v, pred_v,
         ecl_c, val_c, pred_c,
         ylabel_r, ylabel_c, ax) in rate_rows:

        # ---- primary axis: rates ----
        ax.plot(ecl_yr,  ecl_v,  color="#1f77b4", lw=1.8, label="Eclipse (reference)", alpha=0.9)
        ax.plot(val_yr,  val_v,  color="#d62728", lw=1.8, linestyle="--",
                label="OPM Flow (match)", alpha=0.9)
        ax.plot(pred_yr, pred_v, color="#2ca02c", lw=1.8, linestyle=":",
                label="OPM Flow (forward prediction)", alpha=0.9)
        ax.axvspan(val_end_yr, pred_yr[-1] if len(pred_yr) else val_end_yr + 1,
                   alpha=0.08, color="#2ca02c")
        ax.axvline(val_end_yr, color="grey", linestyle="-.", lw=1, alpha=0.6)
        ax.set_ylabel(ylabel_r, fontsize=9, color="#333333")
        ax.tick_params(axis="y", labelcolor="#333333")
        ax.grid(True, alpha=0.3)

        # ---- secondary axis: cumulatives ----
        ax2 = ax.twinx()
        scale = 1e3   # STB → MSTB, Mscf → MMscf
        if ecl_c is not None:
            ax2.plot(ecl_yr,  ecl_c  / scale, color="#1f77b4", lw=0.9,
                     linestyle="-",  alpha=0.45)
        if val_c is not None:
            ax2.plot(val_yr,  val_c  / scale, color="#d62728", lw=0.9,
                     linestyle="--", alpha=0.45)
        if pred_c is not None:
            ax2.plot(pred_yr, pred_c / scale, color="#2ca02c", lw=0.9,
                     linestyle=":",  alpha=0.45)
        ax2.set_ylabel(ylabel_c, fontsize=8, color="#888888")
        ax2.tick_params(axis="y", labelcolor="#888888", labelsize=7)
        ax2.spines["right"].set_alpha(0.4)

        # Legend on primary axis only
        ax.legend(fontsize=7.5, loc="upper right")

    # Annotations for time regions
    for ax in axes:
        ylim = ax.get_ylim()
        mid_y = (ylim[0] + ylim[1]) * 0.92
        ax.text(ecl_yr[len(ecl_yr)//2], mid_y, "Match period",
                ha="center", fontsize=8, color="#555555", style="italic", alpha=0.7)
        ax.text(val_end_yr + 0.5, mid_y, "Forward prediction",
                ha="center", fontsize=8, color="#2ca02c", style="italic", alpha=0.7)

    axes[-1].set_xlabel("Simulation Year", fontsize=9)
    fig.suptitle(
        "Offshore Field X — Eclipse vs OPM Flow\n"
        "Simulation Match + 1-Year Forward Prediction",
        fontsize=11, fontweight="bold"
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path.name}")


def main():
    from resdata.summary import Summary as EclSum

    print("\nAgent 07 — Extend Simulation +1 Year")
    print("-" * 60)

    out_dir    = Path(OFX_OUTPUT_DIR)
    fig_dir    = out_dir / "figures"
    pred_dir   = out_dir / "predict"
    clean_deck = out_dir / "FIELD_X_001_OPM_CLEAN.DATA"
    fig_dir.mkdir(parents=True, exist_ok=True)

    if not clean_deck.exists():
        print(f"  ERROR: clean deck not found: {clean_deck}")
        print("  Run agent_06 first.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 1. Extend the schedule
    # -----------------------------------------------------------------------
    print(f"  Reading clean deck: {clean_deck}")
    with open(clean_deck, "r", errors="replace") as fh:
        text = fh.read()

    print(f"  Extending schedule to {PREDICT_END_DAY} {PREDICT_END_MONTH} {PREDICT_END_YEAR}...")
    text_pred = extend_schedule(text)

    pred_data_file = out_dir / "FIELD_X_001_PREDICT.DATA"
    with open(pred_data_file, "w", errors="replace") as fh:
        fh.write(text_pred)
    print(f"  Prediction deck written: {pred_data_file}")

    # -----------------------------------------------------------------------
    # 2. Run OPM on the prediction deck
    # -----------------------------------------------------------------------
    ok = run_opm(pred_data_file, pred_dir)
    if not ok:
        print("  ERROR: OPM prediction run failed.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 3. Load Eclipse reference + validation UNSMRY (needed before pred mask)
    # -----------------------------------------------------------------------
    eclipse_unsmry = os.environ.get("OFX_ECLIPSE_UNSMRY", "data/FIELD_X_001.UNSMRY")
    val_stem       = Path(OFX_DATA_FILE).stem
    val_unsmry     = out_dir / f"{val_stem}.UNSMRY"

    ecl_sum  = EclSum(eclipse_unsmry, lazy_load=False)
    val_sum  = EclSum(str(val_unsmry), lazy_load=False)

    # -----------------------------------------------------------------------
    # 4. Load prediction UNSMRY
    # -----------------------------------------------------------------------
    stem         = pred_data_file.stem   # FIELD_X_001_PREDICT
    pred_unsmry  = pred_dir / f"{stem}.UNSMRY"
    if not pred_unsmry.exists():
        print(f"  ERROR: prediction UNSMRY not found: {pred_unsmry}")
        sys.exit(1)

    print(f"  Loading prediction summary: {pred_unsmry}")
    pred_sum = EclSum(str(pred_unsmry), lazy_load=False)

    def get_vec(s, key):
        try:
            return np.array(s.numpy_vector(key))
        except Exception:
            return np.zeros(len(np.array(s.days)))

    pred_days = np.array(pred_sum.days)

    # Prediction period: beyond the actual last Eclipse day.
    # Use ecl_days[-1] (not year arithmetic) so the join point lands
    # exactly at the end of the validation data regardless of start-date
    # offset (START = 1 JUL 2000 ≠ 1 JAN 2000).
    ecl_days     = np.array(ecl_sum.days)
    val_end_days = float(ecl_days[-1])
    pred_mask    = pred_days > val_end_days

    # Index of the last point at or before val_end_days in the prediction UNSMRY
    join_idx = int(np.searchsorted(pred_days, val_end_days, side='right')) - 1
    join_idx = max(0, join_idx)

    # Prepend join point so lines meet exactly
    def pred_vec(key):
        v = get_vec(pred_sum, key)
        return np.concatenate([[v[join_idx]], v[pred_mask]])

    p_days = np.concatenate([[pred_days[join_idx]], pred_days[pred_mask]])
    p_fopr = pred_vec("FOPR")
    p_fwpr = pred_vec("FWPR")
    p_fgpr = pred_vec("FGPR")

    def to_yr(d): return 2000.5 + np.asarray(d) / 365.25
    print(f"  Prediction points: {len(p_days)}  "
          f"({to_yr(p_days[0]):.2f} – {to_yr(p_days[-1]):.2f})")

    val_days = np.array(val_sum.days)

    ecl_fopr = get_vec(ecl_sum, "FOPR")
    ecl_fwpr = get_vec(ecl_sum, "FWPR")
    ecl_fgpr = get_vec(ecl_sum, "FGPR")
    ecl_fopt = get_vec(ecl_sum, "FOPT")
    ecl_fwpt = get_vec(ecl_sum, "FWPT")
    ecl_fgpt = get_vec(ecl_sum, "FGPT")

    val_fopr = np.interp(ecl_days, val_days, get_vec(val_sum, "FOPR"))
    val_fwpr = np.interp(ecl_days, val_days, get_vec(val_sum, "FWPR"))
    val_fgpr = np.interp(ecl_days, val_days, get_vec(val_sum, "FGPR"))
    val_fopt = np.interp(ecl_days, val_days, get_vec(val_sum, "FOPT"))
    val_fwpt = np.interp(ecl_days, val_days, get_vec(val_sum, "FWPT"))
    val_fgpt = np.interp(ecl_days, val_days, get_vec(val_sum, "FGPT"))

    p_fopt = pred_vec("FOPT")
    p_fwpt = pred_vec("FWPT")
    p_fgpt = pred_vec("FGPT")

    # -----------------------------------------------------------------------
    # 5. Generate headline figure
    # -----------------------------------------------------------------------
    print("  Generating prediction figure...")
    make_prediction_figure(
        ecl_days, ecl_fopr, ecl_fwpr, ecl_fgpr,
        ecl_days, val_fopr, val_fwpr, val_fgpr,
        p_days,   p_fopr,  p_fwpr,  p_fgpr,
        ecl_fopt, ecl_fwpt, ecl_fgpt,
        val_fopt, val_fwpt, val_fgpt,
        p_fopt,   p_fwpt,  p_fgpt,
        fig_dir / "field_comparison_with_prediction.png"
    )

    print(f"\n  Agent 07 complete.")
    print(f"  Prediction outputs: {pred_dir}")
    print(f"  Headline figure:    {fig_dir / 'field_comparison_with_prediction.png'}")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
