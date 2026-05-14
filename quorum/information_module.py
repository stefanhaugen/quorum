"""
QUORUM Information Module (IM)
===============================
Responsible for all data acquisition, cleaning, harmonization, and
preparation of analytical datasets.

CHANGELOG (v2 API Integration)
------------------------------
- ADDED: _hapi_get() generic paginated API client for HDX HAPI
- ADDED: load_food_security_api() fetches IPC food security data
- ADDED: load_food_prices_api() fetches WFP food price data
- ADDED: merge_hapi_features() combines food security + prices into
         wide-format panel (replaces load_wdi)
- ADDED: JSON caching for API responses to avoid repeated calls
- CHANGED: build_lagged_panels() now accepts HAPIFeatureBlock
- CHANGED: run_information_module() wires new API-based flow
- REMOVED: load_wdi() (WDI replaced by HAPI API data)

Functions in this module correspond to IM requirements:
  IM-REQ-001: Ingest heterogeneous migration data sources
  IM-REQ-002: Ingest food security and price data via HAPI API
  IM-REQ-003: Temporal alignment via configurable lag offsets
  IM-REQ-004: Spatial harmonization (ISO code mapping)
  IM-REQ-005: Quality assurance and ICD validation at each handoff

Every public function returns a validated ICD block (see icd.py).
"""

from __future__ import annotations

import json
import time
import pandas as pd
import numpy as np
import requests
from pathlib import Path
from typing import Dict, List, Optional

from .config import (
    MIGRATION_PATH,
    CA_ISO2,
    CA_ISO3,
    ISO2_TO_ISO3,
    LAG_YEARS,
    PRIMARY_LAG,
    OVERLAP_YEAR_MIN,
    OVERLAP_YEAR_MAX,
    HAPI_BASE_URL,
    HAPI_APP_ID,
    HAPI_PAGE_LIMIT,
    HAPI_TIMEOUT,
    HAPI_ENDPOINTS,
    HAPI_CACHE_DIR,
    IPC_PHASES_OF_INTEREST,
    FEATURE_LABELS,
)

from .icd import (
    MonthlyMigrationBlock,
    AnnualMigrationBlock,
    FoodSecurityBlock,
    FoodPriceBlock,
    HAPIFeatureBlock,
    LaggedPanelBundle,
    validate_block,
)


# ═════════════════════════════════════════════════════════════════════
# HAPI API CLIENT
# ═════════════════════════════════════════════════════════════════════

