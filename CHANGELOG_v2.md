# QUORUM v2 Changelog: HDX HAPI API Integration

## Summary

Replaced the World Development Indicators (WDI) Excel-based data stream
with live API calls to the HDX Humanitarian API (HAPI), sourcing IPC food
security and WFP food price data for all 7 Central American Dry Corridor
countries. Migration data ingestion (from Meta CSV) is unchanged.

Data paths updated from `thesis_data/` to `thesis_data/for_import/`.

All user-facing error messages now carry the `quorum_chat:` prefix.

---

## config.py

| Change | Detail |
|--------|--------|
| ADDED | `HAPI_BASE_URL`, `HAPI_APP_ID`, `HAPI_PAGE_LIMIT`, `HAPI_TIMEOUT` |
| ADDED | `HAPI_ENDPOINTS` dict with `food_security` and `food_prices` paths |
| ADDED | `HAPI_CACHE_DIR` for JSON response caching |
| ADDED | `IPC_PHASES_OF_INTEREST` list for IPC phase extraction |
| ADDED | `FOOD_SECURITY_FEATURES` and `FOOD_PRICE_FEATURES` lists |
| CHANGED | `DATA_DIR` now points to `thesis_data/for_import/` |
| CHANGED | `MIGRATION_PATH` updated to use new `DATA_DIR` |
| CHANGED | `FEATURE_LABELS` now combines food security and food price labels |
| REMOVED | `FEATURE_CODES` dict (WDI indicator codes no longer needed) |

## icd.py

| Change | Detail |
|--------|--------|
| ADDED | `FoodSecurityBlock` (ICD-IM-003a): IPC phase populations from HAPI |
| ADDED | `FoodPriceBlock` (ICD-IM-003b): WFP commodity prices from HAPI |
| ADDED | `HAPIFeatureBlock` (ICD-IM-003): Wide-format merged features (replaces `WDIBlock`) |
| CHANGED | `LaggedPanelBundle` now works with `HAPIFeatureBlock` instead of `WDIBlock` |
| RETAINED | `MonthlyMigrationBlock`, `AnnualMigrationBlock` unchanged |
| RETAINED | `CorrelationResult`, `FixedEffectsResult`, `RandomForestResult`, `AnalyticsBundle` unchanged |
| RETAINED | `validate_block()` utility unchanged |

## information_module.py

| Change | Detail |
|--------|--------|
| ADDED | `_hapi_get()`: Generic paginated API client with caching, rate limiting, and error handling |
| ADDED | `load_food_security_api()`: Fetches IPC data for all 7 CA countries via HAPI |
| ADDED | `load_food_prices_api()`: Fetches WFP food price data for all 7 CA countries via HAPI |
| ADDED | `merge_hapi_features()`: Pivots food security by IPC phase, aggregates food prices, merges into wide panel |
| CHANGED | `build_lagged_panels()`: Accepts `HAPIFeatureBlock` instead of `WDIBlock` |
| CHANGED | `run_information_module()`: Wires new API flow (replaced `load_wdi()` call) |
| CHANGED | Accepts `use_api_cache` parameter to control caching behavior |
| REMOVED | `load_wdi()` function (WDI no longer used) |
| RETAINED | `load_migration()`, `build_annual_panel()` unchanged |

## analytics_module.py

| Change | Detail |
|--------|--------|
| CHANGED | All error messages now use `quorum_chat:` prefix |
| CHANGED | `run_correlations()`: Handles empty results gracefully |
| CHANGED | `run_fixed_effects()`: Handles NaN-heavy features, filters to 10+ obs |
| CHANGED | `run_random_forest()`: Auto-reduces PCA components if fewer features available |
| CHANGED | `run_random_forest()`: Handles single-country-group edge case |
| RETAINED | All analytical algorithms identical (Pearson/Spearman, FE regression, PCA+RF+SHAP) |

## design_module.py

| Change | Detail |
|--------|--------|
| CHANGED | All plot titles reference "HAPI Features" instead of "WDI" |
| CHANGED | Correlation heatmap title updated for food security context |
| CHANGED | SHAP plots reference "HAPI Food Security/Price Features" |
| CHANGED | All functions handle empty result sets with `quorum_chat:` messages |
| CHANGED | `plot_correlation_heatmap()` and `plot_fixed_effects()` return `None` if no data |
| RETAINED | All output filenames (3A_, 3B_, 3C_, etc.) unchanged |
| RETAINED | All visualization logic and styling unchanged |

## main.py

| Change | Detail |
|--------|--------|
| ADDED | `--no-cache` CLI flag to bypass API cache |
| ADDED | Per-module and total timing report |
| CHANGED | Error handling uses `quorum_chat:` prefix |
| CHANGED | Header banner says "HDX HAPI" instead of "WDI" |
| RETAINED | Module boundary enforcement via `validate_block()` |

---

## Architecture Notes

**Modularity preserved**: The three-module boundary architecture is intact.
The Information Module is the only module that knows about the HAPI API.
The Analytics Module receives ICD-validated DataFrames and has no knowledge
of data sources. The Design Module receives validated analytical results
and has no knowledge of data loading or analysis logic.

**API caching**: First run fetches data from HAPI and saves JSON files to
`quorum_outputs/hapi_cache/`. Subsequent runs use cached data unless
`--no-cache` is passed. This avoids unnecessary API calls during
iterative development.

**Potential gaps to note**:
1. The HAPI food-security endpoint provides IPC phase data, but Central
   American countries may have sparse coverage in HAPI depending on when
   IPC assessments were conducted. If the overlap with migration years
   (2020 to 2022) is thin, the panel will be small.
2. Food prices from WFP are typically monthly, aggregated here to annual
   means, maxes, and volatility. The original monthly granularity is
   available in the `FoodPriceBlock` if finer-grained analysis is desired.
3. The `--no-cache` flag requires live network access to `hapi.humdata.org`.
