"""
agent_04_metrics.py  —  Compute Validation Metrics
====================================================
Loads the aligned arrays from agent_03 and computes a suite of metrics
for every matched mnemonic between OPM and Eclipse.

Metrics computed:
  R²        — Coefficient of determination (shape match).  R²=1.0 means
               perfect tracking; R²=0 means the simulator adds no skill
               over predicting the mean.
  RMSE      — Root Mean Squared Error (absolute magnitude error).
  P95_abs   — 95th-percentile absolute error (worst 5% of timesteps).
  MAPE      — Mean Absolute Percentage Error (%).  Calculated only where
               |y_true| > 1 to avoid division by small numbers.  Intuitive
               to the ML/AI audience as a scale-free accuracy measure.
  Bias      — Mean signed error: mean(y_pred - y_true).  Positive = OPM
               systematically over-predicts; negative = under-predicts.
  Pct_2pct  — Percentage of timesteps where the absolute percentage error
               is within 2%.  A "within-tolerance" metric familiar from
               production engineering acceptance criteria.

Why R² alone is insufficient:
  A simulator that produces systematically 10% higher values with perfect
  shape gets R²=1.0 but is physically wrong.  RMSE captures absolute
  magnitude error.  MAPE and Bias capture systematic over/under-prediction.
  P95 flags the worst 5% of timesteps — often where operationally important
  behaviour (sharp production changes, gas breakthrough) lives.

Pass/fail criterion used in results reporting:
  PASS if R² >= 0.99  (tight match, operationally equivalent)
  MARGINAL if 0.90 <= R² < 0.99
  FAIL if R² < 0.90

Outputs:
  {output_dir}/comparison_metrics.csv   — full results table
  Printed summary table to stdout

Exits 1 if the file cannot be written or arrays are missing.
"""

import os, sys
import numpy as np
import pandas as pd
from pathlib import Path

OFX_OUTPUT_DIR = os.environ.get("OFX_OUTPUT_DIR", "output")


def r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 2:
        return float("nan")
    yt, yp = y_true[mask], y_pred[mask]
    ss_res = np.sum((yt - yp) ** 2)
    ss_tot = np.sum((yt - np.mean(yt)) ** 2)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else float("nan")
    return float(1.0 - ss_res / ss_tot)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() == 0:
        return float("nan")
    return float(np.sqrt(np.mean((y_true[mask] - y_pred[mask]) ** 2)))


