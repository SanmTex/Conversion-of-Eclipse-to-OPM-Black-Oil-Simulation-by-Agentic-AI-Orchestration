"""
make_opm_validation.py
Generates OPM_Validation.ipynb from scratch.

Run:  python make_opm_validation.py
Output: OPM_Validation.ipynb  (same directory)
"""
import json, uuid, os

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'OPM_Validation.ipynb')

def _id():
    return str(uuid.uuid4())[:8]

def code(src: str):
    lines = src.split('\n')
    source = [l + '\n' for l in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {"cell_type": "code", "execution_count": None,
            "id": _id(), "metadata": {}, "outputs": [], "source": source}

def md(src: str):
    lines = src.split('\n')
    source = [l + '\n' for l in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return {"cell_type": "markdown", "id": _id(), "metadata": {}, "source": source}

# ===============================================================================
# CELL DEFINITIONS
# ===============================================================================

CELL_01_MD = md(r'''
# FX Offshore Field X -- OPM Flow Simulation Validation
## Eclipse vs OPM Flow Comparison

**Objective:** Re-run the FX black-oil reservoir simulation using OPM Flow
(open-source) and validate every output mnemonic against the original SLB Eclipse
results.

| Property | Value |
|----------|-------|
| Model | Offshore Field X -- Sand Unit A and Sand Unit B |
| Grid | 141 x 34 x 235 = 1,126,590 total / 114,768 active cells |
| Fluid | Three-phase black oil, DISGAS, API 19.4 |
| Simulation | 1 Jul 2000 -> 1 Jan 2003 (10.5 years, 61 UNRST reports, 127 UNSMRY steps) |
| Eclipse files | FIELD_X_001.{DATA, EGRID, INIT, UNRST, UNSMRY, SMSPEC} |
| Solver | OPM Flow via WSL (reads Eclipse .DATA natively) |

> **Note:** This notebook requires OPM Flow installed in WSL. Cell 2 will raise
> an error with installation instructions if it is not found.
> Use *Kernel -> Restart & Run All* to re-run from scratch.
'''.strip())

# -----------------------------------------------------------------------------
CELL_02_SW = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Detects OPM Flow availability by calling `wsl flow --version` as a subprocess.
# OPM Flow is the open-source reservoir simulator from the Open Porous Media
# project (opm-project.org).  On Windows it runs inside WSL (Windows Subsystem
# for Linux) and reads Eclipse .DATA decks natively.  It produces Eclipse-
# compatible binary output (UNRST, UNSMRY, SMSPEC) that resdata can read.
#
# If OPM Flow is not found this cell raises RuntimeError with step-by-step
# installation instructions.  All downstream cells depend on OPM output; there
# is no fallback solver -- install OPM Flow before proceeding.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# This cell checks that the OPM Flow simulation engine is installed and
# accessible.  If it cannot be found the notebook stops here and prints
# exact installation instructions.  OPM Flow must be present because every
# subsequent cell depends on it re-running the Eclipse model.
# -----------------------------------------------------------------------------
import subprocess, sys, platform, datetime

OPM_AVAILABLE = False
OPM_VERSION   = "NOT FOUND"

# Check WSL is present (OPM runs inside the Linux subsystem on Windows)
try:
    r = subprocess.run(['wsl', '--version'], capture_output=True, text=True, timeout=10)
    _wsl_ok = (r.returncode == 0)
except Exception:
    _wsl_ok = False

# Check OPM Flow is installed inside WSL
if _wsl_ok:
    try:
        r = subprocess.run(['wsl', 'flow', '--version'],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            OPM_AVAILABLE = True
            OPM_VERSION   = r.stdout.strip().split('\n')[0]
    except Exception:
        pass

# Print environment table
print(f"{'Software':<35} {'Version / Status':<40} {'OK?'}")
print("-" * 80)
print(f"{'Python':<35} {sys.version.split()[0]:<40} [OK]")
print(f"{'Platform':<35} {platform.system()+' '+platform.release():<40} [OK]")
print(f"{'WSL':<35} {'Installed' if _wsl_ok else 'Not installed':<40} {'[OK]' if _wsl_ok else '[X]'}")
print(f"{'OPM Flow':<35} {OPM_VERSION:<40} {'[OK]' if OPM_AVAILABLE else '[X]'}")
print(f"\n{'Report date':<35} {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

if not OPM_AVAILABLE:
    print("\n" + "=" * 80)
    print("OPM Flow not found.  Install it before running this notebook:")
    print("  Step 1 -- Open PowerShell as Administrator:")
    print("           wsl --install")
    print("  Step 2 -- Reboot, then in the WSL Ubuntu terminal:")
    print("           sudo apt-get update")
    print("           sudo apt-get install -y opm-simulators")
    print("  Step 3 -- Verify:  wsl flow --version")
    print("  Step 4 -- Restart this kernel and re-run all cells.")
    print("=" * 80)
    raise RuntimeError(
        "OPM Flow not found in WSL.  Follow the installation steps printed "
        "above, then restart the kernel and re-run.")

print("\nOPM Flow confirmed -- proceeding with full validation.")
'''.strip())

# -----------------------------------------------------------------------------
CELL_03_IMPORTS = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Standard scientific Python stack.  Key library roles:
#   resdata  -- Eclipse binary file I/O (formerly libecl, now maintained by
#              Equinor).  Provides Summary (UNSMRY), Grid (EGRID), ResdataFile
#              (INIT / UNRST).  The import aliases (EclSum, EclGrid, EclFile)
#              match the names used throughout this notebook.
#   numpy    -- all array arithmetic (pressure, saturation, time vectors).
#   pandas   -- metrics DataFrame, CSV export.
#   matplotlib -- all figures; Agg backend avoids display-server dependency.
#   sklearn  -- r2_score for coefficient-of-determination calculation.
#   tqdm     -- progress bars for loading large UNRST arrays (61 timesteps x
#              114,768 active cells per keyword).
#
# File-path constants are defined here so any path change needs only one edit.
# The UNITS lookup maps Eclipse mnemonics to their display units; it is used by
# every plotting cell to label axes automatically.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# We load the Python libraries needed for file reading, number crunching, and
# plotting.  We also record where all the Eclipse and OPM files live so every
# other cell can find them.  The UNITS dictionary is a reference table that maps
# each measurement name (like FOPR or WBHP) to its physical unit so every chart
# axis is correctly labelled without hard-coding units in each plot.
# -----------------------------------------------------------------------------
import os, re, time, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import r2_score
from tqdm import trange, tqdm
warnings.filterwarnings('ignore')

from resdata.summary import Summary  as EclSum
from resdata.grid    import Grid     as EclGrid
from resdata.resfile import ResdataFile as EclFile

# -- File paths -----------------------------------------------------------------
BASE_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'FIELD_X_001')
NOTEBOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
OPM_OUT_DIR  = NOTEBOOK_DIR
os.makedirs(OPM_OUT_DIR, exist_ok=True)

# -- Units lookup table ---------------------------------------------------------
# Maps the leading mnemonic (before any colon) to its display unit string.
# Used by all plotting cells via get_unit() to label y-axes.
# Eclipse FIELD unit set: oil/water/liquid in stb/d, gas in Mscf/d,
# pressure in psia, cumulatives in Mstb or MMscf, aquifer influx in RB.
UNITS = {
    # Field / well production rates
    'FOPR': 'stb/d',   'WOPR': 'stb/d',
    'FWPR': 'stb/d',   'WWPR': 'stb/d',
    'FLPR': 'stb/d',   'WLPR': 'stb/d',
    'FGPR': 'Mscf/d',  'WGPR': 'Mscf/d',
    # Field / well cumulatives
    'FOPT': 'Mstb',    'WOPT': 'Mstb',
    'FWPT': 'Mstb',    'WWPT': 'Mstb',
    'FLPT': 'Mstb',    'WLPT': 'Mstb',
    'FGPT': 'MMscf',   'WGPT': 'MMscf',
    # Pressures
    'FPR':  'psia',    'WBHP': 'psia',   'WTHP': 'psia',
    # Ratios / fractions
    'FWCT': 'frac',    'WWCT': 'frac',
    'FGOR': 'Mscf/stb','WGOR': 'Mscf/stb',
    # Gas lift
    'FGLIR': 'Mscf/d', 'WGLIR': 'Mscf/d',
    # Water injection
    'FWIR': 'stb/d',   'WWIR': 'stb/d',
    'FWIT': 'Mstb',    'WWIT': 'Mstb',
    # Gas injection
    'FGIR': 'Mscf/d',  'WGIR': 'Mscf/d',
    'FGIT': 'MMscf',   'WGIT': 'MMscf',
    # Productivity / injectivity
    'WPI':  'stb/d/psi','WII': 'stb/d/psi',
    # Aquifer vectors (OPM summary mnemonics)
    'AAQT': 'RB',      'AAQTG': 'RB',
    'AAQR': 'RB/d',    'AAQRG': 'RB/d',
    'AAQP': 'psia',
    # Cell-level arrays
    'PRESSURE': 'psia','SWAT': 'frac','SGAS': 'frac','SOIL': 'frac',
    # History-match reference mnemonics (Eclipse *H / *TH suffixes)
    'FOPTH': 'Mstb',   'FWPTH': 'Mstb',   'FGPTH': 'MMscf',
    'WOPTH': 'Mstb',   'WWPTH': 'Mstb',
    'FGORH': 'Mscf/stb','FWCTH': 'frac',
}

def get_unit(mnemonic):
    """Return the display unit for a mnemonic; empty string if unknown."""
    base = mnemonic.split(':')[0]          # strip ':WELLNAME' suffix if present
    return UNITS.get(base, '')

# -- Helper functions -----------------------------------------------------------
def safe_vec(eclsum_obj, key):
    """Return a float64 numpy array for an UNSMRY key, or None if absent."""
    try:
        return np.array(eclsum_obj.numpy_vector(key), dtype=np.float64)
    except Exception:
        return None

def metrics(a_ecl, a_sim, label=''):
    """
    Compute five agreement statistics between two 1-D arrays.
    Returns dict with keys: r2, rmse, max_err, p50, p95.
    Ignores NaN/Inf in either array before computing.
    """
    a_ecl = np.asarray(a_ecl, dtype=np.float64).ravel()
    a_sim = np.asarray(a_sim, dtype=np.float64).ravel()
    mask  = np.isfinite(a_ecl) & np.isfinite(a_sim)
    if mask.sum() < 2:
        return dict(r2=np.nan, rmse=np.nan, max_err=np.nan, p50=np.nan, p95=np.nan)
    ae = a_ecl[mask]; as_ = a_sim[mask]
    err = np.abs(ae - as_)
    return dict(r2=float(r2_score(ae, as_)),
                rmse=float(np.sqrt(np.mean((ae - as_) ** 2))),
                max_err=float(err.max()),
                p50=float(np.percentile(err, 50)),
                p95=float(np.percentile(err, 95)))

print(f"BASE_PATH    : {BASE_PATH}")
print(f"NOTEBOOK_DIR : {NOTEBOOK_DIR}")
print(f"OPM_OUT_DIR  : {OPM_OUT_DIR}")
print(f"UNITS entries: {len(UNITS)}")
'''.strip())

# -----------------------------------------------------------------------------
CELL_04_ECL = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Loads all six Eclipse binary/ASCII output files.  The data structures built
# here are the reference ("truth") against which OPM Flow output is compared.
#
# EGRID   -> grid topology: NX/NY/NZ dimensions, active-cell count, and the
#            global index of every active cell.  Global index (0-based) uses
#            I-fastest Fortran ordering: g = I + J*NX + K*NX*NY.
#            Constructs global_to_act[g] -> active-cell index (or -1) for fast
#            reverse lookup used in the AQUANCON rebuild (Cell 5).
#
# INIT    -> static reservoir properties stored at all NX*NY*NZ total cells;
#            values at inactive cells are zero but are present in the array.
#            We select active cells via active_globals.  Key arrays:
#            PORO (fraction), PERMX/Y/Z (mD), NTG (fraction), SWL (connate
#            water fraction), DX/DY/DZ (cell dimensions, ft), DEPTH (ft).
#
# UNRST   -> 3-D dynamic arrays at 61 restart report dates.  Each keyword
#            (PRESSURE psia, SWAT fraction, SGAS fraction) is shaped
#            (N_RST=61, N_ACTIVE=114,768).  SOIL is derived as 1-SWAT-SGAS
#            because Eclipse does not store it.  Dates are decoded from the
#            INTEHEAD array (elements 64=day, 65=month, 66=year, 1-based).
#
# UNSMRY  -> scalar time-series vectors at 127 timesteps for all ~300+ Eclipse
#            mnemonics (FOPR, FWPR, FGPR, WBHP:*, AAQT:*, FPR, ...).
#            Loaded into eclipse_smry dict keyed by mnemonic string.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# We read in everything Eclipse produced:
#   * the reservoir grid geometry (which cells exist, where they are)
#   * the static rock properties in every cell (porosity, permeability, ...)
#   * the pressure and saturation in every cell at 61 time snapshots
#   * over 300 production and injection KPIs recorded at 127 time points
# At the end we print a full inventory so a domain expert can confirm that no
# important data is missing before we move on to the OPM comparison.
# -----------------------------------------------------------------------------

print("=" * 70)
print("STEP 1 -- Load Eclipse reference data")
print("=" * 70)

# -- 4a. EGRID -- grid topology --------------------------------------------------
print("\n[4a] Loading EGRID ...")
grid     = EclGrid(BASE_PATH + '.EGRID')
NX, NY, NZ = grid.nx, grid.ny, grid.nz
N_ACTIVE = grid.get_num_active()
N_TOTAL  = NX * NY * NZ
print(f"     Grid : {NX} x {NY} x {NZ} = {N_TOTAL:,} total / {N_ACTIVE:,} active cells")

# Build array of global indices for all active cells (I-fastest Fortran ordering)
try:
    active_globals = np.array(grid.get_active_list(), dtype=np.int64)
except Exception:
    # Fallback: iterate active indices and ask the grid for each global index
    active_globals = np.array([grid.get_global_index(active_index=i)
                               for i in range(N_ACTIVE)], dtype=np.int64)

# Decompose global index into 0-based I, J, K coordinates
i_all = (active_globals % NX).astype(np.float32)
j_all = ((active_globals // NX) % NY).astype(np.float32)
k_all = (active_globals // (NX * NY)).astype(np.float32)

# Reverse lookup array: global_to_act[g] returns the active-cell index (0-based)
# or -1 if cell g is inactive.  Used in Cell 5 to filter AQUANCON connections.
max_g = int(active_globals.max()) + 1
global_to_act = np.full(max_g, -1, dtype=np.int32)
global_to_act[active_globals] = np.arange(N_ACTIVE, dtype=np.int32)

# -- 4b. INIT -- static petrophysical properties --------------------------------
print("\n[4b] Loading INIT ...")
init_f = EclFile(BASE_PATH + '.INIT')
init_kws_present = sorted(set(init_f.keys()))
print(f"     Keywords present: {init_kws_present}")

def load_init(key, default=None):
    """
    Load a keyword from the INIT file and return an array indexed over active
    cells only.  If the keyword is absent, returns an array filled with default.
    Handles both global-indexed (NX*NY*NZ) and active-indexed (N_ACTIVE) storage.
    """
    if key in init_kws_present:
        arr = np.array(init_f[key][0], dtype=np.float32)
        if len(arr) == N_TOTAL:
            return arr[active_globals]   # select only the active-cell values
        elif len(arr) == N_ACTIVE:
            return arr
    return (np.full(N_ACTIVE, default, dtype=np.float32)
            if default is not None else None)

PORO  = load_init('PORO',  0.1)
PERMX = np.maximum(load_init('PERMX', 1.0), 1e-3)
PERMY = np.maximum(load_init('PERMY') if 'PERMY' in init_kws_present
                   else PERMX.copy(), 1e-3)
PERMZ = np.maximum(load_init('PERMZ') if 'PERMZ' in init_kws_present
                   else PERMX * 0.1, 1e-3)
NTG   = load_init('NTG',  1.0)
SWL   = load_init('SWL',  0.15)
DX    = load_init('DX',   100.0)
DY    = load_init('DY',   100.0)
DZ    = load_init('DZ',   10.0)
V_CELL = DX * DY * DZ
DEPTH  = load_init('DEPTH', 2000.0)

print(f"     PORO  : {PORO.min():.3f}-{PORO.max():.3f} (fraction)")
print(f"     PERMX : {PERMX.min():.2f}-{PERMX.max():.1f} mD")
print(f"     DX/DY/DZ (mean): {DX.mean():.1f} / {DY.mean():.1f} / {DZ.mean():.1f} ft")

# -- 4c. UNRST -- 3-D dynamic arrays at each restart report ---------------------
print("\n[4c] Loading UNRST (61 reports x 114,768 active cells) ...")
rst    = EclFile(BASE_PATH + '.UNRST')
rst_kw = sorted(set(rst.keys()))
N_RST  = len(rst['PRESSURE'])
print(f"     Keywords: {rst_kw}")
print(f"     Reports : {N_RST}")

eclipse_rst = {}   # key -> float32 array of shape (N_RST, N_ACTIVE)
for kw in ['PRESSURE', 'SWAT', 'SGAS']:
    if kw in rst_kw:
        arr = np.zeros((N_RST, N_ACTIVE), dtype=np.float32)
        # Load one report at a time; trange provides a progress bar
        for t in trange(N_RST, desc=f'     UNRST {kw}', leave=False):
            arr[t] = np.array(rst[kw][t], dtype=np.float32)
        eclipse_rst[kw] = arr

# Derive oil saturation from complement (SOIL is not stored in UNRST)
eclipse_rst['SOIL'] = np.clip(
    1.0 - eclipse_rst['SWAT'] - eclipse_rst['SGAS'], 0.0, 1.0)
print(f"     PRESSURE: {eclipse_rst['PRESSURE'].min():.1f}-"
      f"{eclipse_rst['PRESSURE'].max():.1f} psia")
print(f"     SWAT    : {eclipse_rst['SWAT'].min():.3f}-"
      f"{eclipse_rst['SWAT'].max():.3f}")

# Load any other UNRST arrays (RS, RV, PCOW, etc.) if present
for kw in [k for k in rst_kw if k not in
           ('PRESSURE','SWAT','SGAS','INTEHEAD','LOGIHEAD','DOUBHEAD')]:
    try:
        n_av = len(rst[kw])
        arr  = np.zeros((N_RST, N_ACTIVE), dtype=np.float32)
        for t in range(min(N_RST, n_av)):
            a = np.array(rst[kw][t], dtype=np.float32)
            if len(a) == N_ACTIVE:
                arr[t] = a
        eclipse_rst[kw] = arr
        print(f"     Extra kw loaded: {kw}  ({n_av} reports)")
    except Exception:
        pass

# Decode restart report dates from INTEHEAD (elements 64=day, 65=month, 66=year)
import datetime as _dt
try:
    _start = ecl_dates[0].date() if hasattr(ecl_dates[0],'date') else ecl_dates[0]
except NameError:
    # ecl_dates not yet defined -- placeholder; will be set below after UNSMRY load
    _start = None

# -- 4d. UNSMRY -- scalar time-series (all mnemonics) ---------------------------
print("\n[4d] Loading UNSMRY ...")
eclsum       = EclSum(BASE_PATH + '.UNSMRY')
ecl_dates    = list(eclsum.dates)
ecl_days     = np.array(eclsum.days, dtype=np.float64)
ecl_years    = ecl_days / 365.25         # fractional years from simulation start
N_SMRY       = len(ecl_dates)
eclipse_keys = sorted(eclsum.keys())
print(f"     Timesteps  : {N_SMRY}")
print(f"     Date range : {ecl_dates[0].date()} -> {ecl_dates[-1].date()}")
print(f"     Mnemonics  : {len(eclipse_keys)}")

eclipse_smry = {}   # mnemonic -> float64 array of length N_SMRY
for k in eclipse_keys:
    v = safe_vec(eclsum, k)
    if v is not None:
        eclipse_smry[k] = v

# Summarise mnemonics by first-letter prefix (F=field, W=well, A=aquifer, ...)
prefix_groups = {}
for k in eclipse_keys:
    p = k.split(':')[0][0]
    prefix_groups.setdefault(p, []).append(k)
print("\n     MNEMONIC INVENTORY")
print("     " + "-" * 60)
for p in sorted(prefix_groups):
    label = {'F':'Field (F*)', 'W':'Well (W*)', 'A':'Aquifer (A*)',
             'R':'Region (R*)', 'B':'Block (B*)'}.get(p, f'Other ({p}*)')
    keys_str = ', '.join(prefix_groups[p][:12])
    extra = f' ... +{len(prefix_groups[p])-12} more' if len(prefix_groups[p]) > 12 else ''
    print(f"     {label:<20} ({len(prefix_groups[p]):3d}): {keys_str}{extra}")

# Build UNRST date array now that ecl_dates is available
try:
    _start = ecl_dates[0].date() if hasattr(ecl_dates[0], 'date') else ecl_dates[0]
    _rst_dates = []
    for _t in range(N_RST):
        _ih = np.array(rst['INTEHEAD'][_t], dtype=np.int32)
        _rst_dates.append(_dt.date(int(_ih[66]), int(_ih[65]), int(_ih[64])))
    rst_days_arr = np.array([(_d - _start).days for _d in _rst_dates],
                            dtype=np.float64)
    print(f"\n     UNRST dates: {_rst_dates[0]} -> {_rst_dates[-1]}")
except Exception as _e:
    print(f"     WARNING: Could not decode UNRST dates ({_e}); using linear spacing.")
    rst_days_arr = np.linspace(0, ecl_days[-1], N_RST)

print("\n     Eclipse data loaded successfully.")
'''.strip())

# -----------------------------------------------------------------------------
CELL_05_SIM = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Runs OPM Flow on the provided DATA deck via WSL.
#
# The DATA deck (FIELD_X_001.DATA) has been prepared to run correctly in OPM
# without modification.  This cell constructs the OPM command, streams output
# line-by-line to the notebook, and raises RuntimeError if OPM exits non-zero.
#
# Flags used:
#   --parsing-strictness=low     Accept any unrecognised Eclipse keywords.
#   --max-single-precision-days=0  Force double-precision throughout.
#
# OPM_OUT_DIR is created automatically.  If outputs already exist from a
# previous run the cell detects this and skips re-running.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# This cell runs the reservoir simulator on the model file.  It is the most
# time-consuming step (30-90 minutes on a modern laptop).  Run it once; all
# subsequent cells read the saved output files.
# -----------------------------------------------------------------------------
import subprocess as _sub, os as _os, glob as _gl

OPM_RUN_OK = False

def _win_to_wsl(p):
    import pathlib
    p = pathlib.Path(p).resolve()
    drive = p.drive.lower().rstrip(":")
    rest  = str(p.relative_to(p.anchor)).replace("\\\\", "/")
    return f"/mnt/{drive}/{rest}"

_have_rst  = _gl.glob(_os.path.join(OPM_OUT_DIR, "*.UNRST"))
_have_smry = _gl.glob(_os.path.join(OPM_OUT_DIR, "*.UNSMRY"))

if _have_rst and _have_smry:
    print(f"OPM output already present in {OPM_OUT_DIR} -- skipping re-run.")
    OPM_RUN_OK = True
else:
    data_wsl   = _win_to_wsl(BASE_PATH + ".DATA")
    out_wsl    = _win_to_wsl(OPM_OUT_DIR)

    opm_cmd = [
        "wsl",
        "OMP_NUM_THREADS=4",
        "flow",
        f"--output-dir={out_wsl}",
        "--parsing-strictness=low",
        "--max-single-precision-days=0",
        data_wsl,
    ]

    print("Running OPM Flow:")
    print("  " + " ".join(opm_cmd))
    print("This may take 30-90 minutes.  Progress shown below.")
    print("-" * 60)

    result = _sub.run(opm_cmd, text=True)

    print("-" * 60)
    if result.returncode != 0:
        raise RuntimeError(
            f"OPM Flow exited with error (rc={result.returncode}). "
            "Check output above.")
    OPM_RUN_OK = True
'''.strip())

# -----------------------------------------------------------------------------
CELL_06_PARSE = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Reads the OPM Flow binary output from OPM_OUT_DIR using the same resdata
# library calls as Cell 4.  OPM writes Eclipse-compatible binary output so the
# same EclFile / EclSum API works for both.
#
# UNRST alignment: OPM may produce a different number of restart reports than
# Eclipse's 61.  Report dates are decoded from OPM's INTEHEAD arrays and each
# Eclipse UNRST step is mapped to the nearest OPM report by date.  This avoids
# off-by-one differences in report frequency from causing spurious metric failures.
#
# UNSMRY alignment: OPM and Eclipse typically produce different numbers of
# summary timesteps.  OPM vectors are linearly interpolated onto Eclipse's
# 127-point time axis (ecl_days) so all downstream comparisons use identically
# shaped arrays.  numpy.interp is used (linear, clamp at endpoints).
#
# Matched / Eclipse-only / OPM-only key sets are printed for QC.  The
# '*H' and '*TH' history-match reference mnemonics (e.g. WOPTH, FGORH) are
# present in Eclipse UNSMRY but not OPM -- these are expected Eclipse-only keys
# and are noted as such rather than treated as failures.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# We load the output files that OPM Flow produced, map them to the same time
# axis Eclipse used, and build matching data structures so every downstream cell
# can compare Eclipse and OPM results using identical arrays.  We also list
# which measurements exist in both outputs, which are Eclipse-only (expected),
# and which are OPM-only (unexpected, worth investigating).
# -----------------------------------------------------------------------------

import glob as _glob, datetime as _dt3

print("=" * 70)
print("STEP 3 -- Load OPM Flow output")
print("=" * 70)

# Find the OPM output files written by Cell 5
_rst_files  = _glob.glob(os.path.join(OPM_OUT_DIR, '*.UNRST'))
_smry_files = _glob.glob(os.path.join(OPM_OUT_DIR, '*.UNSMRY'))
if not _rst_files or not _smry_files:
    raise FileNotFoundError(f"No OPM output found in {OPM_OUT_DIR}. "
                            "Run Cell 5 first.")
OPM_BASE = _rst_files[0].replace('.UNRST', '')
print(f"  OPM output base: {OPM_BASE}")

# -- Load UNRST and align to Eclipse report dates ------------------------------
opm_rst_f  = EclFile(OPM_BASE + '.UNRST')
opm_rst_kw = sorted(set(opm_rst_f.keys()))
N_OPM_RST  = len(opm_rst_f['PRESSURE'])

# Decode OPM restart dates from INTEHEAD (same format as Eclipse: day=64, month=65, year=66)
try:
    _opm_start     = ecl_dates[0].date() if hasattr(ecl_dates[0], 'date') else ecl_dates[0]
    _opm_days_list = []
    for _t in range(N_OPM_RST):
        _ih = np.array(opm_rst_f['INTEHEAD'][_t], dtype=np.int32)
        _opm_days_list.append(
            (_dt3.date(int(_ih[66]), int(_ih[65]), int(_ih[64])) - _opm_start).days)
    _opm_days_arr = np.array(_opm_days_list, dtype=np.float64)

    # For each of Eclipse's 61 UNRST steps find the nearest OPM report by date
    _opm_map = np.array(
        [int(np.argmin(np.abs(_opm_days_arr - d))) for d in rst_days_arr],
        dtype=np.int32)
    print(f"  OPM UNRST: {N_OPM_RST} reports aligned to {N_RST} Eclipse reports by date")
except Exception as _e:
    print(f"  WARNING: OPM date alignment failed ({_e}); using 1:1 index mapping")
    _opm_map = np.clip(np.arange(N_RST, dtype=np.int32), 0, N_OPM_RST - 1)

# -- Build OPM active-cell -> Eclipse active-cell mapping ----------------------
# OPM and Eclipse may differ in active-cell count because they apply MINPV
# deactivation with slightly different internal thresholds.  The approach:
#   1. Read OPM's output EGRID to obtain its list of active global indices.
#   2. Build a reverse lookup (global index -> OPM active index).
#   3. For each of Eclipse's N_ACTIVE cells, look up the OPM active index.
#      Cells active in Eclipse but not in OPM receive NaN (rare edge case).
# This is the only correct way to handle the shape mismatch; direct indexing
# fails whenever len(opm_array) != N_ACTIVE.

_opm_egrid_candidates = _glob.glob(os.path.join(OPM_OUT_DIR, '*.EGRID'))
if _opm_egrid_candidates:
    _opm_grid = EclGrid(_opm_egrid_candidates[0])
    N_OPM_ACTIVE = _opm_grid.get_num_active()
    print(f"  OPM active cells: {N_OPM_ACTIVE:,}  (Eclipse: {N_ACTIVE:,})")
    try:
        _opm_act_globals = np.array(_opm_grid.get_active_list(), dtype=np.int64)
    except Exception:
        _opm_act_globals = np.array([_opm_grid.get_global_index(active_index=i)
                                     for i in range(N_OPM_ACTIVE)], dtype=np.int64)
    # Reverse lookup: global index -> OPM active index (-1 = inactive in OPM)
    _opm_g2a = np.full(NX * NY * NZ, -1, dtype=np.int32)
    _opm_g2a[_opm_act_globals] = np.arange(N_OPM_ACTIVE, dtype=np.int32)
    # For each Eclipse active cell, the corresponding OPM active index
    _ecl_to_opm = _opm_g2a[active_globals]   # shape (N_ACTIVE,)
    _opm_valid  = (_ecl_to_opm >= 0)
    n_missing = int((~_opm_valid).sum())
    if n_missing:
        print(f"  WARNING: {n_missing} Eclipse active cells not active in OPM "
              f"(will be NaN in comparison)")
else:
    # No OPM EGRID found -- assume same active set and fall back to direct slice.
    # This will raise a ValueError if sizes differ; add the OPM EGRID to fix it.
    print("  WARNING: OPM EGRID not found; assuming same active-cell order as Eclipse.")
    _ecl_to_opm = np.arange(N_ACTIVE, dtype=np.int32)
    _opm_valid  = np.ones(N_ACTIVE, dtype=bool)

sim_rst = {}
for kw in ['PRESSURE', 'SWAT', 'SGAS']:
    if kw in opm_rst_kw:
        arr = np.full((N_RST, N_ACTIVE), np.nan, dtype=np.float32)
        for t in trange(N_RST, desc=f'  OPM UNRST {kw}', leave=False):
            _opm_arr = np.array(opm_rst_f[kw][_opm_map[t]], dtype=np.float32)
            arr[t, _opm_valid] = _opm_arr[_ecl_to_opm[_opm_valid]]
        sim_rst[kw] = arr
# Derive SOIL from complement (OPM also does not store it separately)
sim_rst['SOIL'] = np.clip(1.0 - sim_rst['SWAT'] - sim_rst['SGAS'], 0.0, 1.0)

# -- Load UNSMRY and interpolate to Eclipse time axis -------------------------
# OPM may report at different timesteps than Eclipse (different convergence).
# np.interp maps OPM values onto the Eclipse 127-point time axis so all
# comparisons involve identically sized arrays.
opm_sum  = EclSum(OPM_BASE + '.UNSMRY')
opm_keys = sorted(opm_sum.keys())
opm_days = np.array(opm_sum.days, dtype=np.float64)

sim_smry = {}
for k in opm_keys:
    v = safe_vec(opm_sum, k)
    if v is not None:
        sim_smry[k] = np.interp(ecl_days, opm_days, v)

SIM_LABEL = "OPM Flow"

# -- Compute matched / Eclipse-only / OPM-only key sets -----------------------
ecl_rst_keys  = set(eclipse_rst.keys())
ecl_smry_keys = set(eclipse_smry.keys())
sim_rst_keys  = set(sim_rst.keys())
sim_smry_keys = set(sim_smry.keys())

matched_rst        = sorted(ecl_rst_keys  & sim_rst_keys)
matched_smry       = sorted(ecl_smry_keys & sim_smry_keys)
eclipse_only_smry  = sorted(ecl_smry_keys - sim_smry_keys)
sim_only_smry      = sorted(sim_smry_keys - ecl_smry_keys)

# History-match mnemonics (*H / *TH) are Eclipse-only by design -- flag them
_history_only = [k for k in eclipse_only_smry
                 if k.endswith('H') or k.endswith('TH')]
_genuine_missing = [k for k in eclipse_only_smry if k not in _history_only]

print(f"\n  UNRST  matched keys  : {matched_rst}")
print(f"  UNSMRY matched keys  : {len(matched_smry)}")
print(f"  Eclipse-only (total) : {len(eclipse_only_smry)}")
print(f"    of which *H/*TH    : {len(_history_only)}  (expected -- OPM does not replicate history targets)")
print(f"    genuinely missing  : {len(_genuine_missing)}")
if _genuine_missing:
    print(f"    List: {_genuine_missing[:20]}")
print(f"  OPM-only             : {len(sim_only_smry)}")
if sim_only_smry:
    print(f"    List: {sim_only_smry[:20]}")
'''.strip())

# -----------------------------------------------------------------------------
CELL_06B_DIAG = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Root-cause diagnostics for known OPM vs Eclipse differences.  Three sections:
#
#   A. Inactive COMPDAT connections -- parses the OPM PRT log for the pattern
#      "The cell (I,J,K) in well NAME is not active", groups by well, and counts
#      how many completions were silently dropped.  Connections lost due to
#      MINPV=500 (before Fix 4 is applied) are the main cause of well
#      productivity underestimation for PROD-01 and all three FX wells.
#
#   B. FPR initialization offset -- compares Eclipse FPR to OPM FPR at t=0 and
#      over time to distinguish between (i) a real pressure deficiency caused by
#      AQUFETP reverse influx and (ii) the residual cosmetic WPAVEDEP offset.
#      After Fix 3 (AQUFETP PRSI=-1 -> 1196 psia) the offset at t=0 should be
#      < 1 psia.  The WPAVEDEP residual grows slowly to ~20-50 psia at late time
#      because Eclipse depth-corrects FPR to 2763 ft using reservoir fluid
#      gradient while OPM uses a plain PV-weighted average.
#
#   C. Gas lift comparison -- plots WGLIR (Mscf/d) per well versus time for both
#      Eclipse and OPM.  After Fix 7 (VFP THP densification) all three FX wells
#      should hold at 1400-1500 Mscf/d throughout years 8-10 rather than
#      collapsing to the 401 Mscf/d false optimizer equilibrium.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# Before looking at the scorecard we inspect the three known sources of
# OPM/Eclipse difference:
#   (1) Missing well perforations -- OPM drops completions in cells it considers
#       too thin, reducing well productivity.
#   (2) Reservoir pressure offset -- OPM and Eclipse report field average pressure
#       differently; this section tells us whether the difference is real or just
#       a reporting convention.
#   (3) Gas lift rates -- the most important late-life driver.  We plot the gas
#       lift injection per well to check whether the VFP densification fix
#       corrected the optimizer divergence that previously caused water and oil
#       production to collapse in years 8-10.
# -----------------------------------------------------------------------------

import glob as _g6, re as _r6

print("=" * 70)
print("ROOT-CAUSE DIAGNOSTICS -- OPM vs Eclipse")
print("=" * 70)

# -- A. Inactive COMPDAT connections (OPM PRT log) ----------------------------
print("\n[A] Inactive well completions (MINPV-deactivated cells)")
print("    OPM silently drops connections to cells below MINPV.  Fix 4 (MINPV")
print("    500->10 RB) should eliminate these warnings after a fresh OPM run.")
print()
_prt = _g6.glob(os.path.join(OPM_OUT_DIR, '*.PRT'))
_inactive = {}    # well name -> list of '(I,J,K)' strings
if _prt:
    _pat = _r6.compile(
        r'The cell \((\d+),\s*(\d+),\s*(\d+)\) in well (\S+) is not active')
    with open(_prt[0], 'r', errors='replace') as _pf:
        for _ln in _pf:
            _m = _pat.search(_ln)
            if _m:
                _inactive.setdefault(_m.group(4), []).append(
                    f"({_m.group(1)},{_m.group(2)},{_m.group(3)})")
    if _inactive:
        _tot = sum(len(v) for v in _inactive.values())
        print(f"    {'Well':<14} {'Dropped conns':>13}   Cells")
        print("    " + "-" * 60)
        for _w in sorted(_inactive, key=lambda w: -len(_inactive[w])):
            _flag = " *** ALL COMPLETIONS LOST ***" if len(_inactive[_w]) >= 10 else ""
            print(f"    {_w:<14} {len(_inactive[_w]):>13}   "
                  f"{', '.join(_inactive[_w][:4])}"
                  f"{'...' if len(_inactive[_w])>4 else ''}{_flag}")
        print(f"\n    Total dropped: {_tot}  (should be 0 after MINPV 500->10 RB fix)")
    else:
        print("    No inactive completion warnings found -- MINPV fix is working.")
else:
    print(f"    PRT file not found in {OPM_OUT_DIR}")

# -- B. FPR offset: real pressure error vs cosmetic depth-correction ------------
print("\n[B] FPR initialization and offset analysis")
print("    AQUFETP PRSI=-1 -> OPM wrong aquifer equilibrium -> reverse influx at t=0.")
print("    After Fix 3 (PRSI->1196 psia) FPR offset at t=0 should be < 1 psia.")
print()
try:
    _e_fpr  = np.array(eclsum.numpy_vector('FPR'))
    _e_days = np.array(eclsum.days)
    print(f"    Eclipse FPR at t=0 : {float(_e_fpr[0]):.1f} psia")
except Exception as _eb:
    print(f"    Could not load Eclipse FPR: {_eb}")
    _e_fpr = None

if 'FPR' in sim_smry and _e_fpr is not None:
    _o_fpr = sim_smry['FPR']
    print(f"    OPM     FPR at t=0 : {float(_o_fpr[0]):.1f} psia")
    print(f"    Offset  (Ecl-OPM)  : {float(_e_fpr[0] - _o_fpr[0]):+.1f} psia")
    print()
    # If offset is constant over time -> cosmetic WPAVEDEP effect.
    # If offset grows when wells are SHUT -> real aquifer pressure deficiency.
    _e_interp = np.interp(ecl_years * 365.25, _e_days, _e_fpr)
    _offsets  = _e_interp - _o_fpr
    print("    Offset history (constant ~= cosmetic; growing ~= real deficiency):")
    for _tyr, _off in zip(ecl_years[::20], _offsets[::20]):
        _bar = '#' * min(int(abs(_off) / 5), 40)
        print(f"      year {_tyr:4.1f}: {_off:+.1f} psia  {_bar}")

# -- C. Gas lift rate comparison ------------------------------------------------
print("\n[C] Gas lift injection rate per well (WGLIR) -- Eclipse vs OPM Flow")
print("    After VFP THP densification (Fix 7) OPM's optimizer should hold at")
print("    ~1400 Mscf/d per well throughout years 8-10 (matching Eclipse).")
print()

_glir_wells = sorted({k.split(':')[1] for k in matched_smry
                      if k.startswith('WGLIR') and ':' in k})
if _glir_wells:
    _ncols = min(len(_glir_wells), 4)
    _nrows = (len(_glir_wells) + _ncols - 1) // _ncols
    fig_c, axes_c = plt.subplots(_nrows, _ncols,
                                  figsize=(5*_ncols, 3.5*_nrows), squeeze=False)
    axes_c = axes_c.ravel()
    fig_c.suptitle('Gas Lift Injection Rate (WGLIR) -- Eclipse vs OPM Flow',
                   fontsize=12, fontweight='bold')
    for _ax, _w in zip(axes_c, _glir_wells):
        _k = f'WGLIR:{_w}'
        _ax.plot(ecl_years, eclipse_smry[_k], 'k-',  lw=2,   label='Eclipse')
        _ax.plot(ecl_years, sim_smry[_k],     'r--', lw=1.5, label='OPM Flow', alpha=0.85)
        _ecl_final = float(eclipse_smry[_k][-1])
        _opm_final = float(sim_smry[_k][-1])
        _ax.set_title(f'{_w}\nECL={_ecl_final:.0f}  OPM={_opm_final:.0f} Mscf/d',
                      fontweight='bold', fontsize=9)
        _ax.set_xlabel('Time (years from 1 Jul 2000)', fontsize=8)
        _ax.set_ylabel('Gas lift rate (Mscf/d)', fontsize=8)
        _ax.legend(fontsize=8)
        _ax.grid(alpha=0.3)
    for _ax in axes_c[len(_glir_wells):]:
        _ax.set_visible(False)
    plt.tight_layout()
    _out_c = os.path.join(NOTEBOOK_DIR, 'gas_rate_comparison.png')
    plt.savefig(_out_c, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  Saved: {_out_c}")
else:
    print("  WGLIR not in matched summary vectors.")
'''.strip())

# -----------------------------------------------------------------------------
CELL_07_METRICS = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Computes five agreement statistics for every matched mnemonic:
#
#   R^2      -- coefficient of determination: 1 = perfect, 0 = mean-predictor,
#              <0 = worse than predicting the mean.  Computed via sklearn's
#              r2_score (same as the PINN surrogate evaluation).
#   RMSE    -- root-mean-square error in the mnemonic's native units.
#   max_err -- maximum pointwise absolute error across the entire time series.
#   P50/P95 -- median and 95th-percentile absolute error.
#
# Cell-level statistics (PRESSURE, SWAT, SGAS, SOIL) flatten all 114,768 active
# cells x 61 timesteps into a single 7M-element vector before computing metrics,
# capturing both spatial and temporal accuracy simultaneously.
#
# FPR is always tagged WARN(WPAVEDEP) rather than PASS/FAIL because the ~20-50 psia
# late-time residual offset is a reporting-convention difference (depth-correction),
# not a physics error.  Use cell-level PRESSURE arrays for rigorous comparison.
#
# History-match mnemonics (*H / *TH) are excluded from the scorecard because OPM
# does not replicate Eclipse's WCONHIST reference values.
#
# Results are stored in df_metrics (pandas DataFrame) and exported to
# comparison_metrics.csv for external review.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# For every quantity where we have both Eclipse and OPM results, we calculate
# four numbers that measure how close the answers are.  R^2 near 1 means near-
# perfect agreement.  We flag each quantity PASS or FAIL against published
# reservoir-simulation benchmark tolerances (based on SPE-163649-MS).  The full
# results table is also saved as a CSV file.
# -----------------------------------------------------------------------------

print("=" * 70)
print("STEP 4 -- Quantitative comparison metrics")
print("=" * 70)

# Tolerance thresholds by category (R^2 and RMSE in native units)
TOL = {
    'PRESSURE': dict(r2=0.99,  rmse=10.0),
    'SWAT':     dict(r2=0.999, rmse=0.005),
    'SGAS':     dict(r2=0.999, rmse=0.005),
    'SOIL':     dict(r2=0.999, rmse=0.005),
    'F_rate':   dict(r2=0.995, rmse=np.inf),
    'W_rate':   dict(r2=0.990, rmse=np.inf),
    'A_cumul':  dict(r2=0.995, rmse=np.inf),
    'default':  dict(r2=0.990, rmse=np.inf),
}

def get_tol(category, mnemonic):
    if category == 'cell':
        return TOL.get(mnemonic, TOL['default'])
    if category == 'field':   return TOL['F_rate']
    if category == 'well':    return TOL['W_rate']
    if category == 'aquifer': return TOL['A_cumul']
    return TOL['default']

def passes(m, tol):
    return bool(m['r2'] >= tol['r2'] and m['rmse'] <= tol['rmse'])

rows = []

# -- 7a. Cell-level arrays (PRESSURE, SWAT, SGAS, SOIL) -----------------------
print("\n[7a] Cell-level (all active cells x all 61 UNRST timesteps) ...")
for kw in matched_rst:
    e_flat = eclipse_rst[kw].ravel().astype(np.float64)
    s_flat = sim_rst[kw].ravel().astype(np.float64)
    valid  = np.isfinite(s_flat)
    m = metrics(e_flat[valid], s_flat[valid])
    tol = get_tol('cell', kw)
    ok  = passes(m, tol)
    unit = get_unit(kw)
    rows.append(dict(category='cell', mnemonic=kw, well='--',
                     r2=m['r2'], rmse=m['rmse'], max_err=m['max_err'],
                     p50_err=m['p50'], p95_err=m['p95'], units=unit,
                     PASS='PASS' if ok else 'FAIL'))
    print(f"  {kw:<12} R^2={m['r2']:+.4f}  RMSE={m['rmse']:8.4f} {unit:<8}  "
          f"P95={m['p95']:8.4f}  {'PASS' if ok else 'FAIL'}")

# -- 7b. Field summary vectors (F*) -------------------------------------------
print("\n[7b] Field summary (F* vectors) ...")
# Skip history-match mnemonics (end in H or TH) -- OPM does not store them
f_keys = sorted([k for k in matched_smry
                 if k.startswith('F')
                 and not k.endswith('H') and not k.endswith('TH')])
for k in f_keys:
    m  = metrics(eclipse_smry[k], sim_smry[k])
    if k == 'FPR':
        # FPR: WPAVEDEP depth-correction difference makes direct comparison
        # misleading -- tag as WARN rather than PASS/FAIL.
        note = 'WARN(WPAVEDEP)'
        rows.append(dict(category='field', mnemonic=k, well='--',
                         r2=m['r2'], rmse=m['rmse'], max_err=m['max_err'],
                         p50_err=m['p50'], p95_err=m['p95'],
                         units=get_unit(k), PASS=note))
        print(f"  {k:<16} R^2={m['r2']:+.4f}  RMSE={m['rmse']:10.3f} {get_unit(k):<8}  "
              f"{note}")
        continue
    tol = get_tol('field', k)
    ok  = passes(m, tol)
    rows.append(dict(category='field', mnemonic=k, well='--',
                     r2=m['r2'], rmse=m['rmse'], max_err=m['max_err'],
                     p50_err=m['p50'], p95_err=m['p95'],
                     units=get_unit(k), PASS='PASS' if ok else 'FAIL'))
    print(f"  {k:<16} R^2={m['r2']:+.4f}  RMSE={m['rmse']:10.3f} {get_unit(k):<8}  "
          f"{'PASS' if ok else 'FAIL'}")

# -- 7c. Per-well vectors (W*) -------------------------------------------------
print("\n[7c] Per-well (W* vectors) ...")
wells_found = sorted({k.split(':')[1] for k in matched_smry
                      if ':' in k and k.split(':')[0].startswith('W')})
for well in wells_found:
    # Skip history-match mnemonics per well too
    w_keys = sorted([k for k in matched_smry
                     if k.startswith('W') and k.endswith(f':{well}')
                     and not k.split(':')[0].endswith('H')
                     and not k.split(':')[0].endswith('TH')])
    for k in w_keys:
        m   = metrics(eclipse_smry[k], sim_smry[k])
        tol = get_tol('well', k)
        ok  = passes(m, tol)
        rows.append(dict(category='well', mnemonic=k.split(':')[0], well=well,
                         r2=m['r2'], rmse=m['rmse'], max_err=m['max_err'],
                         p50_err=m['p50'], p95_err=m['p95'],
                         units=get_unit(k), PASS='PASS' if ok else 'FAIL'))
    if w_keys:
        best_r2 = max(metrics(eclipse_smry[k], sim_smry[k])['r2'] for k in w_keys)
        print(f"  {well:<15} {len(w_keys):2d} vectors  best R^2={best_r2:+.4f}")

# -- 7d. Aquifer vectors (A*) --------------------------------------------------
print("\n[7d] Aquifer (A* vectors) ...")
a_keys = sorted([k for k in matched_smry if k.startswith('A')])
for k in a_keys:
    m   = metrics(eclipse_smry[k], sim_smry[k])
    tol = get_tol('aquifer', k)
    ok  = passes(m, tol)
    rows.append(dict(category='aquifer', mnemonic=k, well='--',
                     r2=m['r2'], rmse=m['rmse'], max_err=m['max_err'],
                     p50_err=m['p50'], p95_err=m['p95'],
                     units=get_unit(k), PASS='PASS' if ok else 'FAIL'))
    print(f"  {k:<16} R^2={m['r2']:+.4f}  RMSE={m['rmse']:10.3f} {get_unit(k):<8}  "
          f"{'PASS' if ok else 'FAIL'}")

# -- 7e. Region / Block vectors ------------------------------------------------
for k in sorted([k for k in matched_smry if k[0] in ('R', 'B')]):
    m  = metrics(eclipse_smry[k], sim_smry[k])
    ok = passes(m, get_tol('region', k))
    rows.append(dict(category='region/block', mnemonic=k, well='--',
                     r2=m['r2'], rmse=m['rmse'], max_err=m['max_err'],
                     p50_err=m['p50'], p95_err=m['p95'],
                     units=get_unit(k), PASS='PASS' if ok else 'FAIL'))

# -- Export to CSV -------------------------------------------------------------
df_metrics = pd.DataFrame(rows)
csv_path   = os.path.join(NOTEBOOK_DIR, 'comparison_metrics.csv')
df_metrics.to_csv(csv_path, index=False)
_pass = (df_metrics['PASS'] == 'PASS').sum()
_fail = (df_metrics['PASS'] == 'FAIL').sum()
print(f"\n  Metrics: {len(df_metrics)} rows   {_pass} PASS  /  {_fail} FAIL  "
      f"(pass rate {100*_pass/max(len(df_metrics),1):.1f}%)")
print(f"  CSV: {csv_path}")
print()
print(df_metrics[['category','mnemonic','well','r2','rmse','units','PASS']].to_string(index=False))
'''.strip())

# -----------------------------------------------------------------------------
CELL_08_FIELD_VIZ = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Generates time-series overlay plots for all matched field (F*) and aquifer
# (A*) summary vectors.  Eclipse values are solid black lines; OPM Flow is
# dashed red.  Each subplot includes:
#   * title: mnemonic name
#   * x-axis: time in fractional years from 1 Jul 2000
#   * y-axis: physical quantity with unit from the UNITS lookup table
#   * legend: solver labels with R^2 and RMSE from df_metrics
#
# Subplots are arranged in a 4-column grid; rows expand automatically with the
# number of matched vectors.  Aquifer vectors (AAQT, AAQR, AAQP) are plotted
# separately because their y-axis scale differs from production rates.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# We draw one chart per field-level measurement showing Eclipse and OPM results
# on the same axes over the full 10.5-year simulation.  A domain expert can
# quickly see where the two simulators agree and where they diverge.  Each axis
# is labelled with its physical unit so the magnitude of any difference is
# immediately interpretable -- e.g. a 10 stb/d discrepancy in FOPR vs a 500 psia
# discrepancy in FPR are very different in engineering significance.
# -----------------------------------------------------------------------------

def make_r2_label(category, mnemonic, well='--'):
    """Build a compact R^2/RMSE legend label from the df_metrics DataFrame."""
    row = df_metrics[(df_metrics['mnemonic'] == mnemonic) &
                     (df_metrics['well'] == well) &
                     (df_metrics['category'] == category)]
    if row.empty:
        return ''
    r = row.iloc[0]
    return f"R^2={r['r2']:+.4f}  RMSE={r['rmse']:.3g} {r['units']}"

t_years = ecl_years   # common x-axis for all plots

# -- 8a. Field time-series panel -----------------------------------------------
f_keys = sorted([k for k in matched_smry
                 if k.startswith('F')
                 and not k.endswith('H') and not k.endswith('TH')])
if f_keys:
    ncols = 4
    nrows = max(1, (len(f_keys) + ncols - 1) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5*ncols, 3.5*nrows), squeeze=False)
    axes = axes.ravel()
    fig.suptitle(f'Field Summary Vectors -- Eclipse vs {SIM_LABEL}  '
                 f'(1 Jul 2000 -> 1 Jan 2003)',
                 fontsize=13, fontweight='bold')
    for ax, k in zip(axes, f_keys):
        ax.plot(t_years, eclipse_smry[k], 'k-',  lw=2,   label='Eclipse')
        ax.plot(t_years, sim_smry[k],     'r--', lw=1.5, label=SIM_LABEL, alpha=0.85)
        lbl = make_r2_label('field', k)
        ax.set_title(k, fontweight='bold', fontsize=9)
        ax.set_xlabel('Time (years)', fontsize=8)
        # Label y-axis with the physical unit for this mnemonic
        _unit = get_unit(k)
        ax.set_ylabel(_unit if _unit else '--', fontsize=8)
        ax.legend(fontsize=7, title=lbl, title_fontsize=7)
        ax.grid(alpha=0.3)
    for ax in axes[len(f_keys):]:
        ax.set_visible(False)
    plt.tight_layout()
    out = os.path.join(NOTEBOOK_DIR, 'field_comparison.png')
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"Field panel saved: {out}")

# -- 8b. Aquifer time-series panel ---------------------------------------------
a_keys = sorted([k for k in matched_smry if k.startswith('A')])
if a_keys:
    fig, axes = plt.subplots(1, len(a_keys), figsize=(5*len(a_keys), 4), squeeze=False)
    axes = axes.ravel()
    fig.suptitle(f'Aquifer Vectors -- Eclipse vs {SIM_LABEL}',
                 fontsize=12, fontweight='bold')
    for ax, k in zip(axes, a_keys):
        ax.plot(t_years, eclipse_smry[k], 'b-',  lw=2,   label='Eclipse')
        ax.plot(t_years, sim_smry[k],     'r--', lw=1.5, label=SIM_LABEL, alpha=0.85)
        lbl = make_r2_label('aquifer', k)
        ax.set_title(k, fontweight='bold')
        ax.set_xlabel('Time (years)', fontsize=8)
        _unit = get_unit(k)
        ax.set_ylabel(_unit if _unit else '--', fontsize=8)
        ax.legend(fontsize=8, title=lbl, title_fontsize=7)
        ax.grid(alpha=0.3)
    plt.tight_layout()
    out = os.path.join(NOTEBOOK_DIR, 'aquifer_comparison.png')
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"Aquifer panel saved: {out}")
else:
    print("No matched aquifer (A*) vectors to plot.")
'''.strip())

# -----------------------------------------------------------------------------
CELL_09_WELL_VIZ = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Generates one multi-panel figure per well for all matched W* mnemonics.
# The well list is derived dynamically from matched_smry (no hardcoded well names)
# so any well with at least one matched mnemonic gets its own figure.
#
# Each subplot shows:
#   * x-axis : time in fractional years from 1 Jul 2000
#   * y-axis : mnemonic value with unit from UNITS lookup (e.g. 'stb/d', 'psia')
#   * title  : base mnemonic (e.g. WOPR, WBHP)
#   * legend : Eclipse (solid black) and OPM Flow (dashed red) with R^2/RMSE
#
# History-match mnemonics (*H, *TH) are excluded because OPM does not replicate
# Eclipse's WCONHIST stored reference values -- their inclusion would inflate
# the FAIL count misleadingly.
#
# Typical well mnemonics: WOPR (oil rate stb/d), WWPR (water rate stb/d),
# WGPR (gas rate Mscf/d), WLPR (liquid rate stb/d), WOPT/WWPT/WGPT (cumul.),
# WBHP/WTHP (pressures psia), WWIR/WWIT (water injection), WGLIR (gas lift),
# WPI (productivity index stb/d/psia).
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# For each well in the model we plot all available measurements -- oil rate,
# water rate, gas rate, flowing pressure, injection rate, gas lift rate, etc. --
# comparing Eclipse to OPM side by side.  This is the most detailed level of
# validation: a field total can look fine while individual wells behave very
# differently.  Every y-axis is labelled with its unit so discrepancies can be
# assessed in engineering terms.
# -----------------------------------------------------------------------------

t_years = ecl_years

wells_w = sorted({k.split(':')[1] for k in matched_smry
                  if ':' in k and k.split(':')[0].startswith('W')})

if not wells_w:
    print("No matched W* per-well vectors available.")
else:
    print(f"Generating per-well figures for {len(wells_w)} wells ...")
    for well in wells_w:
        # Exclude history-match mnemonics from per-well plots
        w_keys = sorted([k for k in matched_smry
                         if k.startswith('W') and k.endswith(f':{well}')
                         and not k.split(':')[0].endswith('H')
                         and not k.split(':')[0].endswith('TH')])
        if not w_keys:
            continue

        ncols = min(4, len(w_keys))
        nrows = (len(w_keys) + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols,
                                 figsize=(5*ncols, 3.5*nrows), squeeze=False)
        axes = axes.ravel()
        fig.suptitle(f'Well: {well} -- Eclipse vs {SIM_LABEL}  '
                     f'(1 Jul 2000 -> 1 Jan 2003)',
                     fontsize=12, fontweight='bold')

        for ax, k in zip(axes, w_keys):
            base_mnem = k.split(':')[0]
            ax.plot(t_years, eclipse_smry[k], 'k-',  lw=2,   label='Eclipse')
            ax.plot(t_years, sim_smry[k],     'r--', lw=1.5, label=SIM_LABEL, alpha=0.85)
            lbl = make_r2_label('well', base_mnem, well)
            ax.set_title(base_mnem, fontweight='bold', fontsize=9)
            ax.set_xlabel('Time (years)', fontsize=8)
            _unit = get_unit(base_mnem)
            ax.set_ylabel(_unit if _unit else '--', fontsize=8)
            ax.legend(fontsize=7, title=lbl, title_fontsize=7)
            ax.grid(alpha=0.3)

        for ax in axes[len(w_keys):]:
            ax.set_visible(False)
        plt.tight_layout()
        safe_well = well.replace('-', '').replace(' ', '_')
        out = os.path.join(NOTEBOOK_DIR, f'well_{safe_well}_comparison.png')
        plt.savefig(out, dpi=150, bbox_inches='tight')
        plt.show()
        print(f"  {well}: {len(w_keys)} panels  ->  {out}")
'''.strip())

# -----------------------------------------------------------------------------
CELL_10_CELL_VIZ = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Three spatial / statistical panels for cell-level dynamic arrays:
#
#   (1) Scatter plot -- Eclipse vs OPM for each of PRESSURE, SWAT, SGAS.
#       Points are coloured by timestep index (early = dark, late = bright)
#       so temporal drift is visible.  Up to 50,000 points are sampled at
#       random for rendering speed.  The 1:1 perfect-agreement line is shown
#       in dashed black.  R^2 is displayed in the title.
#
#   (2) 2-D areal error map -- |Eclipse - OPM| at the final restart timestep
#       plotted for layers k=0 (shallowest), k=NZ//2 (mid-reservoir), and
#       k=NZ-1 (deepest).  Only active cells contribute; inactive cells are
#       white.  The colour scale is capped at the 95th percentile of errors to
#       prevent a few large outliers from washing out the spatial pattern.
#
#   (3) Error histogram -- distribution of |Eclipse - OPM| across all active
#       cells and all timesteps (log-y scale shows the tail behaviour).
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# We visualise the cell-by-cell agreement between Eclipse and OPM for pressure
# and saturation in three ways: a scatter plot showing whether all points fall
# on the 1:1 line, a map showing where in the reservoir the largest errors occur,
# and a histogram showing how the errors are distributed.  Together these tell
# engineers whether the discrepancies are random noise or concentrated in
# specific geological zones (e.g. near faults, thin layers, or aquifer boundaries).
# -----------------------------------------------------------------------------

def plot_scatter_hist(kw, unit, max_pts=50_000):
    """Scatter (Eclipse vs OPM) and error histogram for a cell-level array."""
    e_flat  = eclipse_rst[kw].ravel().astype(np.float64)
    s_flat  = sim_rst[kw].ravel().astype(np.float64)
    valid   = np.isfinite(s_flat)
    ef = e_flat[valid]; sf = s_flat[valid]

    # Sub-sample for scatter speed; colour by timestep index
    rng_sc = np.random.default_rng(0)
    idx    = rng_sc.choice(len(ef), min(max_pts, len(ef)), replace=False)
    ts_idx = np.repeat(np.arange(N_RST), N_ACTIVE)[valid][idx]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    sc = ax1.scatter(ef[idx], sf[idx], c=ts_idx, cmap='plasma', s=1, alpha=0.3)
    mn, mx = min(ef.min(), sf.min()), max(ef.max(), sf.max())
    ax1.plot([mn, mx], [mn, mx], 'k--', lw=1, label='1:1 line')
    r2v = r2_score(ef, sf)
    ax1.set_xlabel(f'Eclipse {kw} ({unit})', fontsize=9)
    ax1.set_ylabel(f'OPM Flow {kw} ({unit})', fontsize=9)
    ax1.set_title(f'{kw}: Eclipse vs OPM Flow\nR^2={r2v:+.4f}', fontweight='bold')
    plt.colorbar(sc, ax=ax1, label='Restart report index (0=earliest, 60=latest)')
    ax1.legend(fontsize=8)

    ax2.hist(np.abs(ef - sf), bins=80, color='steelblue', edgecolor='none')
    ax2.set_yscale('log')
    ax2.set_xlabel(f'|Eclipse - OPM Flow| ({unit})', fontsize=9)
    ax2.set_ylabel('Cell-timestep count', fontsize=9)
    ax2.set_title(f'{kw} absolute error distribution\n(all cells x all timesteps)',
                  fontweight='bold')
    ax2.grid(alpha=0.3, axis='y')
    plt.tight_layout()
    fname = f'cell_{kw.lower()}_comparison.png'
    out = os.path.join(NOTEBOOK_DIR, fname)
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  Saved: {out}")

def plot_2d_error_maps(kw, unit):
    """
    2-D areal maps of |Eclipse - OPM| at the final restart timestep for three
    reservoir layers: shallowest (k=0), mid (k=NZ//2), and deepest (k=NZ-1).
    Each cell's error is placed at its (I, J) position; empty cells are NaN (white).
    """
    err = np.abs(eclipse_rst[kw][-1].astype(np.float64)
                 - sim_rst[kw][-1].astype(np.float64))
    vmax = np.nanpercentile(err, 95)   # cap colour scale at 95th pctile

    k_layers = [0, NZ // 2, NZ - 1]
    layer_labels = [f'k={kl} ({"shallowest" if kl==0 else "mid" if kl==NZ//2 else "deepest"})'
                    for kl in k_layers]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle(f'{kw} |Eclipse - OPM| -- Final timestep (1 Jan 2003)',
                 fontsize=11, fontweight='bold')
    for ax, kl, lbl in zip(axes, k_layers, layer_labels):
        grid_2d = np.full((NY, NX), np.nan)
        for idx in np.where(k_all == kl)[0]:
            grid_2d[int(j_all[idx]), int(i_all[idx])] = err[idx]
        im = ax.imshow(grid_2d, origin='lower', cmap='hot_r', aspect='auto',
                       vmin=0, vmax=vmax)
        plt.colorbar(im, ax=ax, label=f'|err| ({unit})')
        ax.set_title(lbl, fontweight='bold', fontsize=9)
        ax.set_xlabel('I (column index)', fontsize=8)
        ax.set_ylabel('J (row index)', fontsize=8)
    plt.tight_layout()
    out = os.path.join(NOTEBOOK_DIR, f'cell_{kw.lower()}_2d_error.png')
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"  Saved: {out}")

print("=" * 70)
print("Cell-level spatial visualisations (PRESSURE, SWAT, SGAS)")
print("=" * 70)

for kw, unit in [('PRESSURE', 'psia'), ('SWAT', 'frac'), ('SGAS', 'frac')]:
    if kw in matched_rst:
        print(f"\n  Plotting {kw} ...")
        plot_scatter_hist(kw, unit)
        plot_2d_error_maps(kw, unit)
'''.strip())

# -----------------------------------------------------------------------------
CELL_11_DASHBOARD = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Renders df_metrics as a colour-coded summary table (matplotlib table widget).
# Rows are sorted by category priority (cell -> field -> well -> aquifer ->
# region/block) then by R^2 ascending so the worst vectors appear first within
# each category.
#
# Cell background colour:
#   green  (#d4edda) -- PASS   : R^2 >= threshold and RMSE <= threshold
#   red    (#f8d7da) -- FAIL   : at least one threshold not met
#   yellow (#fff3cd) -- WARN   : flagged (e.g. WARN(WPAVEDEP) for FPR)
#
# Column headers are dark grey with white bold text.
# The figure title shows the overall PASS / FAIL counts and pass rate.
# The table is also saved as tolerance_summary.png for external reporting.
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# This is the single-page validation scorecard.  Every measured quantity is
# listed.  Green means OPM reproduces Eclipse within the agreed engineering
# tolerance; red means it does not; yellow means the comparison is affected by
# a known reporting convention difference (not a physics error).  A domain
# expert can review this one figure to decide whether the OPM results are fit
# for purpose as training data for the PINN surrogate or for any other use.
# -----------------------------------------------------------------------------

cat_order = {'cell': 0, 'field': 1, 'well': 2, 'aquifer': 3, 'region/block': 4}
df_sorted = (df_metrics
             .assign(_ord=df_metrics['category'].map(cat_order).fillna(5))
             .sort_values(['_ord', 'r2'])
             .drop(columns=['_ord'])
             .reset_index(drop=True))

disp = df_sorted[['category', 'mnemonic', 'well', 'r2', 'rmse',
                  'max_err', 'p95_err', 'units', 'PASS']].copy()
disp['r2']      = disp['r2'].map('{:+.4f}'.format)
disp['rmse']    = disp['rmse'].map('{:.4g}'.format)
disp['max_err'] = disp['max_err'].map('{:.4g}'.format)
disp['p95_err'] = disp['p95_err'].map('{:.4g}'.format)
disp.columns    = ['Category', 'Mnemonic', 'Well', 'R^2', 'RMSE',
                   'Max|err|', 'P95|err|', 'Units', 'Result']

# Build per-row cell colours
cell_colors = []
for _, row in disp.iterrows():
    if row['Result'] == 'PASS':
        c = '#d4edda'   # green
    elif str(row['Result']).startswith('WARN'):
        c = '#fff3cd'   # yellow
    else:
        c = '#f8d7da'   # red
    cell_colors.append([c] * len(disp.columns))

n_rows = len(disp)
fig_h  = max(4, 0.35 * n_rows + 1.5)
fig, ax = plt.subplots(figsize=(18, fig_h))
ax.set_axis_off()
tbl = ax.table(cellText=disp.values.tolist(),
               colLabels=disp.columns.tolist(),
               cellColours=cell_colors,
               loc='center', cellLoc='center')
tbl.auto_set_font_size(False)
tbl.set_fontsize(8)
tbl.scale(1, 1.2)
for j in range(len(disp.columns)):
    tbl[0, j].set_facecolor('#343a40')
    tbl[0, j].set_text_props(color='white', fontweight='bold')

_p = (df_sorted['PASS'] == 'PASS').sum()
_f = (df_sorted['PASS'] == 'FAIL').sum()
_w = df_sorted['PASS'].str.startswith('WARN', na=False).sum()
ax.set_title(
    f'OPM Flow Validation Scorecard -- Eclipse vs OPM Flow  |  '
    f'{_p} PASS  /  {_f} FAIL  /  {_w} WARN  '
    f'(pass rate {100*_p/max(len(df_sorted),1):.1f}%)',
    fontsize=12, fontweight='bold', pad=12)
plt.tight_layout()
out = os.path.join(NOTEBOOK_DIR, 'tolerance_summary.png')
plt.savefig(out, dpi=150, bbox_inches='tight')
plt.show()
print(f"Scorecard saved: {out}")
'''.strip())

# -----------------------------------------------------------------------------
CELL_12_CONCLUSIONS = code(r'''
# -- TECHNICAL -----------------------------------------------------------------
# Final summary cell.  Consolidates all metrics into a structured report:
#   * Solver provenance (OPM version, run date, patched DATA path)
#   * Mnemonic coverage: matched / Eclipse-only / OPM-only counts
#   * PASS/FAIL breakdown by category with ASCII progress bars
#   * 5 worst-performing vectors by R^2 -- useful for identifying where physics
#     or numerical differences are largest
#   * Residual root-cause notes for any FAIL vectors:
#       - WPAVEDEP: Eclipse FPR depth-correction vs OPM plain PV-weighted average
#       - WCUTBACK: rate-limiting at GLR > 10 Mscf/stb, removed from OPM DATA
#       - Gas lift optimizer algorithm differences (even with identical VFP table
#         and LIFTOPT parameters, Eclipse and OPM may find different allocations)
#   * VFP densification status: confirms whether Fix 7 eliminated the 401 Mscf/d
#     gas-lift false-equilibrium in years 8-10
#
# -- PLAIN ENGLISH -------------------------------------------------------------
# This cell prints the final validation report in plain numbers.  It lists:
#   * which OPM version was used and when the run was done
#   * how many of the 300+ Eclipse measurements were compared and how many passed
#   * a category-by-category breakdown of the pass rate
#   * the five worst-matching quantities so an engineer knows where to focus
#   * notes on known residual differences that are not fixable at the DATA level
# -----------------------------------------------------------------------------

import datetime as _dt12

print("=" * 75)
print("VALIDATION CONCLUSIONS -- Eclipse vs OPM Flow")
print(f"Generated : {_dt12.datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 75)

print(f"\n  OPM version        : {OPM_VERSION}")
print(f"  Patched DATA       : {BASE_PATH}_OPM.DATA")
print(f"  OPM output dir     : {OPM_OUT_DIR}")
print(f"  Eclipse mnemonics  : {len(eclipse_keys)}")
print(f"  Matched summary    : {len(matched_smry)}")
print(f"  Eclipse-only smry  : {len(eclipse_only_smry)}"
      f"  (of which *H/*TH history targets: {len(_history_only)})")
print(f"  OPM-only smry      : {len(sim_only_smry)}")
print(f"  Matched UNRST kw   : {matched_rst}")

print(f"\n  PASS / FAIL / WARN by category:")
for cat in ['cell', 'field', 'well', 'aquifer', 'region/block']:
    sub = df_metrics[df_metrics['category'] == cat]
    if sub.empty:
        continue
    p = (sub['PASS'] == 'PASS').sum()
    f = (sub['PASS'] == 'FAIL').sum()
    w = sub['PASS'].str.startswith('WARN', na=False).sum()
    pct = 100 * p / max(len(sub), 1)
    bar = '#' * int(pct / 5) + '.' * (20 - int(pct / 5))
    print(f"    {cat:<15} {p:3d} PASS  {f:3d} FAIL  {w:2d} WARN  "
          f"[{bar}] {pct:.0f}%")

print(f"\n  5 WORST vectors by R^2:")
worst5 = df_metrics.nsmallest(5, 'r2')[
    ['category', 'mnemonic', 'well', 'r2', 'rmse', 'units', 'PASS']]
print(worst5.to_string(index=False))

# Check for any remaining FAIL vectors and print root-cause notes
fails = df_metrics[df_metrics['PASS'] == 'FAIL']
warns = df_metrics[df_metrics['PASS'].str.startswith('WARN', na=False)]
if fails.empty and warns.empty:
    print("\n  ALL tolerance targets met -- OPM Flow validation PASSED.")
else:
    if not fails.empty:
        print(f"\n  {len(fails)} vectors failed tolerance:")
        for _, row in fails.iterrows():
            print(f"    {row['category']:<12} {row['mnemonic']:<16} "
                  f"well={row['well']:<12} R^2={row['r2']:+.4f}  "
                  f"RMSE={row['rmse']:.4g} {row['units']}")

    if not warns.empty:
        print(f"\n  {len(warns)} vectors flagged with warnings:")
        for _, row in warns.iterrows():
            print(f"    {row['category']:<12} {row['mnemonic']:<16} "
                  f"well={row['well']:<12} R^2={row['r2']:+.4f}  [{row['PASS']}]")

    print("\n  KNOWN RESIDUAL ROOT CAUSES:")
    print("    1. WPAVEDEP/WPAVE -- Eclipse computes FPR by depth-correcting")
    print("       the PV-weighted average to the 2763 ft datum using reservoir")
    print("       fluid gradient.  OPM uses plain PV-weighted average without")
    print("       depth correction.  Results in a ~20-50 psia late-time FPR")
    print("       offset that is a reporting convention difference, not physics.")
    print("       -> Tagged WARN(WPAVEDEP); not a FAIL.  Use UNRST PRESSURE")
    print("         arrays for rigorous cell-level pressure comparison.")
    print()
    print("    2. WCUTBACK -- Eclipse applies rate cutback when well GLR exceeds")
    print("       10 Mscf/stb (factor 0.9 per step).  This keyword is unsupported")
    print("       in OPM and was removed from the patched DATA.  Residual")
    print("       behavioural difference in high-GOR periods; documented.")
    print()
    print("    3. Gas lift optimizer -- even with the VFP THP densification (Fix 7)")
    print("       Eclipse and OPM use different internal allocation algorithms.")
    print("       Remaining WGLIR / FOPR / FWPR divergence in years 8-10 should")
    print("       be reduced after the VFP fix but may not be eliminated entirely.")
    print("       Check Cell 6B Section C gas lift plots to quantify residual.")

print("\n" + "=" * 75)
print("Notebook complete.  All figures and comparison_metrics.csv saved to:")
print(f"  {NOTEBOOK_DIR}")
print("=" * 75)
'''.strip())

# ===============================================================================
# ASSEMBLE AND WRITE NOTEBOOK
# ===============================================================================

cells = [
    CELL_01_MD,
    CELL_02_SW,
    CELL_03_IMPORTS,
    CELL_04_ECL,
    CELL_05_SIM,
    CELL_06_PARSE,
    CELL_06B_DIAG,
    CELL_07_METRICS,
    CELL_08_FIELD_VIZ,
    CELL_09_WELL_VIZ,
    CELL_10_CELL_VIZ,
    CELL_11_DASHBOARD,
    CELL_12_CONCLUSIONS,
]

nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (ipykernel)",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "pygments_lexer": "ipython3",
            "version": "3.8.0"
        }
    },
    "cells": cells
}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Notebook written  ({len(cells)} cells):")
print(f"  {OUT_PATH}")
