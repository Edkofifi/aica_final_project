"""
Unit tests for pipeline/transform.py.
"""

import sys
import os
import json
import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.transform import (
    transform_all_locations,
    _flatten_to_dataframe,
    _clean_column_names,
    _parse_dates,
    _cast_numeric_types,
    _handle_missing_values,
    _remove_duplicates,
    _validate_measurements,
    _create_derived_fields,
    _standardize_location_name,
    _check_required_columns,
)


# Fixture helpers
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures.json")

def load_fixtures():
    with open(FIXTURE_PATH) as f:
        return json.load(f)

def single_location_fixture():
    """Return just the first fixture (Accra)."""
    return load_fixtures()[0]

# Integration test 
class TestTransformAllLocations:

    def test_returns_dataframe(self):
        df = transform_all_locations(load_fixtures())
        assert isinstance(df, pd.DataFrame)

    def test_all_locations_present(self):
        df = transform_all_locations(load_fixtures())
        names = set(df["location_name"].unique())
        assert names == {"Accra", "Kumasi", "London", "Lagos"}

    def test_correct_row_count(self):
        # 4 locations × 7 days each = 28 rows
        df = transform_all_locations(load_fixtures())
        assert len(df) == 28

    def test_no_nulls_in_critical_columns(self):
        df = transform_all_locations(load_fixtures())
        critical = ["date", "location_name", "temp_max_c", "temp_min_c", "precipitation_mm"]
        for col in critical:
            assert df[col].isna().sum() == 0, f"Nulls found in {col}"

    def test_derived_columns_present(self):
        df = transform_all_locations(load_fixtures())
        for col in ["temp_range_c", "is_rainy_day", "season", "temp_category", "data_quality"]:
            assert col in df.columns


# T1 — Column name cleaning
class TestCleanColumnNames:

    def test_renames_api_columns(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        assert "temp_max_c" in df.columns
        assert "temperature_2m_max" not in df.columns

    def test_no_spaces_in_column_names(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        for col in df.columns:
            assert " " not in col

    def test_all_columns_lowercase(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        for col in df.columns:
            assert col == col.lower()


# T2 — Date parsing
class TestParseDates:

    def _get_df(self):
        df = _flatten_to_dataframe(single_location_fixture())
        return _clean_column_names(df)

    def test_date_column_is_date_type(self):
        df = _parse_dates(self._get_df())
        import datetime
        assert isinstance(df["date"].iloc[0], datetime.date)

    def test_date_values_are_correct(self):
        df = _parse_dates(self._get_df())
        assert str(df["date"].iloc[0]) == "2025-06-01"


# T3 — Numeric types
class TestCastNumericTypes:

    def _pipeline(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df = _parse_dates(df)
        return _cast_numeric_types(df)

    def test_temp_columns_are_float64(self):
        df = self._pipeline()
        assert df["temp_max_c"].dtype == "float64"
        assert df["temp_min_c"].dtype == "float64"

    def test_weathercode_is_integer(self):
        df = self._pipeline()
        assert str(df["weathercode"].dtype).startswith("Int")


# T4 — Missing value handling
class TestHandleMissingValues:

    def test_precipitation_nulls_filled_with_zero(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df = _parse_dates(df)
        df = _cast_numeric_types(df)
        df.loc[0, "precipitation_mm"] = float("nan")
        df = _handle_missing_values(df)
        assert df.loc[0, "precipitation_mm"] == 0.0

    def test_temp_nulls_filled_with_median(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df = _parse_dates(df)
        df = _cast_numeric_types(df)
        df.loc[2, "temp_max_c"] = float("nan")
        # Compute expected median AFTER inserting the NaN (NaN is excluded by pandas median)
        expected_median = df["temp_max_c"].median()
        df = _handle_missing_values(df)
        assert df.loc[2, "temp_max_c"] == pytest.approx(expected_median)


# T5 — Duplicate removal
class TestRemoveDuplicates:

    def test_duplicate_rows_are_dropped(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df = _parse_dates(df)
        df = _cast_numeric_types(df)
        df = _handle_missing_values(df)
        n_before = len(df)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)  # add a dupe
        df = _remove_duplicates(df)
        assert len(df) == n_before


# T6 — Measurement validation
class TestValidateMeasurements:

    def _base_df(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df = _parse_dates(df)
        df = _cast_numeric_types(df)
        return _handle_missing_values(df)

    def test_valid_rows_flagged_valid(self):
        df = _validate_measurements(self._base_df())
        assert (df["data_quality"] == "valid").all()

    def test_impossible_temperature_flagged_suspect(self):
        df = self._base_df()
        df.loc[0, "temp_max_c"] = 100.0   # above TEMP_MAX_VALID = 60
        df = _validate_measurements(df)
        assert df.loc[0, "data_quality"] == "suspect"

    def test_max_below_min_flagged_suspect(self):
        df = self._base_df()
        df.loc[1, "temp_max_c"] = 10.0
        df.loc[1, "temp_min_c"] = 20.0   # min > max — impossible
        df = _validate_measurements(df)
        assert df.loc[1, "data_quality"] == "suspect"


# T7 — Derived fields
class TestCreateDerivedFields:

    def _pipeline(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df = _parse_dates(df)
        df = _cast_numeric_types(df)
        df = _handle_missing_values(df)
        df = _remove_duplicates(df)
        return _validate_measurements(df)

    def test_temp_range_is_difference(self):
        df = _create_derived_fields(self._pipeline())
        for _, row in df.iterrows():
            expected = round(row["temp_max_c"] - row["temp_min_c"], 1)
            assert row["temp_range_c"] == pytest.approx(expected, abs=0.01)

    def test_is_rainy_day_flag(self):
        df = _create_derived_fields(self._pipeline())
        rainy = df[df["precipitation_mm"] > 0]["is_rainy_day"]
        dry   = df[df["precipitation_mm"] == 0]["is_rainy_day"]
        assert (rainy == 1).all()
        assert (dry   == 0).all()

    def test_season_column_present_and_valid(self):
        df = _create_derived_fields(self._pipeline())
        assert "season" in df.columns
        assert set(df["season"].unique()).issubset({"Wet", "Dry"})


# T8 — Location name standardisation
class TestStandardizeLocationName:

    def test_location_name_is_title_case(self):
        df = _flatten_to_dataframe(single_location_fixture())
        df = _clean_column_names(df)
        df["location_name"] = "  accra  "   # messy input
        df = _standardize_location_name(df)
        assert df["location_name"].iloc[0] == "Accra"


# T9 — Required column check
class TestCheckRequiredColumns:

    def test_passes_when_all_columns_present(self):
        df = transform_all_locations(load_fixtures())
        _check_required_columns(df)  # should not raise

    def test_raises_when_column_missing(self):
        df = transform_all_locations(load_fixtures())
        df = df.drop(columns=["temp_max_c"])
        with pytest.raises(ValueError, match="Required columns missing"):
            _check_required_columns(df)
