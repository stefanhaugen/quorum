"""
QUORUM Design Module (DM)
==========================
Visualization, export, and human-systems integration layer.

CHANGELOG (v2 API Integration)
------------------------------
- CHANGED: All plot titles now reference "HAPI Features" instead of "WDI"
- CHANGED: Correlation heatmap title updated for food security context
- CHANGED: SHAP plots reference "HAPI Food Security/Price Features"
- CHANGED: All functions emit quorum_chat: prefixed error messages
- CHANGED: Graceful handling of empty result sets (plots skipped with msg)
- RETAINED: All DM requirements and output file naming conventions

Functions correspond to DM requirements:
  DM-REQ-001: Migration overview time-series visualizations
  DM-REQ-002: Correlation heatmap with significance annotations
  DM-REQ-003: Fixed-effects coefficient plot
  DM-REQ-004: SHAP importance and beeswarm plots
  DM-REQ-005: Partial dependence plots (PCA and original features)
  DM-REQ-006: CSV export of analytical results
  DM-REQ-007: Pipeline summary report
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import seaborn as sns
import shap

from .config import (
    CA_ISO3,
    NAME_MAP,
    OUTPUT_DIR,
    OVERLAP_YEAR_MAX,
    OVERLAP_YEAR_MIN,
    PALETTE,
)
from .icd import (
    AnalyticsBundle,
    CorrelationResult,
    FixedEffectsResult,
    LaggedPanelBundle,
    MonthlyMigrationBlock,
    RandomForestResult,
)


def _ensure_output_dir(output_dir: Path = OUTPUT_DIR) -> Path:
    """Create output directory if it does not exist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-001: MIGRATION TIME-SERIES OVERVIEW
# ═════════════════════════════════════════════════════════════════════


