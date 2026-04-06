"""
agent_01_environment.py  —  Environment Check
==============================================
Verifies that all prerequisites are in place before committing time to
a multi-hour simulation run.  A failed environment check here saves
hours of debugging later.

Checks:
  1. OPM Flow available via WSL  (wsl flow --version)
  2. Required Python packages importable
  3. DATA file exists at configured path
  4. Eclipse reference UNSMRY + SMSPEC exist

Exits 0 if all checks pass, 1 if any check fails.
"""

import os, subprocess, sys, importlib

OFX_DATA_FILE      = os.environ.get("OFX_DATA_FILE",      "data/FIELD_X_001.DATA")
OFX_ECLIPSE_UNSMRY = os.environ.get("OFX_ECLIPSE_UNSMRY", "data/FIELD_X_001.UNSMRY")
OFX_ECLIPSE_SMSPEC = os.environ.get("OFX_ECLIPSE_SMSPEC", "data/FIELD_X_001.SMSPEC")

REQUIRED_PACKAGES = [
    "numpy", "scipy", "pandas", "matplotlib", "resdata",
]

WIDTH = 52

def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    detail_str = f"  {detail}" if detail else ""
    print(f"  {label:<{WIDTH}} [{status}]{detail_str}")
    return ok


def check_opm() -> bool:
    try:
        result = subprocess.run(
            ["wsl", "flow", "--version"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            version_line = (result.stdout + result.stderr).strip().split("\n")[0]
            return check("OPM Flow (wsl flow --version)", True, version_line)
        else:
            return check("OPM Flow (wsl flow --version)", False,
                         "command returned non-zero; is OPM installed in WSL?")
    except FileNotFoundError:
        return check("OPM Flow (wsl flow --version)", False,
                     "wsl not found; WSL required on Windows")
    except subprocess.TimeoutExpired:
        return check("OPM Flow (wsl flow --version)", False,
                     "timed out; WSL may be starting up, try again")


def check_packages() -> bool:
    all_ok = True
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            check(f"Python package: {pkg}", True)
        except ImportError:
            check(f"Python package: {pkg}", False, f"pip install {pkg}")
            all_ok = False
    return all_ok


def check_file(label: str, path: str) -> bool:
    exists = os.path.isfile(path)
    size = f"{os.path.getsize(path):,} bytes" if exists else "not found"
    return check(label, exists, size)


def main():
    print("\nAgent 01 — Environment Check")
    print("-" * (WIDTH + 12))

    results = [
        check_opm(),
        check_packages(),
        check_file("DATA file",           OFX_DATA_FILE),
        check_file("Eclipse UNSMRY",      OFX_ECLIPSE_UNSMRY),
        check_file("Eclipse SMSPEC",      OFX_ECLIPSE_SMSPEC),
    ]

    print("-" * (WIDTH + 12))
    if all(results):
        print("  All checks passed.  Ready to run.\n")
        sys.exit(0)
    else:
        failed = sum(1 for r in results if not r)
        print(f"  {failed} check(s) failed.  Resolve the issues above before running.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