def p95_abs_err(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() == 0:
        return float("nan")
    return float(np.percentile(np.abs(y_true[mask] - y_pred[mask]), 95))


def mape(y_true: np.ndarray, y_pred: np.ndarray, threshold: float = 1.0) -> float:
    """Mean Absolute Percentage Error (%).  Ignores points where |y_true| < threshold."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred) & (np.abs(y_true) > threshold)
    if mask.sum() == 0:
        return float("nan")
    return float(100.0 * np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))


def bias(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Bias Error: mean(y_pred - y_true).  +ve = OPM over-predicts."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(y_pred[mask] - y_true[mask]))


def pct_within_tol(y_true: np.ndarray, y_pred: np.ndarray, tol_pct: float = 2.0) -> float:
    """Percentage of timesteps where abs % error <= tol_pct.
    Scale is max(|y_true|, 1) to avoid division by near-zero."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() == 0:
        return float("nan")
    yt, yp = y_true[mask], y_pred[mask]
    scale  = np.where(np.abs(yt) < 1.0, 1.0, np.abs(yt))
    within = (np.abs(yt - yp) / scale * 100.0) <= tol_pct
    return float(100.0 * within.sum() / mask.sum())


def pass_fail(r2_val: float) -> str:
    if np.isnan(r2_val):
        return "N/A"
    if r2_val >= 0.99:
        return "PASS"
    if r2_val >= 0.90:
        return "MARGINAL"
    return "FAIL"


def main():
    print("\nAgent 04 — Compute Validation Metrics")
    print("-" * 60)

    arrays_file = Path(OFX_OUTPUT_DIR) / "aligned_arrays.npz"
    if not arrays_file.exists():
        print(f"  ERROR: {arrays_file} not found.  Run agent_03 first.")
        sys.exit(1)

    data = np.load(arrays_file, allow_pickle=False)
    keys = list(data.keys())

    # Collect all matched ecl_/opm_ pairs (1D summary vectors only)
    ecl_keys = [k for k in keys if k.startswith("ecl_") and data[k].ndim == 1]
    opm_keys = [k for k in keys if k.startswith("opm_") and data[k].ndim == 1]
    ecl_set  = {k[4:] for k in ecl_keys}
    opm_set  = {k[4:] for k in opm_keys}
    matched  = sorted(ecl_set & opm_set)

    rows = []
    for mnemonic in matched:
        y_true = data[f"ecl_{mnemonic}"]
        y_pred = data[f"opm_{mnemonic}"]
        r2_val   = r2(y_true, y_pred)
        rmse_val = rmse(y_true, y_pred)
        p95_val  = p95_abs_err(y_true, y_pred)
        mape_val = mape(y_true, y_pred)
        bias_val = bias(y_true, y_pred)
        pct_val  = pct_within_tol(y_true, y_pred)
        pf       = pass_fail(r2_val)

        # Normalised bias: bias as % of the Eclipse mean magnitude
        ecl_mean = float(np.nanmean(np.abs(y_true[np.isfinite(y_true)])))
        norm_bias_pct = (bias_val / ecl_mean * 100.0) if ecl_mean > 0 else float("nan")

        rows.append({
            "mnemonic":       mnemonic.replace("_", ":"),
            "R2":             round(r2_val,       4),
            "RMSE":           round(rmse_val,     4),
            "P95_abs":        round(p95_val,      4),
            "MAPE_pct":       round(mape_val,     2) if not np.isnan(mape_val)     else float("nan"),
            "Bias":           round(bias_val,     4),
            "NormBias_pct":   round(norm_bias_pct,2) if not np.isnan(norm_bias_pct) else float("nan"),
            "Pct_2pct":       round(pct_val,      1) if not np.isnan(pct_val)      else float("nan"),
            "result":         pf,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["result", "R2"], ascending=[True, True])

    out_csv = Path(OFX_OUTPUT_DIR) / "comparison_metrics.csv"
    df.to_csv(out_csv, index=False)
    print(f"  Metrics written to: {out_csv}")

    # Summary by result category
    total   = len(df)
    n_pass  = (df["result"] == "PASS").sum()
    n_marg  = (df["result"] == "MARGINAL").sum()
    n_fail  = (df["result"] == "FAIL").sum()
    n_na    = (df["result"] == "N/A").sum()
    pct_pass = 100 * n_pass / total if total > 0 else 0

    print(f"\n  Results summary ({total} mnemonics):")
    print(f"    PASS     (R2>=0.99): {n_pass:3d}  ({pct_pass:.0f}%)")
    print(f"    MARGINAL (R2>=0.90): {n_marg:3d}")
    print(f"    FAIL     (R2< 0.90): {n_fail:3d}")
    print(f"    N/A               : {n_na:3d}")

    # Show aggregate MAPE and Bias for PASS mnemonics
    pass_df = df[df["result"] == "PASS"]
    if len(pass_df) > 0:
        avg_mape = pass_df["MAPE_pct"].dropna().mean()
        avg_pct  = pass_df["Pct_2pct"].dropna().mean()
        print(f"\n  PASS mnemonics avg MAPE: {avg_mape:.2f}%  |  avg within 2%: {avg_pct:.1f}%")

    # Show failures for easy review
    failures = df[df["result"].isin(["FAIL", "MARGINAL"])]
    if len(failures) > 0:
        print(f"\n  Non-passing mnemonics:")
        for _, row in failures.iterrows():
            print(f"    {row['mnemonic']:<25} R2={row['R2']:7.4f}  "
                  f"RMSE={row['RMSE']:.3f}  MAPE={row['MAPE_pct']:.1f}%  Bias={row['Bias']:.3f}")

    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
