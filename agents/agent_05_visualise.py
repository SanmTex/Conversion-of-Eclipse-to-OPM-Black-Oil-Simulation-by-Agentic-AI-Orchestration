"""
agent_05_visualise.py  —  Generate Comparison Figures
======================================================
Produces the standard set of comparison plots used in the validation
report and LinkedIn article.  All figures are saved as 300-dpi PNGs
to {output_dir}/figures/.

Why automated figures matter:
  A reproducible validation workflow needs figures that are generated
  programmatically from the same data that produces the metrics.
  Figures created manually in Petrel or Excel are not reproducible and
  cannot be regenerated after a model update.  These figures are the
  visual contract between the simulation outputs and the published
  results.

Figures produced:
  field_rates_comparison.png        — FOPR, FWPR, FGPR (Eclipse vs OPM)
  field_cumulative_comparison.png   — FOPT, FWPT, FGPT (Eclipse vs OPM)
  pass_rate_dashboard.png           — Pass rate by category
  per_well_rates.png                — WOPR for all producers
  metrics_visual.png                — MAPE, Bias, % within 2% for key vectors
  timeseries_1to1_scatter.png       — OPM vs Eclipse scatter per timestep
  cell_1to1_scatter.png             — Cell-level 1:1 scatter (if Eclipse UNRST loaded)
  cell_error_distribution.png       — Cell-level error histograms (if Eclipse UNRST loaded)
  agent_performance.png             — Agent runtime + OPM convergence dashboard

The field_comparison_with_prediction.png figure is created by agent_07
after the +1yr prediction run.

Exits 1 if the aligned arrays are not found.
"""

import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import pandas as pd
from pathlib import Path

OFX_OUTPUT_DIR = os.environ.get("OFX_OUTPUT_DIR", "output")

FIG_DIR = Path(OFX_OUTPUT_DIR) / "figures"
DPI = 300

ECL_COLOR = "#1f77b4"   # blue
OPM_COLOR = "#d62728"   # red
ALPHA     = 0.85


def load_data():
    arrays_file = Path(OFX_OUTPUT_DIR) / "aligned_arrays.npz"
    time_file   = Path(OFX_OUTPUT_DIR) / "time_axes.npz"
    if not arrays_file.exists():
        print(f"  ERROR: {arrays_file} not found.  Run agent_03 first.")
        sys.exit(1)
    data  = np.load(arrays_file, allow_pickle=False)
    tdata = np.load(time_file,   allow_pickle=False)
    return data, tdata


def get_vec(data, prefix, key):
    """Retrieve a vector by prefix+key, returning None if absent."""
    k = f"{prefix}{key.replace(':', '_')}"
    return data[k] if k in data else None


def days_to_year(days):
    """Convert days-since-start to calendar year.  START = 1 JUL 2000 = year 2000.5."""
    return 2000.5 + days / 365.25


