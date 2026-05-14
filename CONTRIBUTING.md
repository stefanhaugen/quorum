# Contributing to QUORUM

Thanks for considering a contribution. QUORUM is a humanitarian engineering project, and the goal is to keep the codebase readable, the contracts honest, and the methodology auditable. Bug reports, documentation improvements, new data-source adapters, and methodological reviews are all welcome.

## Quick start

```bash
git clone https://github.com/stefanhaugen/quorum.git
cd quorum
make install
make hooks
make test
```

## Development workflow

1. Fork and branch from `main`. Branch names should be short and topical, for example `adapter/world-bank-wdi` or `fix/cache-ttl`.
2. Write or update tests before changing behavior. Every ICD has a `validate()` method that should be exercised in both happy-path and failure-path tests.
3. Run the local quality gates before opening a PR:
   ```bash
   make fmt
   make lint
   make type
   make test
   ```
4. Open a PR with a description that explains the change and (where relevant) cites the requirement code (IM-REQ, AM-REQ, DM-REQ) or the section of the thesis the change implements.

## Adding a new data source

Adding a source should not require changes to the Analytics or Design modules. The roadmap is to add a `DataSourceAdapter` abstraction in the Information Module; until that lands, new sources should follow the existing pattern in `quorum/information_module.py`:

1. Implement a `load_<source>_api()` function that returns a validated ICD block
2. Add corresponding `*Block` dataclasses in `quorum/icd.py` with `REQUIRED_COLUMNS` and a `validate()` method
3. Wire the new block into `merge_*_features()` and through to `LaggedPanelBundle`
4. Add a contract test in `tests/`
5. Update the data sources table in `README.md` and the architecture diagram in `docs/architecture.md`

## Code style

- Line length 100
- `ruff format` is the canonical formatter (black-compatible)
- Type hints encouraged on every public function
- Docstrings on public functions should cite the requirement code

## Reporting issues

Use the GitHub issue tracker. For data-quality reports, include the source URL or HAPI endpoint, the country and time range, and a snippet of the offending payload if possible.

## License

By contributing you agree that your contributions are licensed under the MIT License of this project.
