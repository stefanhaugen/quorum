"""Shared pytest fixtures for the QUORUM test suite."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the directory holding small CSV fixtures."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tiny_migration_path(fixtures_dir: Path) -> Path:
    """Path to a tiny Meta-format migration CSV used by ingestion tests."""
    return fixtures_dir / "tiny_migration.csv"


@pytest.fixture
def tiny_migration_df(tiny_migration_path: Path) -> pd.DataFrame:
    """Loaded form of the tiny migration fixture."""
    return pd.read_csv(tiny_migration_path)
