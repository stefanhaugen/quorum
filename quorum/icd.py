"""
QUORUM Interface Control Documents (ICDs)
==========================================
Formal data contract definitions for inter-module communication.

CHANGELOG (v2 API Integration)
------------------------------
- ADDED: FoodSecurityBlock (ICD-IM-003a) for HAPI IPC data
- ADDED: FoodPriceBlock (ICD-IM-003b) for HAPI food price data
- ADDED: HAPIFeatureBlock (ICD-IM-003) replacing WDIBlock
- CHANGED: LaggedPanelBundle now uses HAPIFeatureBlock instead of WDIBlock
- CHANGED: AnalyticsBundle updated to carry HAPIFeatureBlock metadata
- RETAINED: MonthlyMigrationBlock and AnnualMigrationBlock unchanged
- RETAINED: All Analytics Module output contracts unchanged

Each dataclass below defines an "information block" that flows between
QUORUM modules. These contracts specify required fields, types, and
validation rules.

Module data flow (v2)
---------------------
    Information Module                  Analytics Module
    ──────────────────                 ─────────────────
    load_migration()                   run_correlations(panel)
         │                                  │
         ▼                                  ▼
    MonthlyMigrationBlock              CorrelationResult
         │                                  │
    build_annual_panel()               run_fixed_effects(panel)
         │                                  │
         ▼                                  ▼
    AnnualMigrationBlock               FixedEffectsResult
         │                                  │
    load_food_security_api()           run_random_forest(panel)
    load_food_prices_api()                  │
         │                                  ▼
         ▼                             RandomForestResult
    FoodSecurityBlock                       │
    FoodPriceBlock                          ▼
         │                             AnalyticsBundle -> Design Module
    merge_hapi_features()
         │
         ▼
    HAPIFeatureBlock
         │
    build_lagged_panels()
         │
         ▼
    LaggedPanelBundle
"""

from __future__ import annotations

import dataclasses as dc

import numpy as np
import pandas as pd

from .config import (
    CA_ISO3,
    FEATURE_LABELS,
)

# ═════════════════════════════════════════════════════════════════════
# INFORMATION MODULE OUTPUT CONTRACTS
# ═════════════════════════════════════════════════════════════════════


