# OPM Validation Workflow — Claude Code Agentic Entrypoint

## What this repository is

A complete, reproducible workflow for validating an OPM Flow reservoir simulation
against a commercial Eclipse reference model.  The workflow runs as a sequence of
seven autonomous agents, each with a single responsibility, orchestrated by a
top-level coordinator.

---

## How to run the workflow

Before running: set your data file path in `config.json`.

```bash
python agents/orchestrator.py
```

That single command:
1. Checks the environment (OPM Flow, Python packages, data files)
2. Runs OPM Flow on the DATA deck
3. Parses and time-aligns OPM and Eclipse outputs
4. Computes R², RMSE, and P95 for all 200+ mnemonics
5. Generates field, well, and cell-level comparison figures
6. Builds a clean, OPM-native version of the DATA deck
7. Extends the simulation 1 year and plots the prediction

---

## Agentic workflow instructions for Claude Code

When a user opens this repository and types `claude`, follow these instructions:

1. Read `config.json` and confirm the DATA file path before doing anything.
   If the file does not exist, tell the user to obtain it (see `data/README_DATA.md`)
   and stop.

2. Run the orchestrator:
   ```
   python agents/orchestrator.py
   ```
   After each agent completes, summarise in one sentence what it did.

3. If any agent fails:
   - Read the error output carefully.
   - Identify the most likely root cause (missing file, OPM not installed,
     Python package missing, DATA deck keyword error, etc.).
   - Suggest a specific fix before stopping.
   - Do not retry the failing agent automatically unless the fix is obvious
     and reversible.

4. On successful completion, report:
   - Overall pass rate from `output/comparison_metrics.csv`
   - Path to the headline figure: `output/figures/field_comparison_with_prediction.png`
   - Any mnemonics that did not pass (R² < 0.99) and the likely physics reason.

---

## config.json reference

```json
{
  "data_file":       "data/FIELD_X_001.DATA",
  "eclipse_unsmry":  "data/FIELD_X_001.UNSMRY",
  "eclipse_smspec":  "data/FIELD_X_001.SMSPEC",
  "eclipse_egrid":   "",
  "eclipse_unrst":   "",
  "output_dir":      "output",
  "omp_threads":     4,
  "expected_active": 114768
}
```

- `omp_threads`: set to the number of physical cores on your machine for best performance.
- `expected_active`: do not change — this is a physics checksum on the grid.
- `eclipse_egrid` / `eclipse_unrst`: optional paths to the original Eclipse binary outputs.
  When set, enables cell-level 1:1 scatter and error distribution figures in agent_05.
  Leave empty (`""`) to skip these figures.

---

## Prerequisites

- **OPM Flow** installed in WSL:  `wsl flow --version` should succeed
- **Python 3.9+** with packages in `requirements.txt`
- **Data files** in `data/` — see `data/README_DATA.md` for download instructions
