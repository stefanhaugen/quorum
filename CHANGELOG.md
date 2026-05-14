# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
- `DataSourceAdapter` abstraction with HDX, World Bank WDI, and Meta migration insights as concrete implementations
- Structured logging with optional JSON output
- Retry semantics on the HAPI client (exponential backoff with jitter)
- Per-run manifest capturing git SHA, config hash, input hashes, and per-module duration
- Containerized release (Dockerfile + GHCR publishing on tagged releases)

## [0.2.0] - 2026-05-14

### Added
- Universal Python project layout: `quorum/` package, `tests/`, `docs/`, `data/`, `outputs/`
- `pyproject.toml` with pinned runtime and dev dependencies
- Contract tests for every ICD `validate()` method
- GitHub Actions CI matrix across Python 3.10, 3.11, 3.12
- `Makefile` with `install`, `fmt`, `lint`, `type`, `test`, `cov`, `run` targets
- `.pre-commit-config.yaml` running ruff format and lint on every commit
- `.env.example` documenting every runtime knob
- Architecture documentation in `docs/architecture.md`

### Changed
- All file paths and runtime parameters in `config.py` are now sourced from environment variables with sensible defaults (was hard-coded absolute paths)
- Module imports converted to relative form inside the `quorum/` package

## [0.1.0] - 2026-04 (thesis defense)

### Added
- Three-module architecture: Information, Analytics, Design
- Formal ICD dataclasses for inter-module contracts (`MonthlyMigrationBlock`, `AnnualMigrationBlock`, `FoodSecurityBlock`, `FoodPriceBlock`, `HAPIFeatureBlock`, `LaggedPanelBundle`, `CorrelationResult`, `FixedEffectsResult`, `RandomForestResult`, `AnalyticsBundle`)
- HDX HAPI integration for IPC food security and WFP food price data
- Meta migration CSV ingestion
- Lagged cross-correlation analysis (Pearson and Spearman)
- Fixed-effects panel regression with country dummies
- PCA + Random Forest + SHAP with leave-one-country-out cross-validation
- Visualization layer producing time-series, heatmaps, SHAP plots, and CSV exports
- JSON cache layer for HAPI responses with `--no-cache` override