def plot_migration_overview(
    monthly: MonthlyMigrationBlock,
    bundle: LaggedPanelBundle,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Four-panel migration overview figure."""
    print("  [DM] Plotting migration overview...")
    output_dir = _ensure_output_dir(output_dir)
    data = monthly.data

    annual = (
        data.groupby(["iso3", "year"])
        .agg(
            outbound_total=("outbound_total", "sum"),
            outbound_to_us=("outbound_to_us", "sum"),
            inbound_total=("inbound_total", "sum"),
            net_outbound=("net_outbound", "sum"),
        )
        .reset_index()
    )

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Central America: Migration Overview",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    # (a) Monthly outbound by country
    ax = axes[0, 0]
    for iso3 in CA_ISO3:
        sub = data[data["iso3"] == iso3].sort_values("year_month")
        ax.plot(
            range(len(sub)),
            sub["outbound_total"],
            label=NAME_MAP[iso3],
            color=PALETTE[iso3],
            linewidth=1.8,
        )
    ref = data[data["iso3"] == "GTM"].sort_values("year_month")
    months = ref["year_month"].tolist()
    tick_idx = [i for i, m in enumerate(months) if m.endswith("-01")]
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([months[i][:4] for i in tick_idx])
    ax.set_title("Monthly Outbound Migration", fontweight="bold")
    ax.set_ylabel("Migrants")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(alpha=0.3)

    # (b) Annual total outbound (stacked)
    ax = axes[0, 1]
    years = sorted(annual["year"].unique())
    bottom = np.zeros(len(years))
    for iso3 in CA_ISO3:
        vals = [
            annual[(annual["iso3"] == iso3) & (annual["year"] == y)]["outbound_total"].sum()
            for y in years
        ]
        ax.bar(years, vals, bottom=bottom, label=NAME_MAP[iso3], color=PALETTE[iso3])
        bottom += np.array(vals)
    ax.set_title("Annual Total Outbound (Stacked)", fontweight="bold")
    ax.set_ylabel("Migrants")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(axis="y", alpha=0.3)

    # (c) Outbound to US vs other
    ax = axes[1, 0]
    agg = (
        annual.groupby("year")
        .agg(
            total=("outbound_total", "sum"),
            to_us=("outbound_to_us", "sum"),
        )
        .reset_index()
    )
    agg["other"] = agg["total"] - agg["to_us"]
    ax.bar(agg["year"], agg["to_us"], label="To USA", color="#c0392b")
    ax.bar(
        agg["year"],
        agg["other"],
        bottom=agg["to_us"],
        label="Other Destinations",
        color="#7f8c8d",
    )
    ax.set_title("Regional Outbound: USA vs Other", fontweight="bold")
    ax.set_ylabel("Migrants")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # (d) Net outbound by country
    ax = axes[1, 1]
    net = annual.groupby(["iso3", "year"])["net_outbound"].sum().reset_index()
    x = np.arange(len(CA_ISO3))
    width = 0.2
    for i, year in enumerate(years):
        vals = [
            net[(net["iso3"] == c) & (net["year"] == year)]["net_outbound"].sum() for c in CA_ISO3
        ]
        ax.bar(
            x + i * width,
            vals,
            width,
            label=str(year),
            color=plt.cm.RdYlGn_r(i / max(len(years) - 1, 1)),
        )
    ax.set_xticks(x + width)
    ax.set_xticklabels([NAME_MAP[c][:3] for c in CA_ISO3], fontsize=8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Net Outbound by Country", fontweight="bold")
    ax.set_ylabel("Net Migrants (Out minus In)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    path = output_dir / "3A_migration_overview.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-002: CORRELATION HEATMAP
# ═════════════════════════════════════════════════════════════════════


def plot_correlation_heatmap(
    result: CorrelationResult,
    target_label: str = "Total Outbound Migration",
    output_dir: Path = OUTPUT_DIR,
) -> Path | None:
    """Heatmap of Pearson r by feature and lag, with significance stars."""
    print("  [DM] Plotting correlation heatmap...")

    if result.records.empty:
        print(
            "quorum_chat: Skipping correlation heatmap because no "
            "correlation results are available."
        )
        return None

    output_dir = _ensure_output_dir(output_dir)

    df = result.records
    pivot_r = df.pivot_table(index="Feature", columns="Lag (years)", values="Pearson_r")
    pivot_p = df.pivot_table(index="Feature", columns="Lag (years)", values="Pearson_p")

    fig, ax = plt.subplots(figsize=(8, max(6, len(pivot_r) * 0.45)))
    sns.heatmap(
        pivot_r,
        annot=True,
        fmt=".2f",
        cmap="RdBu_r",
        center=0,
        vmin=-1,
        vmax=1,
        linewidths=0.5,
        ax=ax,
        cbar_kws={"label": "Pearson r"},
    )

    for i, feat in enumerate(pivot_r.index):
        for j, lag in enumerate(pivot_r.columns):
            p = pivot_p.loc[feat, lag] if feat in pivot_p.index else 1
            if pd.notna(p) and p < 0.05:
                ax.text(
                    j + 0.85,
                    i + 0.25,
                    "*",
                    fontsize=12,
                    color="black",
                    fontweight="bold",
                )

    ax.set_title(
        f"Lagged Pearson Correlations: HAPI Features to {target_label}\n"
        f"(* = p < 0.05, column = years features lead migration)",
        fontweight="bold",
    )
    ax.set_xlabel("Feature Lead Time (years)")
    ax.set_ylabel("")
    plt.tight_layout()

    path = output_dir / "3B_lagged_correlation_heatmap.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-003: FIXED-EFFECTS COEFFICIENT PLOT
# ═════════════════════════════════════════════════════════════════════


def plot_fixed_effects(
    result: FixedEffectsResult,
    output_dir: Path = OUTPUT_DIR,
) -> Path | None:
    """Horizontal bar chart of FE regression coefficients with CI bars."""
    print("  [DM] Plotting fixed-effects coefficient chart...")

    if result.coefficients.empty:
        print(
            "quorum_chat: Skipping fixed-effects plot because no regression results are available."
        )
        return None

    output_dir = _ensure_output_dir(output_dir)

    df = result.coefficients
    fig, ax = plt.subplots(figsize=(9, max(5, len(df) * 0.4)))
    y_pos = range(len(df))
    colors = ["#c0392b" if s else "#95a5a6" for s in df["Significant"]]

    ax.barh(list(y_pos), df["coef"], color=colors, alpha=0.8, height=0.6)
    ax.errorbar(
        df["coef"],
        list(y_pos),
        xerr=1.96 * df["se"],
        fmt="none",
        color="black",
        capsize=3,
        linewidth=1,
    )
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(df["Feature"], fontsize=8)
    ax.set_xlabel("Standardised Coefficient (log outbound migration)")
    ax.set_title(
        "Fixed-Effects Panel Regression Coefficients\n"
        "(Red = p < 0.05, HAPI features lagged 1 year, country FE)",
        fontweight="bold",
    )
    sig_patch = mpatches.Patch(color="#c0392b", alpha=0.8, label="p < 0.05")
    ns_patch = mpatches.Patch(color="#95a5a6", alpha=0.8, label="p >= 0.05")
    ax.legend(handles=[sig_patch, ns_patch], fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()

    path = output_dir / "3C_fixed_effects_coefplot.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-004: SHAP PLOTS
# ═════════════════════════════════════════════════════════════════════


def plot_shap_importance(
    result: RandomForestResult,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Horizontal bar chart of mean |SHAP| in original feature space."""
    print("  [DM] Plotting SHAP importance bar chart...")
    output_dir = _ensure_output_dir(output_dir)

    ms = result.mean_shap
    fig, ax = plt.subplots(figsize=(8, max(5, len(ms) * 0.4)))
    bars = ax.barh(
        ms.index[::-1],
        ms.values[::-1],
        color=plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(ms))),
        alpha=0.85,
    )
    ax.set_xlabel("Mean |SHAP Value| (impact on log outbound migration)")
    ax.set_title(
        "Feature Importance: HAPI Features (via PCA back-projection)\n"
        "Random Forest (max_depth=3) to Total Outbound Migration",
        fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.3)
    for bar, val in zip(bars, ms.values[::-1], strict=False):
        ax.text(
            val + 0.001,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.3f}",
            va="center",
            fontsize=9,
        )
    plt.tight_layout()

    path = output_dir / "3D_shap_importance_pca.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


