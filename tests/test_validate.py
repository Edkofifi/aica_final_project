"""
Unit tests for pipeline/validate.py.
"""

import sys
import os
import json
import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.validate import (
    validate_dataframe,
    DataQualityError,
    _check_not_empty,
    _check_required_columns,
    _check_no_critical_nulls,
    _check_temp_range,
    _check_precip_non_neg,
    _check_max_gte_min,
    _check_no_future_dates,
)
from pipeline.transform import transform_all_locations


# Fixture helper

def good_df() -> pd.DataFrame:
    """A fully transformed, valid DataFrame."""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures.json")
    with open(fixture_path) as f:
        fixtures = json.load(f)
    return transform_all_locations(fixtures)


# Integration: validate_dataframe
class TestValidateDataframe:

    def test_passes_good_data(self):
        df = good_df()
        result = validate_dataframe(df)
        assert result is df   # same object returned

    def test_raises_on_empty_dataframe(self):
        with pytest.raises(DataQualityError, match="Empty DataFrame"):
            validate_dataframe(pd.DataFrame())

    def test_raises_on_missing_required_column(self):
        df = good_df().drop(columns=["temp_max_c"])
        with pytest.raises(DataQualityError, match="Required columns"):
            validate_dataframe(df)

    def test_raises_on_critical_nulls(self):
        df = good_df().copy()
        df.loc[0, "temp_max_c"] = None
        with pytest.raises(DataQualityError, match="Nulls in critical columns"):
            validate_dataframe(df)


# Individual checks
class TestCheckNotEmpty:
    def test_passes_non_empty(self):
        ok, _ = _check_not_empty(good_df())
        assert ok is True

    def test_fails_empty(self):
        ok, msg = _check_not_empty(pd.DataFrame())
        assert ok is False
        assert "empty" in msg.lower()


class TestCheckRequiredColumns:
    def test_passes_complete(self):
        ok, _ = _check_required_columns(good_df())
        assert ok is True

    def test_fails_missing_column(self):
        df = good_df().drop(columns=["precipitation_mm"])
        ok, msg = _check_required_columns(df)
        assert ok is False
        assert "precipitation_mm" in msg


class TestCheckNoCriticalNulls:
    def test_passes_no_nulls(self):
        ok, _ = _check_no_critical_nulls(good_df())
        assert ok is True

    def test_fails_with_null_temp(self):
        df = good_df().copy()
        df.loc[0, "temp_max_c"] = None
        ok, msg = _check_no_critical_nulls(df)
        assert ok is False
        assert "temp_max_c" in msg


class TestCheckTempRange:
    def test_passes_valid_temps(self):
        ok, _ = _check_temp_range(good_df())
        assert ok is True

    def test_fails_above_max(self):
        df = good_df().copy()
        df.loc[0, "temp_max_c"] = 70.0   # above 60°C limit
        ok, msg = _check_temp_range(df)
        assert ok is False

    def test_fails_below_min(self):
        df = good_df().copy()
        df.loc[0, "temp_min_c"] = -70.0  # below -60°C limit
        ok, msg = _check_temp_range(df)
        assert ok is False


class TestCheckPrecipNonNeg:
    def test_passes_non_negative(self):
        ok, _ = _check_precip_non_neg(good_df())
        assert ok is True

    def test_fails_negative(self):
        df = good_df().copy()
        df.loc[0, "precipitation_mm"] = -1.0
        ok, _ = _check_precip_non_neg(df)
        assert ok is False


class TestCheckMaxGteMin:
    def test_passes_valid(self):
        ok, _ = _check_max_gte_min(good_df())
        assert ok is True

    def test_fails_when_max_below_min(self):
        df = good_df().copy()
        df.loc[0, "temp_max_c"] = 10.0
        df.loc[0, "temp_min_c"] = 25.0
        ok, _ = _check_max_gte_min(df)
        assert ok is False


class TestCheckNoFutureDates:
    def test_passes_past_dates(self):
        ok, _ = _check_no_future_dates(good_df())
        assert ok is True

    def test_fails_future_date(self):
        df = good_df().copy()
        from datetime import date
        df.loc[0, "date"] = date(2099, 1, 1)
        ok, msg = _check_no_future_dates(df)
        assert ok is False
        assert "future" in msg.lower()
