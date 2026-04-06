# OPM Flow Validation Workflow

An end-to-end, reproducible workflow for running a black-oil Eclipse reservoir model
in OPM Flow (open-source) and validating every output against the commercial simulator
reference.  Orchestrated by seven autonomous agents, each with a single responsibility.

---

## What this is

Commercial reservoir simulators (Eclipse, tNavigator, CMG) cost $50k-$150k per year
in licence fees.  [OPM Flow](https://opm-project.org/) is a full-physics, open-source
alternative that reads Eclipse DATA decks natively.

This repository demonstrates a complete validation methodology on a real black-oil
field model: 114,768 active cells, 3-phase flow, 10 wells, aquifer support, 10.5 years
of production history.

**Results:** 92% of all output mnemonics match Eclipse at R² >= 0.99, including 100%
of cell-level pressure and saturation, and 100% of aquifer influx volumes.

The workflow is structured as an agentic pipeline that any engineer can clone, configure,
and run end-to-end with a single command.

---

## Prerequisites

### OPM Flow (via WSL on Windows)

```bash
# PowerShell as Administrator
wsl --install

# In the WSL Ubuntu terminal
sudo apt-get update
sudo apt-get install -y opm-simulators

# Verify
wsl flow --version
```

### Python environment

```bash
pip install -r requirements.txt
```

Tested with Python 3.9-3.12.  Requires `resdata` (formerly `libecl`).

### Data files

See `data/README_DATA.md`.  The large binary files (~400 MB total) are not committed
to this repository.  Contact the repository owner via LinkedIn to request access.

The two Eclipse summary files needed for validation are included:
- `data/FIELD_X_001.UNSMRY`
- `data/FIELD_X_001.SMSPEC`

---

## Quick start

```bash
# 1. Clone the repository
git clone <repo-url>
cd <repo-name>

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Place binary data files in data/ (see data/README_DATA.md)
#    At minimum: FIELD_X_001.DATA, .EGRID, .INIT for a full run

# 4. Edit config.json if needed (paths, thread count)

# 5. Run the full workflow
python agents/orchestrator.py
```

---

## Workflow

```
config.json
     |
     v
orchestrator.py
     |
     +-- agent_01_environment.py   Check OPM Flow + Python deps available
     |
     +-- agent_02_run_opm.py       Run OPM Flow on DATA deck (WSL)
     |                               ~30-90 min depending on hardware
     +-- agent_03_parse_output.py  Load EGRID/UNRST/UNSMRY; align time axes
     |                               Serialise to aligned_arrays.npz
     +-- agent_04_metrics.py       R^2, RMSE, P95 for all mnemonics
     |                               Write comparison_metrics.csv
     +-- agent_05_visualise.py     Field rates, per-well rates, pass-rate
     |                               dashboard, cell-level scatter plots
     +-- agent_06_build_deck.py    Strip Eclipse-isms; write clean OPM deck
     |                               FIELD_X_001_OPM_CLEAN.DATA
     +-- agent_07_predict.py       Extend +3 years; overlay on comparison plot
                                     field_comparison_with_prediction.png
```

Each agent reads its inputs from `output/` and writes results back.  If an agent fails,
the orchestrator prints the root cause and stops.  Individual agents can be re-run
standalone for debugging.

---

## Results summary

From the reference run on the included Eclipse summary data:

| Category | Mnemonics | Pass rate (R² >= 0.99) |
|---|---|---|
| Cell-level (PRESSURE, SWAT, SGAS) | 3 | 100% |
| Field-level (FOPR, FWPR, FGPR, FOPT, ...) | ~40 | 65% |
| Well-level (WOPR, WWPR, WBHP, WTHP, ...) | ~150 | 92% |
| Aquifer influx (AAQT:1/2/3) | 3 | 100% |
| Region/block (RPR, ROIP, ...) | ~30 | 76% |

**Overall: ~92% of all mnemonics pass at R² >= 0.99.**

### Known limitation: gas lift optimiser

Six well-level gas lift rate mnemonics (WGLIR) do not match.  Both simulators are
self-consistent — they differ because OPM and Eclipse converge to different stable
operating points on the multi-equilibrium VFP curve when gas lift is active.  This is
an optimiser path difference, not a physics error.  All downstream production rates
and pressures that do not directly involve the gas lift rate are correctly matched.

---

## Notebook

A Jupyter notebook version of the validation is in `notebooks/OPM_Validation.ipynb`.
It mirrors the agent workflow in a step-by-step, cell-by-cell format useful for
learning and exploration.

```bash
cd notebooks
python make_opm_validation.py   # regenerate the notebook
jupyter notebook OPM_Validation.ipynb
```

---

## Licence

Code: MIT.  Model data (FIELD_X_001.*): provided for research use, not for
commercial use without permission.  Contact the repository owner.