def plot_shap_beeswarm(
    result: RandomForestResult,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """SHAP beeswarm plot in original feature space."""
    print("  [DM] Plotting SHAP beeswarm...")
    output_dir = _ensure_output_dir(output_dir)

    fig, ax = plt.subplots(figsize=(10, max(6, len(result.feature_names) * 0.5)))
    shap.summary_plot(
        result.shap_values_original,
        result.X_scaled,
        feature_names=result.feature_names,
        show=False,
    )
    plt.title(
        "SHAP Beeswarm: Impact of HAPI Features\n"
        "(colour = standardised feature value, back-projected through PCA)",
        fontweight="bold",
        pad=15,
    )
    plt.tight_layout()

    path = output_dir / "3D_shap_beeswarm_pca.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-005: PARTIAL DEPENDENCE PLOTS
# ═════════════════════════════════════════════════════════════════════


def plot_partial_dependence_pca(
    result: RandomForestResult,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Partial dependence scatter for each PCA component."""
    print("  [DM] Plotting PCA partial dependence...")
    output_dir = _ensure_output_dir(output_dir)

    loadings = result.pca_loadings
    pc_names = list(loadings.columns)
    y = result.y_actual
    countries = result.countries

    fig, axes = plt.subplots(1, len(pc_names), figsize=(15, 4.5))
    if len(pc_names) == 1:
        axes = [axes]
    fig.suptitle(
        "Partial Dependence: Principal Components vs Outbound Migration",
        fontweight="bold",
        fontsize=12,
        y=1.05,
    )

    for i, (ax, pc) in enumerate(zip(axes, pc_names, strict=False)):
        vals = result.X_pca[:, i]
        for iso3 in CA_ISO3:
            mask = countries == iso3
            if mask.sum() == 0:
                continue
            ax.scatter(
                vals[mask],
                np.expm1(y[mask]),
                label=NAME_MAP[iso3],
                color=PALETTE[iso3],
                alpha=0.85,
                s=60,
                zorder=3,
            )
        if len(vals) > 1:
            z = np.polyfit(vals, np.expm1(y), 1)
            xfit = np.linspace(vals.min(), vals.max(), 100)
            ax.plot(
                xfit,
                np.polyval(z, xfit),
                "k--",
                linewidth=1.2,
                alpha=0.6,
            )
        ax.set_xlabel(f"{pc} Value", fontsize=10)
        ax.set_ylabel("Outbound Migrants", fontsize=10)
        top_feat = loadings[pc].abs().idxmax()
        ax.set_title(f"{pc}\n(Top loading: {top_feat})", fontsize=10)
        ax.grid(alpha=0.3)

    axes[-1].legend(fontsize=8, loc="upper right", bbox_to_anchor=(1.4, 1))
    plt.tight_layout()

    path = output_dir / "3D_partial_dependence_pca.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


def plot_partial_dependence_top_features(
    result: RandomForestResult,
    n_features: int = 4,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Partial dependence for the top N original features by SHAP."""
    print(f"  [DM] Plotting partial dependence for top {n_features} features...")
    output_dir = _ensure_output_dir(output_dir)

    top_feats = list(result.mean_shap.head(n_features).index)
    actual_n = len(top_feats)
    if actual_n == 0:
        print("quorum_chat: No features to plot partial dependence for.")
        return output_dir / "3E_partial_dependence.png"

    y = result.y_actual
    countries = result.countries

    nrows = max(1, (actual_n + 1) // 2)
    fig, axes = plt.subplots(nrows, 2, figsize=(13, 5 * nrows))
    if nrows == 1:
        axes = axes.reshape(1, -1)
    fig.suptitle(
        f"Partial Dependence: Top {actual_n} HAPI Features vs "
        f"Outbound Migration\n"
        "(Each point = one country-year, features lagged 1 year)",
        fontweight="bold",
        fontsize=12,
    )

    for ax, feat in zip(axes.flat, top_feats, strict=False):
        feat_idx = result.feature_names.index(feat)
        vals = result.X_scaled[:, feat_idx]

        for iso3 in CA_ISO3:
            mask = countries == iso3
            if mask.sum() == 0:
                continue
            ax.scatter(
                vals[mask],
                np.expm1(y[mask]),
                label=NAME_MAP[iso3],
                color=PALETTE[iso3],
                alpha=0.85,
                s=80,
                zorder=3,
            )
        if len(vals) > 1:
            z = np.polyfit(vals, np.expm1(y), 1)
            xfit = np.linspace(vals.min(), vals.max(), 100)
            ax.plot(
                xfit,
                np.polyval(z, xfit),
                "k--",
                linewidth=1.2,
                alpha=0.6,
            )
        ax.set_xlabel(feat, fontsize=9)
        ax.set_ylabel("Outbound Migrants", fontsize=9)
        ax.set_title(feat, fontweight="bold", fontsize=10)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=6, ncol=2)

    for ax in axes.flat[actual_n:]:
        ax.set_visible(False)

    plt.tight_layout()
    path = output_dir / "3E_partial_dependence.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"       Saved: {path.name}")
    return path


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-006: CSV EXPORTS
# ═════════════════════════════════════════════════════════════════════


def export_csv_results(
    analytics: AnalyticsBundle,
    output_dir: Path = OUTPUT_DIR,
) -> list[Path]:
    """Export analytical results as CSV files."""
    print("  [DM] Exporting CSV results...")
    output_dir = _ensure_output_dir(output_dir)
    paths = []

    # Primary panel
    p = output_dir / "quorum_panel_lag1.csv"
    analytics.panel_bundle.primary_panel.to_csv(p, index=False)
    paths.append(p)

    # Correlations
    if not analytics.correlations.records.empty:
        p = output_dir / "3B_lagged_correlations.csv"
        analytics.correlations.records.to_csv(p, index=False)
        paths.append(p)

    # Fixed effects
    if not analytics.fixed_effects.coefficients.empty:
        p = output_dir / "3C_fixed_effects_results.csv"
        analytics.fixed_effects.coefficients.to_csv(p, index=False)
        paths.append(p)

    for path in paths:
        print(f"       Saved: {path.name}")
    return paths


# ═════════════════════════════════════════════════════════════════════
# DM-REQ-007: SUMMARY REPORT
# ═════════════════════════════════════════════════════════════════════


def print_summary(analytics: AnalyticsBundle) -> None:
    """Print a human-readable pipeline summary to console."""
    monthly = analytics.monthly_migration
    bundle = analytics.panel_bundle
    corr = analytics.correlations
    fe = analytics.fixed_effects
    rf = analytics.random_forest

    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)

    print(
        f"\n  Migration data:   {monthly.year_range}  |  {monthly.row_count:,} country-month rows"
    )
    print(
        f"  Analysis panel:   {OVERLAP_YEAR_MIN} to {OVERLAP_YEAR_MAX}  |  "
        f"{len(bundle.primary_panel)} country-year rows (lag=1)"
    )
    print(f"  HAPI features:    {len(rf.feature_names)} indicators")
    print("  Data source:      HDX HAPI (food security + food prices)")

    print(f"\n  Correlations: {corr.summary()}")
    print(f"  Fixed Effects: {fe.summary()}")

    print(
        f"\n  Random Forest:  Train R2={rf.train_r2:.3f}  |  "
        f"LOGO-CV R2={rf.cv_r2_mean:.3f} +/- {rf.cv_r2_std:.3f}"
    )
    print("\n  Top SHAP drivers (HAPI feature space):")
    for feat, val in rf.mean_shap.head(5).items():
        print(f"    {feat}: {val:.4f}")


# ═════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═════════════════════════════════════════════════════════════════════


def run_design_module(analytics: AnalyticsBundle) -> None:
    """Execute the full Design Module pipeline."""
    print("\n" + "=" * 60)
    print("DESIGN MODULE")
    print("=" * 60)

    plot_migration_overview(
        analytics.monthly_migration,
        analytics.panel_bundle,
    )
    plot_correlation_heatmap(analytics.correlations)
    plot_fixed_effects(analytics.fixed_effects)
    plot_shap_importance(analytics.random_forest)
    plot_shap_beeswarm(analytics.random_forest)
    plot_partial_dependence_pca(analytics.random_forest)
    plot_partial_dependence_top_features(analytics.random_forest)
    export_csv_results(analytics)
    print_summary(analytics)

    print("\n  [DM] Design Module complete.")
    print(f"  All outputs saved to: {OUTPUT_DIR}/")