def _hapi_get(
    endpoint: str,
    params: Optional[Dict] = None,
    use_cache: bool = True,
) -> List[dict]:
    """Generic paginated GET client for the HDX HAPI.

    Fetches all pages of results for the given endpoint and parameters.
    Caches raw JSON responses to disk to avoid repeated API calls
    during iterative development.

    Parameters
    ----------
    endpoint : str
        API path (e.g. "/api/v2/food-security-nutrition-poverty/food-security")
    params : dict, optional
        Additional query parameters beyond app_identifier and limit.
    use_cache : bool
        If True, check for cached response before calling API.

    Returns
    -------
    list of dict
        All records across all pages.
    """
    if params is None:
        params = {}

    # Build cache key from endpoint and params
    cache_key = endpoint.replace("/", "_").strip("_")
    for k, v in sorted(params.items()):
        cache_key += f"_{k}_{v}"
    cache_path = HAPI_CACHE_DIR / f"{cache_key}.json"

    if use_cache and cache_path.exists():
        print(f"       [CACHE HIT] {cache_path.name}")
        with open(cache_path, "r") as f:
            return json.load(f)

    url = f"{HAPI_BASE_URL}{endpoint}"
    all_records = []
    offset = 0
    page = 1

    while True:
        request_params = {
            "app_identifier": HAPI_APP_ID,
            "output_format": "json",
            "limit": HAPI_PAGE_LIMIT,
            "offset": offset,
            **params,
        }

        try:
            resp = requests.get(
                url, params=request_params, timeout=HAPI_TIMEOUT
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            print(
                f"quorum_chat: Connection failed for {endpoint}. "
                f"Check your internet connection and that "
                f"{HAPI_BASE_URL} is reachable.\n"
                f"  Error detail: {e}"
            )
            return all_records
        except requests.exceptions.Timeout:
            print(
                f"quorum_chat: API request timed out after "
                f"{HAPI_TIMEOUT}s for {endpoint} (page {page}). "
                f"Try increasing HAPI_TIMEOUT in config.py."
            )
            return all_records
        except requests.exceptions.HTTPError as e:
            print(
                f"quorum_chat: API returned HTTP error for {endpoint}: "
                f"{resp.status_code} {resp.reason}.\n"
                f"  URL: {resp.url}\n"
                f"  Detail: {resp.text[:500]}"
            )
            return all_records

        payload = resp.json()
        data = payload.get("data", [])

        if not data:
            break

        all_records.extend(data)
        print(
            f"       [API] Page {page}: {len(data)} records "
            f"(total so far: {len(all_records)})"
        )

        if len(data) < HAPI_PAGE_LIMIT:
            break

        offset += HAPI_PAGE_LIMIT
        page += 1
        time.sleep(0.3)  # polite rate limiting

    # Cache result
    if all_records:
        HAPI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(all_records, f)
        print(f"       [CACHE WRITE] {cache_path.name}")

    return all_records


# ═════════════════════════════════════════════════════════════════════
# IM-REQ-001: MIGRATION DATA INGESTION (unchanged from v1)
# ═════════════════════════════════════════════════════════════════════

def load_migration(path: Path = MIGRATION_PATH) -> MonthlyMigrationBlock:
    """Ingest raw Meta migration CSV and produce monthly migration panel.

    Processing steps:
      1. Load raw CSV and drop rows with missing origin/destination
      2. Filter to Dry Corridor countries (CA_ISO2)
      3. Parse date fields and map ISO2 to ISO3
      4. Compute outbound, inbound, and net flows per country-month
      5. Validate output against ICD-IM-001 contract

    Parameters
    ----------
    path : Path
        Location of the international_migration_flow.csv file.

    Returns
    -------
    MonthlyMigrationBlock
        Validated monthly migration panel ready for aggregation.
    """
    print("  [IM] Loading migration data...")

    if not path.exists():
        raise FileNotFoundError(
            f"quorum_chat: Migration file not found at {path}. "
            f"Please ensure the file exists in the for_import/ folder."
        )

    raw = pd.read_csv(path)
    raw = raw.dropna(subset=["country_from", "country_to"])

    # Outbound from CA countries
    mig_out = raw[raw["country_from"].isin(CA_ISO2)].copy()
    mig_out["year"] = mig_out["migration_month"].str[:4].astype(int)
    mig_out["month"] = mig_out["migration_month"].str[5:7].astype(int)
    mig_out["iso3"] = mig_out["country_from"].map(ISO2_TO_ISO3)

    # Inbound to CA countries
    mig_in = raw[raw["country_to"].isin(CA_ISO2)].copy()
    mig_in["year"] = mig_in["migration_month"].str[:4].astype(int)
    mig_in["month"] = mig_in["migration_month"].str[5:7].astype(int)
    mig_in["iso3"] = mig_in["country_to"].map(ISO2_TO_ISO3)

    # Aggregate: outbound total per country-month
    monthly_out = (
        mig_out.groupby(["iso3", "year", "month"])["num_migrants"]
        .sum()
        .reset_index()
        .rename(columns={"num_migrants": "outbound_total"})
    )

    # Aggregate: outbound to US specifically
    mig_us = mig_out[mig_out["country_to"] == "US"]
    monthly_us = (
        mig_us.groupby(["iso3", "year", "month"])["num_migrants"]
        .sum()
        .reset_index()
        .rename(columns={"num_migrants": "outbound_to_us"})
    )

    # Aggregate: inbound total per country-month
    monthly_in = (
        mig_in.groupby(["iso3", "year", "month"])["num_migrants"]
        .sum()
        .reset_index()
        .rename(columns={"num_migrants": "inbound_total"})
    )

    # Merge into unified monthly panel
    monthly = (
        monthly_out
        .merge(monthly_us, on=["iso3", "year", "month"], how="left")
        .merge(monthly_in, on=["iso3", "year", "month"], how="left")
        .fillna(0)
    )
    monthly["net_outbound"] = (
        monthly["outbound_total"] - monthly["inbound_total"]
    )
    monthly["year_month"] = (
        monthly["year"].astype(str)
        + "-"
        + monthly["month"].astype(str).str.zfill(2)
    )

    block = MonthlyMigrationBlock(data=monthly)
    validate_block(block, "ICD-IM-001: MonthlyMigrationBlock")

    print(f"       {block.summary()}")
    return block


# ═════════════════════════════════════════════════════════════════════
# IM-REQ-001 (continued): ANNUAL AGGREGATION (unchanged)
# ═════════════════════════════════════════════════════════════════════

def build_annual_panel(
    monthly: MonthlyMigrationBlock,
) -> AnnualMigrationBlock:
    """Aggregate monthly migration to annual country-level totals."""
    print("  [IM] Aggregating to annual panel...")

    annual = (
        monthly.data.groupby(["iso3", "year"])
        .agg(
            outbound_total=("outbound_total", "sum"),
            outbound_to_us=("outbound_to_us", "sum"),
            inbound_total=("inbound_total", "sum"),
            net_outbound=("net_outbound", "sum"),
            peak_month_out=("outbound_total", "max"),
        )
        .reset_index()
    )

    block = AnnualMigrationBlock(data=annual)
    validate_block(block, "ICD-IM-002: AnnualMigrationBlock")

    print(f"       {block.summary()}")
    return block


# ═════════════════════════════════════════════════════════════════════
# IM-REQ-002: HAPI API DATA INGESTION (NEW in v2)
# ═════════════════════════════════════════════════════════════════════

def load_food_security_api(use_cache: bool = True) -> FoodSecurityBlock:
    """Fetch IPC food security data from HAPI for all CA countries.

    Queries the food-security endpoint for each Dry Corridor country,
    extracts IPC phase populations and fractions, and returns a
    validated FoodSecurityBlock.

    Returns
    -------
    FoodSecurityBlock
        Validated IPC food security panel.
    """
    print("  [IM] Fetching food security data from HAPI API...")

    all_rows = []
    for iso3 in CA_ISO3:
        print(f"       Querying food security for {iso3}...")
        records = _hapi_get(
            HAPI_ENDPOINTS["food_security"],
            params={"location_code": iso3},
            use_cache=use_cache,
        )

        if not records:
            print(
                f"quorum_chat: No food security data returned for "
                f"{iso3}. This country may not be covered by HAPI."
            )
            continue

        for rec in records:
            ref_start = rec.get("reference_period_start", "")
            year = None
            if ref_start and len(ref_start) >= 4:
                try:
                    year = int(ref_start[:4])
                except (ValueError, TypeError):
                    continue

            phase = str(rec.get("ipc_phase", ""))
            pop = rec.get("population_in_phase")
            frac = rec.get("population_fraction_in_phase")

            if year is not None and phase:
                all_rows.append({
                    "iso3": iso3,
                    "year": year,
                    "ipc_phase": phase,
                    "population_in_phase": pop if pop else 0.0,
                    "population_fraction_in_phase": frac if frac else 0.0,
                    "reference_period_start": ref_start,
                    "ipc_type": rec.get("ipc_type", ""),
                })

    df = pd.DataFrame(all_rows)
    if df.empty:
        print(
            "quorum_chat: Food security API returned no data for any "
            "Dry Corridor country. The pipeline will continue but "
            "food security features will be empty."
        )
        df = pd.DataFrame(columns=[
            "iso3", "year", "ipc_phase",
            "population_in_phase", "population_fraction_in_phase",
            "reference_period_start", "ipc_type",
        ])

    block = FoodSecurityBlock(data=df)
    validate_block(block, "ICD-IM-003a: FoodSecurityBlock")

    print(f"       {block.summary()}")
    return block


def load_food_prices_api(use_cache: bool = True) -> FoodPriceBlock:
    """Fetch WFP food price data from HAPI for all CA countries.

    Queries the food-prices-market-monitor endpoint for each Dry
    Corridor country, returning commodity-level prices with market
    and time metadata.

    Returns
    -------
    FoodPriceBlock
        Validated food price panel.
    """
    print("  [IM] Fetching food price data from HAPI API...")

    all_rows = []
    for iso3 in CA_ISO3:
        print(f"       Querying food prices for {iso3}...")
        records = _hapi_get(
            HAPI_ENDPOINTS["food_prices"],
            params={"location_code": iso3},
            use_cache=use_cache,
        )

        if not records:
            print(
                f"quorum_chat: No food price data returned for "
                f"{iso3}. This country may not be covered by HAPI."
            )
            continue

        for rec in records:
            ref_start = rec.get("reference_period_start", "")
            year = None
            if ref_start and len(ref_start) >= 4:
                try:
                    year = int(ref_start[:4])
                except (ValueError, TypeError):
                    continue

            price = rec.get("price")
            if year is not None and price is not None:
                all_rows.append({
                    "iso3": iso3,
                    "year": year,
                    "commodity_name": rec.get("commodity_name", "Unknown"),
                    "commodity_category": rec.get("commodity_category", ""),
                    "price": float(price),
                    "currency_code": rec.get("currency_code", ""),
                    "unit": rec.get("unit", ""),
                    "market_name": rec.get("market_name", ""),
                    "price_type": rec.get("price_type", ""),
                    "price_flag": rec.get("price_flag", ""),
                    "reference_period_start": ref_start,
                })

    df = pd.DataFrame(all_rows)
    if df.empty:
        print(
            "quorum_chat: Food price API returned no data for any "
            "Dry Corridor country. The pipeline will continue but "
            "food price features will be empty."
        )
        df = pd.DataFrame(columns=[
            "iso3", "year", "commodity_name", "commodity_category",
            "price", "currency_code", "unit", "market_name",
            "price_type", "price_flag", "reference_period_start",
        ])

    block = FoodPriceBlock(data=df)
    validate_block(block, "ICD-IM-003b: FoodPriceBlock")

    print(f"       {block.summary()}")
    return block


# ═════════════════════════════════════════════════════════════════════
# IM-REQ-002 (continued): MERGE HAPI FEATURES
# ═════════════════════════════════════════════════════════════════════

def merge_hapi_features(
    food_sec: FoodSecurityBlock,
    food_price: FoodPriceBlock,
) -> HAPIFeatureBlock:
    """Combine food security and food price data into wide-format panel.

    This function replaces the former load_wdi() in the pipeline.
    It aggregates HAPI API data to country-year level and pivots
    into a wide format suitable for the analytical pipeline.

    Processing:
      1. Food security: pivot IPC phases to columns (fraction per phase)
      2. Food prices: aggregate across commodities to country-year stats
      3. Merge both into a single wide panel on (iso3, year)

    Parameters
    ----------
    food_sec : FoodSecurityBlock
    food_price : FoodPriceBlock

    Returns
    -------
    HAPIFeatureBlock
        Wide-format feature panel indexed by iso3 and year.
    """
    print("  [IM] Merging HAPI features into wide panel...")

    frames = []

    # Food security features
    if not food_sec.data.empty:
        fs = food_sec.data.copy()

        # Get the most crisis-relevant aggregate: national-level, latest
        # per country-year. Prefer admin0 (national) data where available.
        # Aggregate by taking the max fraction per phase per country-year.
        fs_agg = (
            fs.groupby(["iso3", "year", "ipc_phase"])
            .agg(
                population_in_phase=("population_in_phase", "sum"),
                population_fraction_in_phase=(
                    "population_fraction_in_phase", "mean"
                ),
            )
            .reset_index()
        )

        # Pivot phase fractions to columns
        frac_pivot = fs_agg.pivot_table(
            index=["iso3", "year"],
            columns="ipc_phase",
            values="population_fraction_in_phase",
            aggfunc="mean",
        ).reset_index()

        # Rename columns
        rename_map = {}
        for col in frac_pivot.columns:
            if col in ("iso3", "year"):
                continue
            rename_map[col] = f"IPC Phase {col} Fraction"
        frac_pivot = frac_pivot.rename(columns=rename_map)

        # Extract Phase 3+ population specifically
        p3plus = fs_agg[fs_agg["ipc_phase"] == "3+"].copy()
        if not p3plus.empty:
            p3plus_yr = (
                p3plus.groupby(["iso3", "year"])
                ["population_in_phase"].sum()
                .reset_index()
                .rename(columns={"population_in_phase": "IPC Phase 3+ Population"})
            )
            frac_pivot = frac_pivot.merge(
                p3plus_yr, on=["iso3", "year"], how="left"
            )

        frames.append(frac_pivot)
        print(f"       Food security: {len(frac_pivot)} country-years")
    else:
        print("       Food security: no data available")

    # Food price features
    if not food_price.data.empty:
        fp = food_price.data.copy()

        # Aggregate across commodities and markets per country-year
        fp_agg = (
            fp.groupby(["iso3", "year"])
            .agg(
                **{
                    "Mean Staple Price (USD)": ("price", "mean"),
                    "Max Staple Price (USD)": ("price", "max"),
                    "Price Volatility (StdDev)": ("price", "std"),
                    "Num Commodities Tracked": ("commodity_name", "nunique"),
                }
            )
            .reset_index()
        )

        frames.append(fp_agg)
        print(f"       Food prices: {len(fp_agg)} country-years")
    else:
        print("       Food prices: no data available")

    # Merge all feature frames
    if not frames:
        print(
            "quorum_chat: No HAPI feature data available for any country. "
            "The pipeline cannot proceed without feature data."
        )
        empty = pd.DataFrame(columns=["iso3", "year"])
        return HAPIFeatureBlock(
            data=empty,
            source_food_security=food_sec,
            source_food_prices=food_price,
        )

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on=["iso3", "year"], how="outer")

    block = HAPIFeatureBlock(
        data=merged,
        source_food_security=food_sec,
        source_food_prices=food_price,
    )
    validate_block(block, "ICD-IM-003: HAPIFeatureBlock")

    print(f"       {block.summary()}")
    return block


