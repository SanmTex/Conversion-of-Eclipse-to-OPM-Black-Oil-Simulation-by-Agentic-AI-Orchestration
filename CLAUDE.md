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

---

## Project status (updated 2026-04-13)

The workflow is complete and published.  The following deliverables exist alongside the agents:

| File | Description |
|---|---|
| `article/linkedin_article_v2.md` | Final LinkedIn article (Markdown) |
| `article/linkedin_article_v2.docx` | Word version with 5 figures embedded |
| `article/build_presentation.py` | Generates the SPE PPTX via python-pptx |
| `article/OPM_Agentic_AI_SPE_Presentation.pptx` | 16-slide SPE technical presentation |
| `output/figures/` | 5 article figures (copied from a Pretest run) |

**Validation results on FIELD_X_001:**
- 89% of output mnemonics match Eclipse at R² ≥ 0.99 (72 of 81)
- Cell-level pressure residual σ ≈ 2 psia across 114,768 active cells and 61 timesteps
- Cumulative MAPE: FOPT 1.5%, FWPT 1.3%, FGPT 0.5%
- Total wall-clock time: 37 minutes on a standard laptop (35 min OPM, <2 min agents)
- Non-passing: gas lift well rates (WGLIR) — VFP multi-stability between optimisers, not a physics error

**Regenerating article deliverables:**
Before regenerating `linkedin_article_v2.docx` or the PPTX, ensure the 5 figures
are present in `output/figures/`.  If they are missing, copy them from `Pretest/output/figures/`:
```bash
cp Pretest/output/figures/{field_comparison_with_prediction,timeseries_1to1_scatter,metrics_visual,cell_error_distribution,agent_performance}.png output/figures/
```
Then run:
```bash
python article/build_presentation.py          # regenerate PPTX
python article/build_linkedin_article_docx.py # regenerate Word doc (if script exists)
```

**Anonymisation map (original → published):**
- BQC_APR09_P015_EXP → FIELD_X_001
- Simulation dates shifted -8 years (1 Jul 2008 → 1 Jul 2000)
- Well names: ADNH-3A→PROD-01, ADNH-4P→PROD-02, ADNH-5P→PROD-03, ADNH-8P2→PROD-04,
  ADNH-8P3→PROD-05, ADNH-6I→INJ-01, ADNH-7I→INJ-02, BQC1E2→PROD-06, BQC2W2→PROD-07, BQC3W→PROD-08
