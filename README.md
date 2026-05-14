# QUORUM

**Quantitative Understanding of Regional Outmigration Using Multivariate data**

[![CI](https://github.com/stefanhaugen/quorum/actions/workflows/ci.yml/badge.svg)](https://github.com/stefanhaugen/quorum/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

QUORUM is a systems-engineered pipeline that turns publicly available environmental, food security, and human-mobility data into reproducible migration-risk indicators. It was built to give policymakers and affected communities analytical tools that anticipate displacement pressures in the Water-Energy-Food (WEF) nexus, a documented gap in the literature.

The pipeline is structured around formal Interface Control Documents (ICDs) at every module boundary, leave-one-country-out cross-validation, SHAP-based feature attribution, and pluggable data-source adapters (HDX HAPI today, World Bank and Meta migration insights on the roadmap).

> Built as a Master's thesis in Systems Engineering at Colorado State University. Defended 2026.

---

## Why this exists

No existing WEF nexus model treats migration as a thematic focus. The result is that field actors and policymakers in regions like the Central American Dry Corridor lack analytical tools to anticipate displacement pressure. QUORUM addresses that gap with a transparent, reproducible architecture that processes open data through requirements-traceable analytics.

---

## Quickstart

```bash
git clone https://github.com/stefanhaugen/quorum.git
cd quorum
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then edit paths to point at your data
python -m quorum              # runs the full pipeline
python -m quorum --no-cache   # bypasses the local API cache
```

Pipeline outputs land in `$QUORUM_OUTPUT_DIR` (defaults to `./outputs`).

---

## Architecture

```mermaid
flowchart LR
    subgraph IM[Information Module]
        A1[Meta migration CSV] --> B1[MonthlyMigrationBlock]
        A2[HDX HAPI food security] --> B2[FoodSecurityBlock]
        A3[HDX HAPI food prices] --> B3[FoodPriceBlock]
        B1 --> C1[AnnualMigrationBlock]
        B2 --> C2[HAPIFeatureBlock]
        B3 --> C2
        C1 --> D[LaggedPanelBundle]
        C2 --> D
    end
    subgraph AM[Analytics Module]
        D --> E1[CorrelationResult]
        D --> E2[FixedEffectsResult]
        D --> E3[RandomForestResult]
        E1 --> F[AnalyticsBundle]
        E2 --> F
        E3 --> F
    end
    subgraph DM[Design Module]
        F --> G1[Time-series figures]
        F --> G2[Correlation heatmap]
        F --> G3[SHAP plots]
        F --> G4[CSV exports]
    end
    style IM fill:#eef
    style AM fill:#efe
    style DM fill:#fee
```

Each arrow crosses a contract. The contracts are dataclasses with `validate()` methods in `quorum/icd.py`. `validate_block()` raises at every module boundary if a contract is violated. Modules know nothing about each other beyond their ICDs.

---

## Modules

| Module | Responsibility | Knows about |
|---|---|---|
| **Information** (`information_module.py`) | Data ingestion, harmonization, temporal alignment | Data sources, file paths, APIs |
| **Analytics** (`analytics_module.py`) | Correlation, fixed-effects panel regression, PCA + Random Forest + SHAP | Statistics, ML, ICDs |
| **Design** (`design_module.py`) | Visualization, CSV export, human-systems integration | Plotting, output paths, ICDs |

---

## Data sources

| Source | Adapter | Indicators | Status |
|---|---|---|---|
| HDX HAPI | `hdx_food_security` | IPC phase populations and fractions | Active |
| HDX HAPI | `hdx_food_prices` | WFP commodity prices | Active |
| Meta Data for Good | `meta_migration` | Monthly bilateral migration flows | Active (local CSV) |
| World Bank Open Data | `world_bank_wdi` | Selected WDI codes | Roadmap |
| CSIC SPEI | `spei_drought` | Drought severity (multi-month) | Roadmap |
| WRI Aqueduct | `aqueduct_water_stress` | Baseline and projected water stress | Roadmap |

Adding a new source means implementing one `DataSourceAdapter` subclass. The analytical core does not change.

---

## Methodology highlights

- **No leakage** in cross-validation. `Impute -> Scale -> PCA -> RandomForest` is a single sklearn `Pipeline`, refit on every training fold.
- **Leave-One-Group-Out CV** at country granularity for honest generalization estimates on a small panel.
- **Constrained Random Forest** (`max_depth=3`, `min_samples_leaf=4`) appropriate for small-N regimes.
- **SHAP back-projection**: explanations computed in PC space and projected back to original feature space via the linear PCA transformation.
- **Bivariate fixed-effects regressions** with country dummies and standardized features for coefficient comparability.

Full methodology in [`docs/whitepaper.md`](docs/whitepaper.md). Full thesis in [`docs/QUORUM_thesis.pdf`](docs/QUORUM_thesis.pdf).

---

## Development

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy quorum
pytest --cov=quorum --cov-report=term-missing
```

Pre-commit hooks are configured in `.pre-commit-config.yaml`. Install with `pre-commit install`.

---

## Configuration

All paths and runtime knobs are environment variables. See [`.env.example`](.env.example) for the full list. Common ones:

| Variable | Purpose | Default |
|---|---|---|
| `QUORUM_DATA_DIR` | Input data directory | `./data` |
| `QUORUM_OUTPUT_DIR` | Output directory | `./outputs` |
| `QUORUM_HAPI_APP_ID` | HDX HAPI app identifier | `quorum_thesis` |
| `QUORUM_HAPI_TIMEOUT` | API timeout in seconds | `30` |
| `QUORUM_LOG_LEVEL` | Logging verbosity | `INFO` |

---

## Project status and roadmap

- [x] Three-module architecture with formal ICDs
- [x] HDX HAPI integration (food security and food prices)
- [x] Random Forest + SHAP with LOGO cross-validation
- [ ] Pluggable adapter pattern for arbitrary data sources
- [ ] World Bank WDI adapter
- [ ] Meta migration insights adapter
- [ ] Structured logging, retry semantics, cache TTL
- [ ] Per-run manifest (git SHA, config hash, input hashes)
- [ ] Containerized release

---

## Citation

If you use QUORUM in academic work, please cite:

> Haugen, S. (2026). *QUORUM: A Systems Engineering Framework for Migration Risk Assessment.* Master's thesis, Department of Systems Engineering, Colorado State University.

---

## License

MIT. See [`LICENSE`](LICENSE).