# ═════════════════════════════════════════════════════════════════════
# IM-REQ-003 / IM-REQ-004: TEMPORAL ALIGNMENT AND MERGE
# ═════════════════════════════════════════════════════════════════════

def build_lagged_panels(
    annual_mig: AnnualMigrationBlock,
    features: HAPIFeatureBlock,
    lag_years: List[int] = LAG_YEARS,
    primary_lag: int = PRIMARY_LAG,
    year_min: int = OVERLAP_YEAR_MIN,
    year_max: int = OVERLAP_YEAR_MAX,
) -> LaggedPanelBundle:
    """Build merged migration-feature panels at each lag offset.

    For each lag value, feature year is shifted forward by `lag` so that
    features[year t-lag] align with migration[year t]. This tests the
    hypothesis that food security conditions precede migration response.

    Parameters
    ----------
    annual_mig : AnnualMigrationBlock
    features : HAPIFeatureBlock (replaces former WDIBlock)
    lag_years : list of int
    primary_lag : int
    year_min, year_max : int

    Returns
    -------
    LaggedPanelBundle
    """
    print("  [IM] Building lagged merge panels...")

    overlap_mig = annual_mig.data[
        annual_mig.data["year"].between(year_min, year_max)
    ].copy()

    if overlap_mig.empty:
        raise ValueError(
            f"quorum_chat: No migration data found in the overlap window "
            f"{year_min} to {year_max}. Check OVERLAP_YEAR_MIN and "
            f"OVERLAP_YEAR_MAX in config.py."
        )

    migration_cols = [
        "outbound_total", "outbound_to_us", "inbound_total",
        "net_outbound", "peak_month_out",
    ]

    panels: Dict[int, pd.DataFrame] = {}
    for lag in lag_years:
        feat_shifted = features.data.copy()
        feat_shifted["year"] = feat_shifted["year"] + lag
        panel = overlap_mig.merge(
            feat_shifted, on=["iso3", "year"], how="inner"
        )
        panels[lag] = panel
        print(
            f"       Lag {lag}: {len(panel)} rows x {panel.shape[1]} cols"
        )

    if not panels.get(primary_lag, pd.DataFrame()).shape[0]:
        print(
            f"quorum_chat: Primary lag {primary_lag} produced 0 rows. "
            f"This likely means feature year coverage does not overlap "
            f"with migration years when shifted by {primary_lag}. "
            f"Check the HAPI data temporal range."
        )

    # Determine feature columns
    primary = panels.get(primary_lag, pd.DataFrame())
    non_feature = {"iso3", "year"} | set(migration_cols)
    feature_cols = [c for c in primary.columns if c not in non_feature]

    bundle = LaggedPanelBundle(
        panels=panels,
        primary_lag=primary_lag,
        feature_columns=feature_cols,
        target_column="outbound_total",
        migration_columns=migration_cols,
    )
    validate_block(bundle, "ICD-IM-004: LaggedPanelBundle")

    print(f"       {bundle.summary()}")
    return bundle


# ═════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═════════════════════════════════════════════════════════════════════

def run_information_module(
    use_api_cache: bool = True,
) -> tuple[MonthlyMigrationBlock, LaggedPanelBundle]:
    """Execute the full Information Module pipeline.

    Returns both the monthly migration block (needed by Design Module
    for time-series plots) and the lagged panel bundle (needed by
    Analytics Module for all analyses).

    Parameters
    ----------
    use_api_cache : bool
        If True, use cached API responses when available.

    Returns
    -------
    monthly : MonthlyMigrationBlock
    bundle  : LaggedPanelBundle
    """
    print("\n" + "=" * 60)
    print("INFORMATION MODULE")
    print("=" * 60)

    # Step 1: Migration data (from local CSV, unchanged)
    monthly = load_migration()
    annual = build_annual_panel(monthly)

    # Step 2: HAPI API data (replaces WDI)
    food_sec = load_food_security_api(use_cache=use_api_cache)
    food_price = load_food_prices_api(use_cache=use_api_cache)
    features = merge_hapi_features(food_sec, food_price)

    # Step 3: Lagged merge
    bundle = build_lagged_panels(annual, features)

    print("\n  [IM] Information Module complete.")
    return monthly, bundle
