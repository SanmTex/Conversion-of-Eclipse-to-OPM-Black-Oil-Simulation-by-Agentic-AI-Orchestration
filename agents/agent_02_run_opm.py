"""
agent_02_run_opm.py  —  Run OPM Flow (Validation)
==================================================
Converts the Windows DATA file path to a WSL path and runs OPM Flow.
Streams the PRT output line-by-line so the user can watch progress.

Why these flags:
  --parsing-strictness=low     Accept Eclipse keywords that OPM does not
                                recognise (e.g. WCUTBACK, GLIFTOPT) without
                                aborting.  Without this, OPM exits on the
                                first unknown keyword.
  --max-single-precision-days=0  Force double-precision arithmetic throughout.
                                OPM defaults to single precision after a
                                threshold, which degrades pressure accuracy.
  OMP_NUM_THREADS              Limit CPU parallelism to avoid starving the
                                Windows host process.

The simulation end-point matches the Eclipse reference (1 JAN 2011 in
anonymised dates).  The +1-year prediction is handled separately by
agent_07 to keep this agent focused on the validation run.

After the run completes, Newton iteration and failed timestep counts are
extracted from the PRT log and written to opm_convergence.json for the
agent performance dashboard in agent_05.

Exits 0 on clean completion, 1 on convergence failure or crash.
"""

import json, os, re, subprocess, sys
from pathlib import Path, PurePosixPath

OFX_DATA_FILE  = os.environ.get("OFX_DATA_FILE", "data/FIELD_X_001.DATA")
OFX_OUTPUT_DIR = os.environ.get("OFX_OUTPUT_DIR", "output")
OMP_THREADS    = os.environ.get("OFX_OMP_THREADS", "4")


def win_to_wsl(win_path: str) -> str:
    """Convert a Windows path to its WSL equivalent (/mnt/c/...)."""
    p = Path(win_path).resolve()
    drive = p.drive.lower().rstrip(":")   # 'c'
    rest  = str(p.relative_to(p.anchor)).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def check_completion(log_lines: list) -> bool:
    """Return True if the PRT log shows a clean END keyword."""
    for line in reversed(log_lines[-200:]):
        if "Time step" in line and "Converged" in line:
            return True
        if re.search(r"Simulation\s+complete", line, re.IGNORECASE):
            return True
        if "End of simulation" in line:
            return True
    return False


def check_failure(log_lines: list) -> str:
    """Return a failure message if OPM reported a convergence failure."""
    for line in log_lines[-100:]:
        if re.search(r"Convergence\s+failure|ABORT|Fatal", line, re.IGNORECASE):
            return line.strip()
    return ""


def parse_convergence_stats(log_lines: list) -> dict:
    """
    Extract Newton iteration counts and failed timestep count from PRT log.
    Returns a dict suitable for opm_convergence.json.

    OPM outputs lines like:
      'Time step X succeeded after Y Newton iterations.'
      'Timestep X failed to converge' or 'chopped' variants
    """
    newton_counts   = []   # iterations per successful timestep
    failed_steps    = 0
    report_steps    = 0

    # OPM outputs successful steps as: " Newton its= 8, linearizations= 9 ..."
    # Failed steps are flagged by: "Solver convergence failure" or "Timestep chopped"
    newton_re  = re.compile(r'Newton\s+its\s*=\s*(\d+)', re.IGNORECASE)
    failed_re  = re.compile(r'convergence failure|Timestep chopped', re.IGNORECASE)
    report_re  = re.compile(r'Report\s+step\s+\d+', re.IGNORECASE)

    for line in log_lines:
        m = newton_re.search(line)
        if m:
            newton_counts.append(int(m.group(1)))
        if failed_re.search(line):
            failed_steps += 1
        if report_re.search(line):
            report_steps += 1

    total_ts   = len(newton_counts)
    newton_sum = sum(newton_counts)
    avg_newton = newton_sum / total_ts if total_ts > 0 else 0.0
    total_attempts = total_ts + failed_steps
    efficiency = total_ts / total_attempts if total_attempts > 0 else 1.0

    return {
        "timestep_count":        total_ts,
        "report_steps":          report_steps,
        "newton_total":          newton_sum,
        "newton_per_ts_avg":     round(avg_newton, 2),
        "failed_timesteps":      failed_steps,
        "convergence_efficiency": round(efficiency, 4),
    }


def main():
    data_file = Path(OFX_DATA_FILE).resolve()
    if not data_file.exists():
        print(f"ERROR: DATA file not found: {data_file}")
        print("       Run agent_01 first to verify prerequisites.")
        sys.exit(1)

    wsl_data = win_to_wsl(str(data_file))
    wsl_outdir = win_to_wsl(str(Path(OFX_OUTPUT_DIR).resolve()))

    cmd = [
        "wsl",
        f"OMP_NUM_THREADS={OMP_THREADS}",
        "flow",
        f"--output-dir={wsl_outdir}",
        "--parsing-strictness=low",
        "--max-single-precision-days=0",
        wsl_data,
    ]

    print("\nAgent 02 — Run OPM Flow (Validation)")
    print(f"  DATA : {data_file}")
    print(f"  WSL  : {wsl_data}")
    print(f"  Threads: {OMP_THREADS}")
    print(f"  Command: {' '.join(cmd)}\n")
    print("  Streaming OPM output (this may take 30-120 minutes)...")
    print("-" * 60)

    os.makedirs(OFX_OUTPUT_DIR, exist_ok=True)

    log_lines = []
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log_lines.append(line)
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nInterrupted by user.")
        sys.exit(1)

    print("-" * 60)
    print(f"  OPM exit code: {proc.returncode}")

    failure_msg = check_failure(log_lines)
    if proc.returncode != 0 or failure_msg:
        print(f"  ERROR: OPM simulation failed.")
        if failure_msg:
            print(f"  Detail: {failure_msg}")
        print("  Check the PRT file in the output directory for details.")
        sys.exit(1)

    # Parse and write convergence stats
    stats = parse_convergence_stats(log_lines)
    conv_path = Path(OFX_OUTPUT_DIR) / "opm_convergence.json"
    with open(conv_path, "w") as fh:
        json.dump(stats, fh, indent=2)
    print(f"\n  Convergence stats: {stats['timestep_count']} timesteps, "
          f"avg {stats['newton_per_ts_avg']:.1f} Newton iters, "
          f"{stats['failed_timesteps']} failed, "
          f"efficiency {stats['convergence_efficiency']*100:.1f}%")
    print(f"  Written: {conv_path}")

    # Verify output files were created
    stem = data_file.stem  # FIELD_X_001
    expected = [
        Path(OFX_OUTPUT_DIR) / f"{stem}.UNRST",
        Path(OFX_OUTPUT_DIR) / f"{stem}.EGRID",
        Path(OFX_OUTPUT_DIR) / f"{stem}.INIT",
        Path(OFX_OUTPUT_DIR) / f"{stem}.UNSMRY",
    ]
    missing = [str(p) for p in expected if not p.exists()]
    if missing:
        print("  WARNING: expected output files not found:")
        for m in missing:
            print(f"    {m}")
        sys.exit(1)

    print(f"  OPM run complete.  Outputs in: {OFX_OUTPUT_DIR}")
    for p in expected:
        if p.exists():
            print(f"    {p.name}: {os.path.getsize(p):,} bytes")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
