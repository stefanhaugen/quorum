"""Contract tests for QUORUM ICDs.

These tests are the proof that the interface contracts advertised in
icd.py are real and enforced. Every ICD's validate() method is exercised
on both a happy path and at least one failure path.

Run with:
    pytest tests/test_icd_contracts.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from quorum.icd import (
    AnnualMigrationBlock,
    FoodPriceBlock,
    FoodSecurityBlock,
    HAPIFeatureBlock,
    MonthlyMigrationBlock,
    validate_block,
)

# ----- fixtures ------------------------------------------------------------


@pytest.fixture
def good_monthly_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "iso3": ["GTM", "GTM", "HND"],
            "year": [2020, 2020, 2020],
            "month": [1, 2, 1],
            "outbound_total": [100.0, 110.0, 80.0],
            "outbound_to_us": [60.0, 65.0, 50.0],
            "inbound_total": [10.0, 12.0, 8.0],
            "net_outbound": [90.0, 98.0, 72.0],
            "year_month": ["2020-01", "2020-02", "2020-01"],
        }
    )


@pytest.fixture
def good_annual_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "iso3": ["GTM", "HND"],
            "year": [2020, 2020],
            "outbound_total": [1200.0, 900.0],
            "outbound_to_us": [700.0, 550.0],
            "inbound_total": [110.0, 80.0],
            "net_outbound": [1090.0, 820.0],
            "peak_month_out": [150.0, 110.0],
        }
    )


# ----- MonthlyMigrationBlock -----------------------------------------------


def test_monthly_block_validates_clean_data(good_monthly_df):
    block = MonthlyMigrationBlock(data=good_monthly_df)
    assert block.validate() == []


def test_monthly_block_rejects_missing_columns(good_monthly_df):
    bad = good_monthly_df.drop(columns=["net_outbound"])
    errors = MonthlyMigrationBlock(data=bad).validate()
    assert any("Missing columns" in e for e in errors)


def test_monthly_block_rejects_negative_outbound(good_monthly_df):
    bad = good_monthly_df.copy()
    bad.loc[0, "outbound_total"] = -1.0
    errors = MonthlyMigrationBlock(data=bad).validate()
    assert any("Negative" in e for e in errors)


def test_monthly_block_rejects_invalid_month(good_monthly_df):
    bad = good_monthly_df.copy()
    bad.loc[0, "month"] = 13
    errors = MonthlyMigrationBlock(data=bad).validate()
    assert any("Month" in e for e in errors)


def test_monthly_block_rejects_unknown_iso3(good_monthly_df):
    bad = good_monthly_df.copy()
    bad.loc[0, "iso3"] = "ZZZ"
    errors = MonthlyMigrationBlock(data=bad).validate()
    assert any("ISO3" in e for e in errors)


# ----- AnnualMigrationBlock ------------------------------------------------


def test_annual_block_validates_clean_data(good_annual_df):
    assert AnnualMigrationBlock(data=good_annual_df).validate() == []


def test_annual_block_rejects_missing_columns(good_annual_df):
    bad = good_annual_df.drop(columns=["peak_month_out"])
    errors = AnnualMigrationBlock(data=bad).validate()
    assert any("Missing columns" in e for e in errors)


# ----- FoodSecurityBlock ---------------------------------------------------


def test_food_security_block_validates_clean_data():
    df = pd.DataFrame(
        {
            "iso3": ["GTM"],
            "year": [2021],
            "ipc_phase": ["3+"],
            "population_in_phase": [1_000_000.0],
            "population_fraction_in_phase": [0.12],
        }
    )
    assert FoodSecurityBlock(data=df).validate() == []


def test_food_security_block_rejects_empty_dataframe():
    df = pd.DataFrame(
        columns=[
            "iso3",
            "year",
            "ipc_phase",
            "population_in_phase",
            "population_fraction_in_phase",
        ]
    )
    errors = FoodSecurityBlock(data=df).validate()
    assert any("no data" in e.lower() for e in errors)


# ----- FoodPriceBlock ------------------------------------------------------


def test_food_price_block_validates_clean_data():
    df = pd.DataFrame(
        {
            "iso3": ["GTM"],
            "year": [2021],
            "commodity_name": ["Maize"],
            "price": [0.45],
        }
    )
    assert FoodPriceBlock(data=df).validate() == []


def test_food_price_block_rejects_empty_dataframe():
    df = pd.DataFrame(columns=["iso3", "year", "commodity_name", "price"])
    errors = FoodPriceBlock(data=df).validate()
    assert any("no data" in e.lower() for e in errors)


# ----- HAPIFeatureBlock ----------------------------------------------------


def test_hapi_feature_block_rejects_unknown_features():
    fs = FoodSecurityBlock(
        data=pd.DataFrame(
            {
                "iso3": ["GTM"],
                "year": [2021],
                "ipc_phase": ["3+"],
                "population_in_phase": [1.0],
                "population_fraction_in_phase": [0.1],
            }
        )
    )
    fp = FoodPriceBlock(
        data=pd.DataFrame(
            {
                "iso3": ["GTM"],
                "year": [2021],
                "commodity_name": ["Maize"],
                "price": [0.5],
            }
        )
    )
    df = pd.DataFrame(
        {
            "iso3": ["GTM"],
            "year": [2021],
            "unrelated_column": [1.0],
        }
    )
    errors = HAPIFeatureBlock(data=df, source_food_security=fs, source_food_prices=fp).validate()
    assert any("feature" in e.lower() for e in errors)


# ----- validate_block utility ----------------------------------------------


def test_validate_block_raises_on_bad_block(good_monthly_df):
    bad = good_monthly_df.drop(columns=["year_month"])
    with pytest.raises(ValueError, match="ICD validation failed"):
        validate_block(MonthlyMigrationBlock(data=bad), "test")


def test_validate_block_passes_on_good_block(good_monthly_df):
    validate_block(MonthlyMigrationBlock(data=good_monthly_df), "test")
