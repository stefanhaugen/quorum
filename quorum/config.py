"""
QUORUM Configuration
====================
Single source of truth for all system-level parameters.

All paths and runtime knobs come from environment variables with sensible
defaults. Copy .env.example to .env and edit to match your machine.

CHANGELOG (v2.1 Externalized Config)
------------------------------------
- CHANGED: All file paths now read from QUORUM_* environment variables
- CHANGED: HAPI parameters now read from QUORUM_HAPI_* environment variables
- ADDED: Analysis window now configurable via QUORUM_OVERLAP_YEAR_*
- ADDED: Cache TTL via QUORUM_CACHE_TTL_HOURS
- RETAINED: Every public name imported elsewhere (ISO2_TO_ISO3, FEATURE_LABELS, etc.)
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional; envs may also be set by the shell or CI.
    pass


def _env_path(key: str, default: str) -> Path:
    return Path(os.environ.get(key, default)).expanduser().resolve()


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))


# ─────────────────────────────────────────────────────────────────────
# FILE PATHS
# ─────────────────────────────────────────────────────────────────────
DATA_DIR = _env_path("QUORUM_DATA_DIR", "./data")
OUTPUT_DIR = _env_path("QUORUM_OUTPUT_DIR", "./outputs")

MIGRATION_FILENAME = os.environ.get("QUORUM_MIGRATION_FILENAME", "international_migration_flow.csv")
MIGRATION_PATH = DATA_DIR / MIGRATION_FILENAME

# Legacy WDI path kept for backward compatibility
WDI_PATH = DATA_DIR / "20_25_merged.xlsx"


# ─────────────────────────────────────────────────────────────────────
# HDX HAPI API CONFIGURATION
# ─────────────────────────────────────────────────────────────────────
HAPI_BASE_URL = os.environ.get("QUORUM_HAPI_BASE_URL", "https://hapi.humdata.org")
HAPI_APP_ID = os.environ.get("QUORUM_HAPI_APP_ID", "quorum_thesis")
HAPI_PAGE_LIMIT = _env_int("QUORUM_HAPI_PAGE_LIMIT", 1000)
HAPI_TIMEOUT = _env_int("QUORUM_HAPI_TIMEOUT", 30)

HAPI_ENDPOINTS = {
    "food_security": "/api/v2/food-security-nutrition-poverty/food-security",
    "food_prices": "/api/v2/food-security-nutrition-poverty/food-prices-market-monitor",
}

HAPI_CACHE_DIR = OUTPUT_DIR / "hapi_cache"
CACHE_TTL_HOURS = _env_int("QUORUM_CACHE_TTL_HOURS", 168)  # 7 days


# ─────────────────────────────────────────────────────────────────────
# GEOGRAPHIC SCOPE
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
# HAPI FEATURE DEFINITIONS (unchanged)
# ─────────────────────────────────────────────────────────────────────
IPC_PHASES_OF_INTEREST = ["1", "2", "3", "4", "5", "3+"]

FOOD_SECURITY_FEATURES = [
    "IPC Phase 3+ Fraction",
    "IPC Phase 3+ Population",
    "IPC Phase 1 Fraction",
    "IPC Phase 2 Fraction",
    "IPC Phase 3 Fraction",
    "IPC Phase 4 Fraction",
    "IPC Phase 5 Fraction",
]

FOOD_PRICE_FEATURES = [
    "Mean Staple Price (USD)",
    "Max Staple Price (USD)",
    "Price Volatility (StdDev)",
    "Num Commodities Tracked",
]

FEATURE_LABELS = FOOD_SECURITY_FEATURES + FOOD_PRICE_FEATURES


# ─────────────────────────────────────────────────────────────────────
# ANALYSIS PARAMETERS
# ─────────────────────────────────────────────────────────────────────
LAG_YEARS = [0, 1, 2]
PRIMARY_LAG = _env_int("QUORUM_PRIMARY_LAG", 1)
OVERLAP_YEAR_MIN = _env_int("QUORUM_OVERLAP_YEAR_MIN", 2020)
OVERLAP_YEAR_MAX = _env_int("QUORUM_OVERLAP_YEAR_MAX", 2022)
SIGNIFICANCE_THRESHOLD = _env_float("QUORUM_SIGNIFICANCE_THRESHOLD", 0.05)

RF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 3,
    "min_samples_leaf": 4,
    "max_features": "sqrt",
    "random_state": 42,
    "n_jobs": -1,
}
PCA_COMPONENTS = 3


# ─────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("QUORUM_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.environ.get("QUORUM_LOG_FORMAT", "human").lower()


# ─────────────────────────────────────────────────────────────────────
# VISUAL IDENTITY (unchanged)
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