@dc.dataclass
class MonthlyMigrationBlock:
    """ICD-IM-001: Monthly migration panel for Dry Corridor countries.

    Produced by: information_module.load_migration()
    Consumed by: information_module.build_annual_panel()
                 design_module (time-series visualizations)

    Schema
    ------
    iso3            : str   (one of CA_ISO3)
    year            : int   (e.g. 2019)
    month           : int   (1 to 12)
    outbound_total  : float (>= 0, total emigrants for that month)
    outbound_to_us  : float (>= 0, emigrants to United States)
    inbound_total   : float (>= 0, total immigrants for that month)
    net_outbound    : float (outbound_total minus inbound_total)
    year_month      : str   (formatted as "YYYY-MM")
    """

    data: pd.DataFrame

    REQUIRED_COLUMNS = [
        "iso3",
        "year",
        "month",
        "outbound_total",
        "outbound_to_us",
        "inbound_total",
        "net_outbound",
        "year_month",
    ]

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty list means contract met."""
        errors = []

        missing = set(self.REQUIRED_COLUMNS) - set(self.data.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")

        if errors:
            return errors

        invalid_iso = set(self.data["iso3"].unique()) - set(CA_ISO3)
        if invalid_iso:
            errors.append(f"Unexpected ISO3 codes: {invalid_iso}")

        if self.data["outbound_total"].min() < 0:
            errors.append("Negative values in outbound_total")

        if not self.data["month"].between(1, 12).all():
            errors.append("Month values outside 1 to 12 range")

        return errors

    @property
    def year_range(self) -> str:
        return f"{self.data['year'].min()} to {self.data['year'].max()}"

    @property
    def country_count(self) -> int:
        return self.data["iso3"].nunique()

    @property
    def row_count(self) -> int:
        return len(self.data)

    def summary(self) -> str:
        return (
            f"MonthlyMigrationBlock: {self.row_count} rows, "
            f"{self.country_count} countries, {self.year_range}"
        )


@dc.dataclass
class AnnualMigrationBlock:
    """ICD-IM-002: Annual aggregated migration panel.

    Produced by: information_module.build_annual_panel()
    Consumed by: information_module.build_lagged_panels()

    Schema
    ------
    iso3            : str
    year            : int
    outbound_total  : float (annual sum)
    outbound_to_us  : float (annual sum)
    inbound_total   : float (annual sum)
    net_outbound    : float (annual sum)
    peak_month_out  : float (max monthly outbound in that year)
    """

    data: pd.DataFrame

    REQUIRED_COLUMNS = [
        "iso3",
        "year",
        "outbound_total",
        "outbound_to_us",
        "inbound_total",
        "net_outbound",
        "peak_month_out",
    ]

    def validate(self) -> list[str]:
        errors = []
        missing = set(self.REQUIRED_COLUMNS) - set(self.data.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")
        return errors

    @property
    def year_range(self) -> str:
        return f"{self.data['year'].min()} to {self.data['year'].max()}"

    def summary(self) -> str:
        return f"AnnualMigrationBlock: {len(self.data)} rows, {self.year_range}"


# ─────────────────────────────────────────────────────────────────────
# NEW v2: HAPI API DATA BLOCKS
# ─────────────────────────────────────────────────────────────────────


@dc.dataclass
class FoodSecurityBlock:
    """ICD-IM-003a: IPC food security data from HAPI API.

    Produced by: information_module.load_food_security_api()
    Consumed by: information_module.merge_hapi_features()

    Schema
    ------
    iso3                        : str
    year                        : int
    ipc_phase                   : str (e.g. "3+", "1", "2")
    population_in_phase         : float
    population_fraction_in_phase: float
    reference_period_start      : str
    """

    data: pd.DataFrame

    REQUIRED_COLUMNS = [
        "iso3",
        "year",
        "ipc_phase",
        "population_in_phase",
        "population_fraction_in_phase",
    ]

    def validate(self) -> list[str]:
        errors = []
        missing = set(self.REQUIRED_COLUMNS) - set(self.data.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")
        if errors:
            return errors

        if self.data.empty:
            errors.append(
                "FoodSecurityBlock contains no data. "
                "Check HAPI API connectivity and country coverage."
            )

        return errors

    def summary(self) -> str:
        n_countries = self.data["iso3"].nunique() if not self.data.empty else 0
        return f"FoodSecurityBlock: {len(self.data)} rows, {n_countries} countries"


@dc.dataclass
class FoodPriceBlock:
    """ICD-IM-003b: WFP food price data from HAPI API.

    Produced by: information_module.load_food_prices_api()
    Consumed by: information_module.merge_hapi_features()

    Schema
    ------
    iso3                   : str
    year                   : int
    commodity_name         : str
    commodity_category     : str
    price                  : float
    currency_code          : str
    unit                   : str
    market_name            : str
    reference_period_start : str
    """

    data: pd.DataFrame

    REQUIRED_COLUMNS = [
        "iso3",
        "year",
        "commodity_name",
        "price",
    ]

    def validate(self) -> list[str]:
        errors = []
        missing = set(self.REQUIRED_COLUMNS) - set(self.data.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")
        if errors:
            return errors

        if self.data.empty:
            errors.append(
                "FoodPriceBlock contains no data. Check HAPI API connectivity and country coverage."
            )

        return errors

    def summary(self) -> str:
        n_countries = self.data["iso3"].nunique() if not self.data.empty else 0
        return f"FoodPriceBlock: {len(self.data)} rows, {n_countries} countries"


@dc.dataclass
class HAPIFeatureBlock:
    """ICD-IM-003: Wide-format HAPI feature panel (replaces WDIBlock).

    Produced by: information_module.merge_hapi_features()
    Consumed by: information_module.build_lagged_panels()

    Schema
    ------
    iso3    : str
    year    : int
    <one column per feature label from FEATURE_LABELS>
    """

    data: pd.DataFrame
    source_food_security: FoodSecurityBlock
    source_food_prices: FoodPriceBlock

    REQUIRED_COLUMNS = ["iso3", "year"]

    def validate(self) -> list[str]:
        errors = []
        missing = set(self.REQUIRED_COLUMNS) - set(self.data.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")

        feature_cols = [c for c in self.data.columns if c in FEATURE_LABELS]
        if len(feature_cols) == 0:
            errors.append(
                "No recognized HAPI feature columns found. "
                "API data may not have returned usable features."
            )

        return errors

    @property
    def feature_columns(self) -> list[str]:
        return [c for c in self.data.columns if c in FEATURE_LABELS]

    def summary(self) -> str:
        return (
            f"HAPIFeatureBlock: {len(self.data)} rows, "
            f"{len(self.feature_columns)} features, "
            f"{self.data['year'].min()} to {self.data['year'].max()}"
        )


# ─────────────────────────────────────────────────────────────────────
# LAGGED PANEL BUNDLE (unchanged interface, new data source)
# ─────────────────────────────────────────────────────────────────────


@dc.dataclass
class LaggedPanelBundle:
    """ICD-IM-004: Collection of lagged merge panels.

    The primary output of the Information Module. Contains one merged
    panel per lag value, plus metadata about the merge.

    Produced by: information_module.build_lagged_panels()
    Consumed by: analytics_module (all analysis functions)
                 design_module (panel-level visualizations)
    """

    panels: dict[int, pd.DataFrame]
    primary_lag: int
    feature_columns: list[str]
    target_column: str
    migration_columns: list[str]

    def validate(self) -> list[str]:
        errors = []

        if self.primary_lag not in self.panels:
            errors.append(
                f"Primary lag {self.primary_lag} not in panels "
                f"(available: {list(self.panels.keys())})"
            )

        for lag, panel in self.panels.items():
            if "iso3" not in panel.columns:
                errors.append(f"Lag {lag} panel missing 'iso3'")
            if "year" not in panel.columns:
                errors.append(f"Lag {lag} panel missing 'year'")
            if self.target_column not in panel.columns:
                errors.append(f"Lag {lag} panel missing target '{self.target_column}'")

        return errors

    @property
    def primary_panel(self) -> pd.DataFrame:
        """Convenience accessor for the main analytical dataset."""
        return self.panels[self.primary_lag]

    def summary(self) -> str:
        lines = [f"LaggedPanelBundle (primary_lag={self.primary_lag}):"]
        for lag, panel in sorted(self.panels.items()):
            lines.append(f"  Lag {lag}: {len(panel)} rows x {panel.shape[1]} cols")
        lines.append(f"  Features: {len(self.feature_columns)}")
        lines.append(f"  Target: {self.target_column}")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════
# ANALYTICS MODULE OUTPUT CONTRACTS (unchanged)
# ═════════════════════════════════════════════════════════════════════


@dc.dataclass
class CorrelationResult:
    """ICD-AM-001: Lagged cross-correlation analysis results."""

    records: pd.DataFrame
    significant_count: int
    total_count: int

    REQUIRED_COLUMNS = [
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

    def validate(self) -> list[str]:
        errors = []
        missing = set(self.REQUIRED_COLUMNS) - set(self.records.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")
        return errors

    def summary(self) -> str:
        return (
            f"CorrelationResult: {self.significant_count} significant "
            f"of {self.total_count} total (p < 0.05)"
        )


@dc.dataclass
class FixedEffectsResult:
    """ICD-AM-002: Fixed-effects panel regression results."""

    coefficients: pd.DataFrame
    significant_count: int

    REQUIRED_COLUMNS = ["Feature", "coef", "se", "p", "t", "R2", "N"]

    def validate(self) -> list[str]:
        errors = []
        missing = set(self.REQUIRED_COLUMNS) - set(self.coefficients.columns)
        if missing:
            errors.append(f"Missing columns: {missing}")
        return errors

    def summary(self) -> str:
        return (
            f"FixedEffectsResult: {self.significant_count} significant "
            f"predictors of {len(self.coefficients)}"
        )


@dc.dataclass
class RandomForestResult:
    """ICD-AM-003: PCA + Random Forest + SHAP results."""

    train_r2: float
    cv_r2_mean: float
    cv_r2_std: float
    mean_shap: pd.Series
    shap_values_original: np.ndarray
    X_scaled: np.ndarray
    X_pca: np.ndarray
    pca_loadings: pd.DataFrame
    feature_names: list[str]
    y_actual: np.ndarray
    y_predicted: np.ndarray
    countries: np.ndarray

    def validate(self) -> list[str]:
        errors = []
        n_obs = self.shap_values_original.shape[0]
        if self.X_scaled.shape[0] != n_obs:
            errors.append("X_scaled row count mismatch with SHAP values")
        if len(self.feature_names) != self.shap_values_original.shape[1]:
            errors.append("Feature name count mismatch with SHAP columns")
        return errors

    def summary(self) -> str:
        top3 = list(self.mean_shap.head(3).index)
        return (
            f"RandomForestResult: Train R2={self.train_r2:.3f}, "
            f"CV R2={self.cv_r2_mean:.3f} +/- {self.cv_r2_std:.3f}\n"
            f"  Top SHAP drivers: {', '.join(top3)}"
        )


@dc.dataclass
class AnalyticsBundle:
    """ICD-AM-004: Combined analytics output for the Design Module."""

    correlations: CorrelationResult
    fixed_effects: FixedEffectsResult
    random_forest: RandomForestResult
    panel_bundle: LaggedPanelBundle
    monthly_migration: MonthlyMigrationBlock

    def validate(self) -> list[str]:
        errors = []
        errors.extend(self.correlations.validate())
        errors.extend(self.fixed_effects.validate())
        errors.extend(self.random_forest.validate())
        errors.extend(self.panel_bundle.validate())
        errors.extend(self.monthly_migration.validate())
        return errors

    def summary(self) -> str:
        return "\n".join(
            [
                "AnalyticsBundle:",
                f"  {self.correlations.summary()}",
                f"  {self.fixed_effects.summary()}",
                f"  {self.random_forest.summary()}",
            ]
        )


# ═════════════════════════════════════════════════════════════════════
# VALIDATION UTILITY
# ═════════════════════════════════════════════════════════════════════


def validate_block(block, block_name: str = "") -> None:
    """Run validation on any ICD block and raise if contract is violated.

    This function is called at every module boundary to enforce
    interface contracts. Failed validation halts the pipeline with
    a clear error message from quorum_chat.
    """
    errors = block.validate()
    if errors:
        label = block_name or type(block).__name__
        error_msg = "\n  ".join(errors)
        raise ValueError(f"quorum_chat: ICD validation failed for {label}:\n  {error_msg}")
