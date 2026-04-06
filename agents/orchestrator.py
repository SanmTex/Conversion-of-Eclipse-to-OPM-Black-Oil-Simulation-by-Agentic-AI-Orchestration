"""
orchestrator.py  —  OPM Validation Workflow Orchestrator
=========================================================
Runs the full OPM validation and prediction pipeline by spawning
seven agents in sequence.  Each agent is a standalone Python script
that reads its inputs from the shared output directory and writes
results back to it.

Usage:
    python agents/orchestrator.py [--config path/to/config.json]

config.json keys:
    data_file       : path to FIELD_X_001.DATA (required)
    eclipse_unsmry  : path to FIELD_X_001.UNSMRY (required)
    eclipse_smspec  : path to FIELD_X_001.SMSPEC  (required)
    eclipse_egrid   : path to FIELD_X_001.EGRID  (optional — enables cell scatter)
    eclipse_unrst   : path to FIELD_X_001.UNRST  (optional — enables cell-level figures)
    output_dir      : directory for all outputs (default: ./output)
    omp_threads     : OPM thread count (default: 4)
    expected_active : expected active cell count (default: 114768)

If this repo was cloned as-is, set data_file to the path where you
obtained the binary data files (see data/README_DATA.md).
"""

import argparse, json, os, subprocess, sys, time
from pathlib import Path

AGENTS = [
    ("agent_01_environment.py",  "Environment check"),
    ("agent_02_run_opm.py",      "Run OPM Flow (validation)"),
    ("agent_03_parse_output.py", "Parse and align outputs"),
    ("agent_04_metrics.py",      "Compute validation metrics"),
    ("agent_05_visualise.py",    "Generate comparison figures"),
    ("agent_06_build_deck.py",   "Build clean OPM deck"),
    ("agent_07_predict.py",      "Extend simulation +1 year"),
]

AGENTS_DIR = Path(__file__).parent


def load_config(config_path: str) -> dict:
    default = {
        "data_file":       "data/FIELD_X_001.DATA",
        "eclipse_unsmry":  "data/FIELD_X_001.UNSMRY",
        "eclipse_smspec":  "data/FIELD_X_001.SMSPEC",
        "eclipse_egrid":   "",
        "eclipse_unrst":   "",
        "output_dir":      "output",
        "omp_threads":     4,
        "expected_active": 114768,
    }
    if config_path and os.path.exists(config_path):
        with open(config_path) as fh:
            user_cfg = json.load(fh)
        default.update(user_cfg)
    return default


def _append_timing(timing_path: str, record: dict):
    """Append a timing record to the agent_timings.json list."""
    records = []
    if os.path.exists(timing_path):
        try:
            with open(timing_path) as fh:
                records = json.load(fh)
        except Exception:
            records = []
    records.append(record)
    with open(timing_path, "w") as fh:
        json.dump(records, fh, indent=2)


def run_agent(script: str, description: str, env: dict, timing_path: str) -> bool:
    agent_path = AGENTS_DIR / script
    if not agent_path.exists():
        print(f"  ERROR: agent script not found: {agent_path}")
        return False

    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  Script: {script}")
    print(f"{'='*60}")
    t0 = time.time()

    result = subprocess.run(
        [sys.executable, str(agent_path)],
        env=env,
        text=True,
    )

    elapsed = time.time() - t0
    status = "PASS" if result.returncode == 0 else "FAIL"

    _append_timing(timing_path, {
        "agent":       script,
        "description": description,
        "elapsed_s":   round(elapsed, 2),
        "status":      status,
    })

    if result.returncode == 0:
        print(f"\n  [DONE] {description}  ({elapsed:.1f}s)")
        return True
    else:
        print(f"\n  [FAILED] {description} (exit code {result.returncode}, {elapsed:.1f}s)")
        print(f"\n  Root cause: agent exited non-zero.  Review the output above.")
        print(f"  Suggested fix: re-run agent {script} standalone for debugging.")
        return False


def main():
    parser = argparse.ArgumentParser(description="OPM Validation Orchestrator")
    parser.add_argument("--config", default="config.json",
                        help="Path to config.json (default: config.json)")
    args = parser.parse_args()

    cfg = load_config(args.config)

    # Resolve paths relative to repo root (parent of agents/)
    repo_root = str(AGENTS_DIR.parent)
    for key in ("data_file", "eclipse_unsmry", "eclipse_smspec", "output_dir"):
        if not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(repo_root, cfg[key])

    # Optional eclipse binary paths — resolve only if non-empty
    for key in ("eclipse_egrid", "eclipse_unrst"):
        if cfg[key] and not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(repo_root, cfg[key])

    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(os.path.join(cfg["output_dir"], "figures"), exist_ok=True)

    timing_path = os.path.join(cfg["output_dir"], "agent_timings.json")
    # Clear any previous run's timings
    if os.path.exists(timing_path):
        os.remove(timing_path)

    print("OPM Validation Workflow — Orchestrator")
    print(f"Config: {args.config}")
    print(f"DATA file:    {cfg['data_file']}")
    print(f"Eclipse SMRY: {cfg['eclipse_unsmry']}")
    print(f"Output dir:   {cfg['output_dir']}")
    print(f"OMP threads:  {cfg['omp_threads']}")
    if cfg["eclipse_unrst"]:
        print(f"Eclipse UNRST: {cfg['eclipse_unrst']}  (cell-level figures enabled)")
    else:
        print(f"Eclipse UNRST: (not configured — cell-level figures will be skipped)")

    # Pass config to all agents via environment variables
    env = os.environ.copy()
    env["OFX_DATA_FILE"]        = cfg["data_file"]
    env["OFX_ECLIPSE_UNSMRY"]   = cfg["eclipse_unsmry"]
    env["OFX_ECLIPSE_SMSPEC"]   = cfg["eclipse_smspec"]
    env["OFX_ECLIPSE_EGRID"]    = cfg["eclipse_egrid"]
    env["OFX_ECLIPSE_UNRST"]    = cfg["eclipse_unrst"]
    env["OFX_OUTPUT_DIR"]       = cfg["output_dir"]
    env["OFX_OMP_THREADS"]      = str(cfg["omp_threads"])
    env["OFX_EXPECTED_ACTIVE"]  = str(cfg["expected_active"])
    env["OFX_REPO_ROOT"]        = repo_root

    t_start = time.time()
    for script, description in AGENTS:
        ok = run_agent(script, description, env, timing_path)
        if not ok:
            print(f"\nOrchestrator stopped at: {script}")
            sys.exit(1)

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  All {len(AGENTS)} agents completed successfully ({elapsed/60:.1f} min)")
    print(f"  Outputs in: {cfg['output_dir']}")
    print(f"  Key files:")
    print(f"    comparison_metrics.csv")
    print(f"    agent_timings.json")
    print(f"    figures/field_comparison_with_prediction.png")
    print(f"    figures/pass_rate_dashboard.png")
    print(f"    figures/agent_performance.png")
    print(f"    FIELD_X_001_OPM_CLEAN.DATA")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