# ---------------------------------------------------------------------------
# Figure 1 — Field rates
# ---------------------------------------------------------------------------
def figure_field_rates(data, tdata):
    ecl_t = days_to_year(tdata["ecl_days"])
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    pairs = [
        ("FOPR", "Oil Production Rate (STB/d)",  axes[0]),
        ("FWPR", "Water Production Rate (STB/d)", axes[1]),
        ("FGPR", "Gas Production Rate (Mscf/d)",  axes[2]),
    ]
    for key, ylabel, ax in pairs:
        ecl_v = get_vec(data, "ecl_", key)
        opm_v = get_vec(data, "opm_", key)
        if ecl_v is not None:
            ax.plot(ecl_t, ecl_v, color=ECL_COLOR, lw=1.5, label="Eclipse", alpha=ALPHA)
        if opm_v is not None:
            ax.plot(ecl_t, opm_v, color=OPM_COLOR, lw=1.5, linestyle="--",
                    label="OPM Flow", alpha=ALPHA)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("Simulation Year", fontsize=9)
    fig.suptitle("Field Production Rates: Eclipse vs OPM Flow", fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "field_rates_comparison.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 2 — Field cumulatives
# ---------------------------------------------------------------------------
def figure_field_cumulative(data, tdata):
    ecl_t = days_to_year(tdata["ecl_days"])
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    pairs = [
        ("FOPT", "Cum. Oil Production (MSTB)",  axes[0]),
        ("FWPT", "Cum. Water Production (MSTB)", axes[1]),
        ("FGPT", "Cum. Gas Production (MMscf)",  axes[2]),
    ]
    for key, ylabel, ax in pairs:
        ecl_v = get_vec(data, "ecl_", key)
        opm_v = get_vec(data, "opm_", key)
        if ecl_v is not None:
            ax.plot(ecl_t, ecl_v / 1e3, color=ECL_COLOR, lw=1.5, label="Eclipse", alpha=ALPHA)
        if opm_v is not None:
            ax.plot(ecl_t, opm_v / 1e3, color=OPM_COLOR, lw=1.5, linestyle="--",
                    label="OPM Flow", alpha=ALPHA)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("Simulation Year", fontsize=9)
    fig.suptitle("Field Cumulative Production: Eclipse vs OPM Flow", fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "field_cumulative_comparison.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 3 — Pass rate dashboard
# ---------------------------------------------------------------------------
def figure_pass_rate_dashboard():
    metrics_file = Path(OFX_OUTPUT_DIR) / "comparison_metrics.csv"
    if not metrics_file.exists():
        print("  Skipping pass-rate dashboard (metrics CSV not found)")
        return
    df = pd.read_csv(metrics_file)

    def category(mnemonic):
        m = str(mnemonic)
        if m.startswith("F") and ":" not in m:
            return "Field"
        if m.startswith("W"):
            return "Well"
        if m.startswith("AAQT"):
            return "Aquifer"
        if m.startswith("R"):
            return "Region/Block"
        return "Other"

    df["category"] = df["mnemonic"].apply(category)

    cats = ["Field", "Well", "Aquifer", "Region/Block"]
    pass_rates = []
    for cat in cats:
        sub = df[df["category"] == cat]
        if len(sub) == 0:
            pass_rates.append(0)
        else:
            pass_rates.append(100 * (sub["result"] == "PASS").sum() / len(sub))

    fig, ax = plt.subplots(figsize=(7, 5))
    colors = ["#2ca02c" if p >= 90 else "#ff7f0e" if p >= 70 else "#d62728"
              for p in pass_rates]
    bars = ax.barh(cats, pass_rates, color=colors, edgecolor="white")
    ax.set_xlim(0, 105)
    ax.set_xlabel("Pass Rate (%)", fontsize=10)
    ax.set_title("OPM Validation Pass Rate by Category (R² >= 0.99)", fontsize=11, fontweight="bold")
    for bar, pct in zip(bars, pass_rates):
        ax.text(pct + 1, bar.get_y() + bar.get_height() / 2,
                f"{pct:.0f}%", va="center", fontsize=10, fontweight="bold")
    ax.axvline(100, color="grey", linestyle=":", lw=1)
    ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    out = FIG_DIR / "pass_rate_dashboard.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 4 — Per-well oil rates
# ---------------------------------------------------------------------------
def figure_per_well_rates(data, tdata):
    ecl_t = days_to_year(tdata["ecl_days"])
    producers = ["PROD-01", "PROD-02", "PROD-03", "PROD-04", "PROD-05",
                 "PROD-06", "PROD-07", "PROD-08"]

    fig, axes = plt.subplots(4, 2, figsize=(12, 10), sharex=True)
    axes_flat = axes.flatten()

    for i, well in enumerate(producers):
        ax = axes_flat[i]
        ecl_v = get_vec(data, "ecl_", f"WOPR:{well}")
        opm_v = get_vec(data, "opm_", f"WOPR:{well}")
        if ecl_v is not None:
            ax.plot(ecl_t, ecl_v, color=ECL_COLOR, lw=1.2, label="Eclipse", alpha=ALPHA)
        if opm_v is not None:
            ax.plot(ecl_t, opm_v, color=OPM_COLOR, lw=1.2, linestyle="--",
                    label="OPM", alpha=ALPHA)
        ax.set_title(well, fontsize=9, fontweight="bold")
        ax.set_ylabel("WOPR (STB/d)", fontsize=8)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    for j in range(len(producers), len(axes_flat)):
        axes_flat[j].set_visible(False)

    for ax in axes[-1]:
        ax.set_xlabel("Simulation Year", fontsize=8)

    fig.suptitle("Per-Well Oil Production Rate: Eclipse vs OPM Flow", fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "per_well_rates.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 5 — Metrics visual: MAPE / Bias / % within tolerance
# ---------------------------------------------------------------------------
def figure_metrics_visual():
    metrics_file = Path(OFX_OUTPUT_DIR) / "comparison_metrics.csv"
    if not metrics_file.exists():
        print("  Skipping metrics visual (metrics CSV not found)")
        return
    df = pd.read_csv(metrics_file)

    # MAPE: cumulative vectors only — rates excluded because MAPE inflates
    # near zero (ramp-up / late-life decline) and gives a misleading picture.
    # Bias and within-tolerance: rates + cumulatives (no zero-division issue).
    mape_target = ["FOPT", "FWPT", "FGPT"]   # cumulatives — MAPE meaningful
    rate_target = ["FOPR", "FWPR", "FGPR"]   # rates — bias and tolerance

    df_mape = df[df["mnemonic"].isin(mape_target)].set_index("mnemonic").reindex(
        [m for m in mape_target if m in df["mnemonic"].values]
    )
    df_rate = df[df["mnemonic"].isin(rate_target)].set_index("mnemonic").reindex(
        [m for m in rate_target if m in df["mnemonic"].values]
    )

    if df_rate.empty:
        print("  Skipping metrics visual (target mnemonics not found in CSV)")
        return

    width = 0.55
    fig, axes = plt.subplots(3, 1, figsize=(9, 9))

    # Panel 1: MAPE — cumulatives only
    xm = np.arange(len(df_mape))
    mape_vals = df_mape["MAPE_pct"].fillna(0).values
    colors_m  = ["#2ca02c" if v < 2 else "#ff7f0e" if v < 5 else "#d62728"
                 for v in mape_vals]
    axes[0].bar(xm, mape_vals, width, color=colors_m, edgecolor="white")
    axes[0].axhline(2, color="#ff7f0e", linestyle="--", lw=1, label="2% threshold")
    axes[0].axhline(5, color="#d62728", linestyle=":",  lw=1, label="5% threshold")
    axes[0].set_xticks(xm)
    axes[0].set_xticklabels(df_mape.index.tolist(), fontsize=9)
    axes[0].set_ylabel("MAPE (%)", fontsize=9)
    axes[0].set_title(
        "Mean Absolute Percentage Error — cumulative volumes only\n"
        "(rates excluded: MAPE unreliable near zero production)",
        fontsize=9, fontweight="bold")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, axis="y", alpha=0.3)

    # Panel 2: Normalised Bias — rates only
    xa = np.arange(len(df_rate))
    bias_col  = "NormBias_pct" if "NormBias_pct" in df_rate.columns else "Bias"
    bias_vals = df_rate[bias_col].fillna(0).values
    colors_b  = ["#1f77b4" if v >= 0 else "#d62728" for v in bias_vals]
    axes[1].bar(xa, bias_vals, width, color=colors_b, edgecolor="white")
    axes[1].axhline( 0, color="black",   lw=0.8)
    axes[1].axhline( 2, color="#ff7f0e", linestyle="--", lw=1, alpha=0.7)
    axes[1].axhline(-2, color="#ff7f0e", linestyle="--", lw=1, alpha=0.7)
    axes[1].set_xticks(xa)
    axes[1].set_xticklabels(df_rate.index.tolist(), fontsize=9)
    axes[1].set_ylabel("Normalised Bias (%)", fontsize=9)
    axes[1].set_title("Mean Bias Error  (+ve = OPM over-predicts, as % of Eclipse mean)",
                      fontsize=9, fontweight="bold")
    axes[1].grid(True, axis="y", alpha=0.3)

    # Panel 3: Within-tolerance — rates only
    pct_vals = df_rate["Pct_2pct"].fillna(0).values
    colors_p = ["#2ca02c" if v >= 90 else "#ff7f0e" if v >= 70 else "#d62728"
                for v in pct_vals]
    axes[2].bar(xa, pct_vals, width, color=colors_p, edgecolor="white")
    axes[2].axhline(90, color="#ff7f0e", linestyle="--", lw=1, label="90% target")
    axes[2].set_ylim(0, 110)
    axes[2].set_xticks(xa)
    axes[2].set_xticklabels(df_rate.index.tolist(), fontsize=9)
    axes[2].set_ylabel("% timesteps within 2%", fontsize=9)
    axes[2].set_title("Within-Tolerance Rate (2% threshold)", fontsize=9, fontweight="bold")
    axes[2].legend(fontsize=8)
    axes[2].grid(True, axis="y", alpha=0.3)

    fig.suptitle("OPM vs Eclipse — AI/ML Validation Metrics  (Field Vectors)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "metrics_visual.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 6 — Time-series 1:1 scatter (concordance plot)
# ---------------------------------------------------------------------------
def figure_timeseries_1to1(data, tdata):
    """
    For FOPR, FWPR, FGPR: scatter each timestep as a point (Eclipse x-axis,
    OPM y-axis), coloured by simulation time.  The 1:1 line shows perfect
    agreement; deviation reveals systematic bias or shape error.
    """
    ecl_t  = tdata["ecl_days"]
    keys   = ["FOPR", "FWPR", "FGPR"]
    labels = ["Oil Rate (STB/d)", "Water Rate (STB/d)", "Gas Rate (Mscf/d)"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    cmap = plt.cm.plasma
    norm = mcolors.Normalize(vmin=ecl_t.min(), vmax=ecl_t.max())
    sm   = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])

    for ax, key, label in zip(axes, keys, labels):
        ecl_v = get_vec(data, "ecl_", key)
        opm_v = get_vec(data, "opm_", key)
        if ecl_v is None or opm_v is None:
            ax.set_title(f"{key}\n(data unavailable)", fontsize=9)
            continue

        mask = np.isfinite(ecl_v) & np.isfinite(opm_v)
        ev, ov, tv = ecl_v[mask], opm_v[mask], ecl_t[mask]

        sc = ax.scatter(ev, ov, c=tv, cmap=cmap, norm=norm, s=18, alpha=0.75,
                        edgecolors="none")
        lo = min(ev.min(), ov.min())
        hi = max(ev.max(), ov.max())
        ax.plot([lo, hi], [lo, hi], "k--", lw=1.2, label="1:1")

        # R² annotation
        ss_res = np.sum((ev - ov) ** 2)
        ss_tot = np.sum((ev - ev.mean()) ** 2)
        r2_v   = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        ax.text(0.05, 0.93, f"R² = {r2_v:.4f}", transform=ax.transAxes,
                fontsize=9, fontweight="bold", va="top")

        ax.set_xlabel(f"Eclipse {key}", fontsize=9)
        ax.set_ylabel(f"OPM {key}", fontsize=9)
        ax.set_title(label, fontsize=9, fontweight="bold")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)

    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal", pad=0.12,
                        shrink=0.5, aspect=40)
    cbar.set_label("Simulation time (days since start)", fontsize=8)
    fig.suptitle("OPM vs Eclipse — Time-Series Concordance (each point = 1 timestep)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "timeseries_1to1_scatter.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 7 — Cell-level 1:1 scatter (requires Eclipse UNRST)
# ---------------------------------------------------------------------------
def figure_cell_1to1(data):
    """
    Scatter OPM vs Eclipse at cell level for PRESSURE, SWAT, SGAS.
    Uses mid-simulation timestep.  Eclipse and OPM share identical ACTNUM,
    so cell i in one file corresponds exactly to cell i in the other.
    """
    if "ecl_pressure" not in data:
        print("  Skipping cell 1:1 scatter (Eclipse UNRST not loaded)")
        return

    ecl_p = data["ecl_pressure"]
    opm_p = data["pressure"]
    ecl_sw = data["ecl_swat"]
    opm_sw = data["swat"]
    ecl_sg = data["ecl_sgas"]
    opm_sg = data["sgas"]

    n_t = min(ecl_p.shape[0], opm_p.shape[0])
    mid = n_t // 2

    triples = [
        (ecl_p[mid],  opm_p[mid],  "Pressure (psia)", "PRESSURE"),
        (ecl_sw[mid], opm_sw[mid], "Water Saturation", "SWAT"),
        (ecl_sg[mid], opm_sg[mid], "Gas Saturation",   "SGAS"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for ax, (ev, ov, label, key) in zip(axes, triples):
        mask = np.isfinite(ev) & np.isfinite(ov)
        # Subsample to keep scatter readable (max 20 000 points)
        n = mask.sum()
        if n > 20000:
            idx = np.random.default_rng(42).choice(np.where(mask)[0], 20000, replace=False)
            ev_s, ov_s = ev[idx], ov[idx]
        else:
            ev_s, ov_s = ev[mask], ov[mask]

        ax.scatter(ev_s, ov_s, s=1, alpha=0.3, color=ECL_COLOR, rasterized=True)
        lo = min(ev_s.min(), ov_s.min())
        hi = max(ev_s.max(), ov_s.max())
        ax.plot([lo, hi], [lo, hi], "k--", lw=1.2, label="1:1")

        # R²
        ev_all, ov_all = ev[mask], ov[mask]
        ss_res = np.sum((ev_all - ov_all) ** 2)
        ss_tot = np.sum((ev_all - ev_all.mean()) ** 2)
        r2_v   = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        ax.text(0.05, 0.93, f"R² = {r2_v:.6f}", transform=ax.transAxes,
                fontsize=9, fontweight="bold", va="top")

        ax.set_xlabel(f"Eclipse {key}", fontsize=9)
        ax.set_ylabel(f"OPM {key}", fontsize=9)
        ax.set_title(label, fontsize=9, fontweight="bold")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)

    fig.suptitle("Cell-Level 1:1 Scatter — Eclipse vs OPM Flow (mid-simulation timestep)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "cell_1to1_scatter.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 8 — Cell-level error distributions (requires Eclipse UNRST)
# ---------------------------------------------------------------------------
def figure_cell_error_distribution(data):
    """
    Histogram of (OPM - Eclipse) residuals across all cells and timesteps
    for PRESSURE, SWAT, SGAS.  Shows whether errors are centred on zero
    (unbiased) and how fat the tails are.
    """
    if "ecl_pressure" not in data:
        print("  Skipping cell error distribution (Eclipse UNRST not loaded)")
        return

    ecl_p  = data["ecl_pressure"]
    opm_p  = data["pressure"]
    ecl_sw = data["ecl_swat"]
    opm_sw = data["swat"]
    ecl_sg = data["ecl_sgas"]
    opm_sg = data["sgas"]

    n_t = min(ecl_p.shape[0], opm_p.shape[0])

    triples = [
        (opm_p[:n_t]  - ecl_p[:n_t],   "Pressure error (psia)",       "PRESSURE"),
        (opm_sw[:n_t] - ecl_sw[:n_t],   "Water sat. error (fraction)", "SWAT"),
        (opm_sg[:n_t] - ecl_sg[:n_t],   "Gas sat. error (fraction)",   "SGAS"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for ax, (err_arr, xlabel, key) in zip(axes, triples):
        err_flat = err_arr.ravel()
        finite   = err_flat[np.isfinite(err_flat)]

        # Subsample to 500 000 for histogram speed
        if len(finite) > 500000:
            finite = np.random.default_rng(42).choice(finite, 500000, replace=False)

        mean_e = finite.mean()
        std_e  = finite.std()
        p95_e  = np.percentile(np.abs(finite), 95)

        n_bins = 80
        ax.hist(finite, bins=n_bins, color=ECL_COLOR, alpha=0.7, edgecolor="none",
                density=True)
        ax.axvline(0,      color="black",   lw=1.2, linestyle="--", label="Zero error")
        ax.axvline(mean_e, color="#d62728", lw=1.2, linestyle="-",  label=f"Mean = {mean_e:.3g}")

        # Normal overlay
        x_norm = np.linspace(finite.min(), finite.max(), 200)
        from scipy.stats import norm as sp_norm
        y_norm = sp_norm.pdf(x_norm, mean_e, std_e)
        ax.plot(x_norm, y_norm, color="#ff7f0e", lw=1.5, linestyle=":", label="Normal fit")

        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel("Density", fontsize=9)
        ax.set_title(f"{key}\nμ={mean_e:.3g}  σ={std_e:.3g}  P95={p95_e:.3g}",
                     fontsize=9, fontweight="bold")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.25)

    fig.suptitle("Cell-Level Error Distribution — OPM minus Eclipse (all cells × timesteps)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "cell_error_distribution.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Figure 9 — Agent performance dashboard
# ---------------------------------------------------------------------------
def figure_agent_performance():
    """
    Three-panel dashboard showing:
      1. Agent runtime bar chart (horizontal)
      2. Task Success Rate (pie)
      3. OPM Newton convergence efficiency (gauge-style bar)
    """
    timing_path = Path(OFX_OUTPUT_DIR) / "agent_timings.json"
    conv_path   = Path(OFX_OUTPUT_DIR) / "opm_convergence.json"

    if not timing_path.exists():
        print("  Skipping agent performance dashboard (agent_timings.json not found)")
        return

    with open(timing_path) as fh:
        timings = json.load(fh)

    conv = {}
    if conv_path.exists():
        with open(conv_path) as fh:
            conv = json.load(fh)

    from matplotlib.patches import Patch, Ellipse

    # --- data prep ---
    labels   = [t["description"] for t in timings]
    elapsed  = [t["elapsed_s"]   for t in timings]
    statuses = [t["status"]      for t in timings]

    bar_colors = ["#2ca02c" if s == "PASS" else "#d62728" for s in statuses]

    fig = plt.figure(figsize=(13, 6))
    gs  = fig.add_gridspec(1, 2, width_ratios=[3, 1], wspace=0.4)

    # ------------------------------------------------------------------
    # Panel 1: Agent runtime bars + "Local CPU" ellipse around OPM runs
    # ------------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0])
    y   = np.arange(len(labels))
    ax1.barh(y, elapsed, color=bar_colors, edgecolor="white", height=0.6)
    ax1.set_yticks(y)
    ax1.set_yticklabels(labels, fontsize=8)
    ax1.set_xlabel("Elapsed time (s)", fontsize=9)
    ax1.set_title("Agent Runtime", fontsize=10, fontweight="bold")
    ax1.grid(True, axis="x", alpha=0.3)

    for i, t in enumerate(elapsed):
        ax1.text(t + max(elapsed) * 0.01, i,
                 f"{t:.0f}s", va="center", fontsize=7, color="black")

    ax1.legend(handles=[Patch(facecolor="#2ca02c", label="PASS"),
                        Patch(facecolor="#d62728", label="FAIL")],
               fontsize=8, loc="lower right")

    # Identify OPM simulation run bars — the two long-running agents.
    # Use elapsed time rather than label text to avoid catching short agents
    # whose descriptions also mention "OPM" (e.g. "Build clean OPM deck").
    threshold   = max(elapsed) * 0.4   # must be at least 40% of the longest bar
    opm_indices = [i for i, t in enumerate(elapsed) if t >= threshold]
    if opm_indices:
        max_opm = max(elapsed[i] for i in opm_indices)
        rx = max_opm / 2 + max(elapsed) * 0.06
        ry = 0.52   # tight around each individual bar

        for idx in opm_indices:
            cx = max_opm / 2
            cy = idx
            ellipse = Ellipse((cx, cy), width=rx * 2, height=ry * 2,
                              fill=False, edgecolor="black",
                              linestyle="--", linewidth=1.5, zorder=5)
            ax1.add_patch(ellipse)

        # Single label above the topmost ellipse
        top_idx = max(opm_indices)
        ax1.text(max_opm / 2, top_idx + 0.65,
                 "Local CPU — no tokens consumed",
                 ha="center", va="bottom", fontsize=7.5,
                 color="black", style="italic",
                 bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))

    # ------------------------------------------------------------------
    # Panel 2: OPM solver convergence
    # ------------------------------------------------------------------
    ax2 = fig.add_subplot(gs[1])
    GOLD = "#E6A817"

    if conv:
        eff     = conv.get("convergence_efficiency", 0) * 100
        ts_cnt  = conv.get("timestep_count", 0)
        retried = conv.get("failed_timesteps", 0)
        avg_nwt = conv.get("newton_per_ts_avg", 0)

        # Stacked bar: solved cleanly vs retried (chopped then re-solved)
        ax2.barh([0], [ts_cnt],  color="#2ca02c", height=0.4,
                 label=f"Solved first attempt: {ts_cnt}")
        ax2.barh([0], [retried], color=GOLD,      height=0.4,
                 left=[ts_cnt],
                 label=f"Retried (step halved then solved): {retried}")
        ax2.set_yticks([0])
        ax2.set_yticklabels(["Timesteps"], fontsize=9)
        ax2.set_xlabel("Count", fontsize=9)
        ax2.legend(fontsize=7, loc="lower right")
        ax2.set_title(
            f"OPM Solver\n{eff:.1f}% solved first attempt\n"
            f"avg {avg_nwt:.1f} Newton iters/step",
            fontsize=9, fontweight="bold"
        )
        ax2.grid(True, axis="x", alpha=0.3)
    else:
        ax2.text(0.5, 0.5, "OPM convergence\ndata not available",
                 ha="center", va="center", transform=ax2.transAxes, fontsize=9)
        ax2.set_title("OPM Solver", fontsize=10, fontweight="bold")

    fig.suptitle("Agent Pipeline Performance Dashboard", fontsize=12, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "agent_performance.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("\nAgent 05 — Generate Comparison Figures")
    print("-" * 60)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    data, tdata = load_data()

    figure_field_rates(data, tdata)
    figure_field_cumulative(data, tdata)
    figure_pass_rate_dashboard()
    figure_per_well_rates(data, tdata)
    figure_metrics_visual()
    figure_timeseries_1to1(data, tdata)
    figure_cell_1to1(data)
    figure_cell_error_distribution(data)
    figure_agent_performance()

    print(f"\n  All figures saved to: {FIG_DIR}")
    print("  Note: field_comparison_with_prediction.png generated by agent_07")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
