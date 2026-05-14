"""
QUORUM Analytics Module (AM)
=============================
Transforms standardized information blocks into risk assessments
with quantified uncertainty.

CHANGELOG (v2 API Integration)
------------------------------
- CHANGED: All functions now emit quorum_chat: prefixed error messages
- CHANGED: run_random_forest gracefully handles cases where PCA_COMPONENTS
           exceeds available features (auto-reduces)
- CHANGED: run_fixed_effects handles potential NaN-heavy HAPI features
- RETAINED: All analytical logic and ICD contracts unchanged

Functions in this module correspond to AM requirements:
  AM-REQ-001: Lagged cross-correlation analysis (Pearson + Spearman)
  AM-REQ-002: Fixed-effects panel regression with country dummies
  AM-REQ-003: Dimensionality reduction via PCA
  AM-REQ-004: Random Forest with constrained hyperparameters
  AM-REQ-005: SHAP explainability with PCA back-projection
  AM-REQ-006: Leave-one-group-out cross-validation

Every public function accepts ICD input blocks and returns validated
ICD result objects (see icd.py). The Analytics Module has zero
knowledge of file paths, visualization, or data loading.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import shap
import statsmodels.formula.api as smf
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import r2_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import (
    NAME_MAP,
    PCA_COMPONENTS,
    RF_PARAMS,
    SIGNIFICANCE_THRESHOLD,
)
from .icd import (
    AnalyticsBundle,
    CorrelationResult,
    FixedEffectsResult,
    LaggedPanelBundle,
    MonthlyMigrationBlock,
    RandomForestResult,
    validate_block,
)

# ═════════════════════════════════════════════════════════════════════
# AM-REQ-001: LAGGED CROSS-CORRELATIONS
# ═════════════════════════════════════════════════════════════════════


def run_correlations(
    bundle: LaggedPanelBundle,
    threshold: float = SIGNIFICANCE_THRESHOLD,
) -> CorrelationResult:
    """Compute Pearson and Spearman correlations at each lag offset.

    For every (feature, lag) combination, tests bivariate association
    between the HAPI indicator and the target migration variable.
    """
    print("  [AM] Computing lagged cross-correlations...")

    target = bundle.target_column
    records = []

    for lag, panel in bundle.panels.items():
        feat_cols = [c for c in bundle.feature_columns if c in panel.columns]
        for feat in feat_cols:
            sub = panel[["iso3", target, feat]].dropna()
            if len(sub) < 5:
                continue
            r, p = stats.pearsonr(sub[feat], sub[target])
            rs, ps = stats.spearmanr(sub[feat], sub[target])
            records.append(
                {
                    "Feature": feat,
                    "Lag (years)": lag,
                    "Pearson_r": round(r, 3),
                    "Pearson_p": round(p, 4),
                    "Spearman_r": round(rs, 3),
                    "Spearman_p": round(ps, 4),
                    "N": len(sub),
                    "Sig_Pearson": "Y" if p < threshold else "",
                    "Sig_Spearman": "Y" if ps < threshold else "",
                }
            )

    if not records:
        print(
            "quorum_chat: No feature-lag combinations had enough data "
            "(minimum 5 observations) for correlation analysis. "
            "Check whether HAPI data overlaps with migration years."
        )

    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(
            columns=[
                "Feature",
                "Lag (years)",
                "Pearson_r",
                "Pearson_p",
                "Spearman_r",
                "Spearman_p",
                "N",
                "Sig_Pearson",
                "Sig_Spearman",
            ]
        )

    sig_count = int((df["Pearson_p"] < threshold).sum()) if len(df) else 0

    result = CorrelationResult(
        records=df,
        significant_count=sig_count,
        total_count=len(df),
    )
    validate_block(result, "ICD-AM-001: CorrelationResult")

    print(f"       {result.summary()}")
    return result


# ═════════════════════════════════════════════════════════════════════
# AM-REQ-002: FIXED-EFFECTS PANEL REGRESSION
# ═════════════════════════════════════════════════════════════════════


def run_fixed_effects(
    bundle: LaggedPanelBundle,
    threshold: float = SIGNIFICANCE_THRESHOLD,
) -> FixedEffectsResult:
    """Run bivariate fixed-effects regressions for each feature.

    Each feature is regressed individually against log(outbound_total)
    with country fixed effects (C(iso3) dummies). Features are
    standardized for coefficient comparability.
    """
    print("  [AM] Running fixed-effects panel regressions...")

    panel = bundle.primary_panel.copy()
    panel["country_name"] = panel["iso3"].map(NAME_MAP)

    # Filter to features with sufficient non-null coverage
    available = [
        c for c in bundle.feature_columns if c in panel.columns and panel[c].notna().sum() >= 10
    ]

    if not available:
        print(
            "quorum_chat: No features have at least 10 non-null "
            "observations in the primary panel. Fixed-effects regression "
            "cannot proceed. Check HAPI data coverage."
        )
        empty_df = pd.DataFrame(
            columns=["Feature", "coef", "se", "p", "t", "R2", "N", "Significant"]
        )
        return FixedEffectsResult(coefficients=empty_df, significant_count=0)

    # Standardize features
    scaler = StandardScaler()
    panel_scaled = panel.copy()
    panel_scaled[available] = scaler.fit_transform(
        panel[available].fillna(panel[available].median())
    )
    panel_scaled["log_outbound"] = np.log1p(panel_scaled[bundle.target_column])

    # Run bivariate regressions with country FE
    results = {}
    for feat in available:
        try:
            safe = (
                feat.replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .replace("%", "pct")
                .replace("/", "_per_")
                .replace("+", "plus")
            )
            panel_scaled[safe] = panel_scaled[feat]
            formula = f"log_outbound ~ {safe} + C(iso3)"
            model = smf.ols(formula, data=panel_scaled.dropna(subset=[feat])).fit()
            results[feat] = {
                "coef": round(model.params[safe], 4),
                "se": round(model.bse[safe], 4),
                "p": round(model.pvalues[safe], 4),
                "t": round(model.tvalues[safe], 3),
                "R2": round(model.rsquared, 3),
                "N": int(model.nobs),
            }
        except Exception as e:
            print(f"quorum_chat: Fixed-effects regression failed for '{feat}': {e}")

    if not results:
        print(
            "quorum_chat: All fixed-effects regressions failed. "
            "This may indicate insufficient data variation or "
            "collinearity with country dummies."
        )
        empty_df = pd.DataFrame(
            columns=["Feature", "coef", "se", "p", "t", "R2", "N", "Significant"]
        )
        return FixedEffectsResult(coefficients=empty_df, significant_count=0)

    df = pd.DataFrame(results).T.reset_index().rename(columns={"index": "Feature"})
    df["Significant"] = df["p"] < threshold
    df = df.sort_values("coef", key=abs, ascending=False)

    result = FixedEffectsResult(
        coefficients=df,
        significant_count=int(df["Significant"].sum()),
    )
    validate_block(result, "ICD-AM-002: FixedEffectsResult")

    print(f"       {result.summary()}")
    return result


# ═════════════════════════════════════════════════════════════════════
# AM-REQ-003 to AM-REQ-006: PCA + RANDOM FOREST + SHAP
# ═════════════════════════════════════════════════════════════════════


def run_random_forest(
    bundle: LaggedPanelBundle,
) -> RandomForestResult:
    """PCA dimensionality reduction, Random Forest, and SHAP analysis.

    Pipeline architecture (prevents data leakage):
      Impute (median) -> Scale -> PCA -> Random Forest

    SHAP values are computed in PCA space then back-projected to
    original features via the linear PCA transformation.

    Auto-reduces PCA_COMPONENTS if fewer features are available.
    """
    print("  [AM] Running PCA + Random Forest + SHAP pipeline...")

    panel = bundle.primary_panel.copy()
    feat_cols = [
        c for c in bundle.feature_columns if c in panel.columns and panel[c].notna().sum() >= 10
    ]

    if len(feat_cols) < 2:
        raise ValueError(
            "quorum_chat: Fewer than 2 features with sufficient data "
            "for PCA + Random Forest. Need at least 2 features with "
            f"10+ non-null values. Found {len(feat_cols)} qualifying "
            f"features. Check HAPI data coverage for your countries "
            f"and time window."
        )

    X = panel[feat_cols].values
    y = np.log1p(panel[bundle.target_column].values)
    groups = pd.Categorical(panel["iso3"]).codes
    countries = panel["iso3"].values

    # Auto-reduce PCA components if needed
    n_components = min(PCA_COMPONENTS, len(feat_cols), X.shape[0] - 1)
    if n_components < PCA_COMPONENTS:
        print(
            f"quorum_chat: Reduced PCA components from "
            f"{PCA_COMPONENTS} to {n_components} because only "
            f"{len(feat_cols)} features (or {X.shape[0]} obs) available."
        )

    # Build strict pipeline (no leakage)
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("pca", PCA(n_components=n_components)),
            ("rf", RandomForestRegressor(**RF_PARAMS)),
        ]
    )

    # Leave-one-country-out cross-validation
    logo = LeaveOneGroupOut()
    n_unique_groups = len(np.unique(groups))
    if n_unique_groups < 2:
        print(
            "quorum_chat: Only 1 country group in data. "
            "Cannot perform leave-one-group-out CV. "
            "Using train-only evaluation."
        )
        pipeline.fit(X, y)
        y_pred = pipeline.predict(X)
        train_r2 = r2_score(y, y_pred)
        cv_r2 = np.array([train_r2])
    else:
        cv_r2 = cross_val_score(pipeline, X, y, groups=groups, cv=logo, scoring="r2")
        pipeline.fit(X, y)
        y_pred = pipeline.predict(X)
        train_r2 = r2_score(y, y_pred)

    print(
        f"       Train R2: {train_r2:.3f}  |  LOGO-CV R2: {cv_r2.mean():.3f} +/- {cv_r2.std():.3f}"
    )

    # Extract pipeline stages
    pca_step = pipeline.named_steps["pca"]
    rf_step = pipeline.named_steps["rf"]
    pc_names = [f"PC{i + 1}" for i in range(pca_step.n_components_)]

    # PCA loadings table
    loadings = pd.DataFrame(
        pca_step.components_.T,
        columns=pc_names,
        index=feat_cols,
    )

    print("       PCA component interpretation:")
    for col in loadings.columns:
        top2 = loadings[col].abs().sort_values(ascending=False).head(2).index
        print(f"         {col} driven by: '{top2[0]}' and '{top2[1]}'")

    # Compute intermediate representations for SHAP
    X_imputed = pipeline.named_steps["imputer"].transform(X)
    X_scaled = pipeline.named_steps["scaler"].transform(X_imputed)
    X_pca = pca_step.transform(X_scaled)

    # SHAP in PC space, then back-project to original features
    explainer = shap.TreeExplainer(rf_step)
    shap_pca = explainer.shap_values(X_pca)
    shap_original = shap_pca @ pca_step.components_

    # Mean absolute SHAP per original feature
    shap_abs = pd.DataFrame(np.abs(shap_original), columns=feat_cols)
    mean_shap = shap_abs.mean().sort_values(ascending=False)

    result = RandomForestResult(
        train_r2=train_r2,
        cv_r2_mean=cv_r2.mean(),
        cv_r2_std=cv_r2.std(),
        mean_shap=mean_shap,
        shap_values_original=shap_original,
        X_scaled=X_scaled,
        X_pca=X_pca,
        pca_loadings=loadings,
        feature_names=feat_cols,
        y_actual=y,
        y_predicted=y_pred,
        countries=countries,
    )
    validate_block(result, "ICD-AM-003: RandomForestResult")

    print("       Top SHAP drivers:")
    for feat, val in mean_shap.head(5).items():
        print(f"         {feat}: {val:.4f}")

    return result


# ═════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═════════════════════════════════════════════════════════════════════


def run_analytics_module(
    monthly: MonthlyMigrationBlock,
    bundle: LaggedPanelBundle,
) -> AnalyticsBundle:
    """Execute the full Analytics Module pipeline.

    Takes validated Information Module outputs and runs all analyses.
    """
    print("\n" + "=" * 60)
    print("ANALYTICS MODULE")
    print("=" * 60)

    correlations = run_correlations(bundle)
    fixed_effects = run_fixed_effects(bundle)
    random_forest = run_random_forest(bundle)

    analytics = AnalyticsBundle(
        correlations=correlations,
        fixed_effects=fixed_effects,
        random_forest=random_forest,
        panel_bundle=bundle,
        monthly_migration=monthly,
    )
    validate_block(analytics, "ICD-AM-004: AnalyticsBundle")

    print("\n  [AM] Analytics Module complete.")
    return analytics
