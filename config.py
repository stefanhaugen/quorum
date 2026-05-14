"""
QUORUM Configuration
====================
Single source of truth for all system-level parameters.

Every configurable assumption lives here: file paths, country scope,
HAPI API settings, analysis settings, and visual identity.

CHANGELOG (v2 API Integration)
------------------------------
- ADDED: HAPI_BASE_URL, HAPI_APP_ID, HAPI_ENDPOINTS for HDX HAPI
- ADDED: HAPI_CACHE_DIR for caching API responses during development
- ADDED: FOOD_SECURITY_FEATURES and FOOD_PRICE_FEATURES replacing WDI
- CHANGED: DATA_DIR now points to thesis_data/for_import/ subfolder
- CHANGED: MIGRATION_PATH updated to for_import/ subfolder
- REMOVED: FEATURE_CODES dict (replaced by HAPI-derived feature labels)

When documenting parameter choices in the thesis, reference this file
by section. Each constant group maps to a traceable design decision.
"""

from pathlib import Path


# ─────────────────────────────────────────────────────────────────────
# FILE PATHS (updated: now uses for_import/ subfolder)
# ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path(
    "/Users/stefanhaugen/Documents/Stefan Haugen/CSU/Thesis/"
    "thesis_data/for_import"
)
MIGRATION_PATH = DATA_DIR / "international_migration_flow.csv"

OUTPUT_DIR = Path(
    "/Users/stefanhaugen/Documents/Stefan Haugen/CSU/Thesis/"
    "thesis_data/quorum_outputs"
)

# Legacy WDI path kept for backward compatibility if needed
WDI_PATH = DATA_DIR / "20_25_merged.xlsx"


# ─────────────────────────────────────────────────────────────────────
# HDX HAPI API CONFIGURATION
# Base: https://hapi.humdata.org
# Docs: https://hapi.humdata.org/docs
# ─────────────────────────────────────────────────────────────────────
HAPI_BASE_URL = "https://hapi.humdata.org"
HAPI_APP_ID = "quorum_thesis"      # required app_identifier parameter
HAPI_PAGE_LIMIT = 1000             # max records per request page
HAPI_TIMEOUT = 30                  # seconds per request

HAPI_ENDPOINTS = {
    "food_security": "/api/v2/food-security-nutrition-poverty/food-security",
    "food_prices": "/api/v2/food-security-nutrition-poverty/food-prices-market-monitor",
}

# Cache directory for API responses (avoids repeated calls during dev)
HAPI_CACHE_DIR = OUTPUT_DIR / "hapi_cache"


# ─────────────────────────────────────────────────────────────────────
# GEOGRAPHIC SCOPE
# Central American Dry Corridor: 7 countries
# ─────────────────────────────────────────────────────────────────────
ISO2_TO_ISO3 = {
    "BZ": "BLZ",
    "CR": "CRI",
    "GT": "GTM",
    "HN": "HND",
    "NI": "NIC",
    "PA": "PAN",
    "SV": "SLV",
}

CA_ISO2 = list(ISO2_TO_ISO3.keys())
CA_ISO3 = list(ISO2_TO_ISO3.values())

NAME_MAP = {
    "BLZ": "Belize",
    "CRI": "Costa Rica",
    "GTM": "Guatemala",
    "HND": "Honduras",
    "NIC": "Nicaragua",
    "PAN": "Panama",
    "SLV": "El Salvador",
}


# ─────────────────────────────────────────────────────────────────────
# HAPI FEATURE DEFINITIONS
# These replace the former WDI FEATURE_CODES.
# Food security features are derived from IPC phase populations.
# Food price features are derived from WFP commodity price data.
# ─────────────────────────────────────────────────────────────────────

# IPC phases we extract population fractions for
IPC_PHASES_OF_INTEREST = ["1", "2", "3", "4", "5", "3+"]

# Human-readable labels for food security features (generated per phase)
FOOD_SECURITY_FEATURES = [
    "IPC Phase 3+ Fraction",
    "IPC Phase 3+ Population",
    "IPC Phase 1 Fraction",
    "IPC Phase 2 Fraction",
    "IPC Phase 3 Fraction",
    "IPC Phase 4 Fraction",
    "IPC Phase 5 Fraction",
]

# Food price features (aggregated across commodities per country-year)
FOOD_PRICE_FEATURES = [
    "Mean Staple Price (USD)",
    "Max Staple Price (USD)",
    "Price Volatility (StdDev)",
    "Num Commodities Tracked",
]

# Combined feature labels for the analytical pipeline
FEATURE_LABELS = FOOD_SECURITY_FEATURES + FOOD_PRICE_FEATURES


# ─────────────────────────────────────────────────────────────────────
# ANALYSIS PARAMETERS
# ─────────────────────────────────────────────────────────────────────
LAG_YEARS = [0, 1, 2]          # same-year, 1-year lag, 2-year lag
PRIMARY_LAG = 1                 # main analytical dataset per thesis theory
OVERLAP_YEAR_MIN = 2020         # migration-feature overlap window start
OVERLAP_YEAR_MAX = 2022         # migration-feature overlap window end
SIGNIFICANCE_THRESHOLD = 0.05   # p-value cutoff for flagging significance

# Random Forest hyperparameters (constrained for small-N honesty)
RF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 3,
    "min_samples_leaf": 4,
    "max_features": "sqrt",
    "random_state": 42,
    "n_jobs": -1,
}
PCA_COMPONENTS = 3              # dimensionality reduction target


# ─────────────────────────────────────────────────────────────────────
# VISUAL IDENTITY
# Consistent palette across all Design Module outputs
# ─────────────────────────────────────────────────────────────────────
PALETTE = {
    "BLZ": "#1f77b4",
    "CRI": "#ff7f0e",
    "GTM": "#2ca02c",
    "HND": "#d62728",
    "NIC": "#9467bd",
    "PAN": "#8c564b",
    "SLV": "#e377c2",
}
