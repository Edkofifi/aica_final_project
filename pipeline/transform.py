"""
Converts raw Open-Meteo API dicts into clean, typed DataFrames that
are ready to be loaded into the star schema.
"""

import pandas as pd
from datetime import date, timedelta

from utils.config import (
    REQUIRED_COLUMNS,
    TEMP_MIN_VALID, TEMP_MAX_VALID,
    PRECIP_MIN_VALID, WIND_MAX_VALID,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# Public API
def transform_all_locations(raw_list: list[dict]) -> pd.DataFrame:
    """
    Transform a list of raw API dicts into one merged clean DataFrame.

    Args:
        raw_list: Output from extract.extract_all_locations().

    Returns:
        A single pandas DataFrame with one row per (date, location).
        Columns match what validate.py and load.py expect.
    """
    frames = []
    for raw in raw_list:
        location_name = raw.get("_location", {}).get("name", "Unknown")
        try:
            df = _transform_one(raw)
            frames.append(df)
            logger.info(f"✓ Transformed '{location_name}' → {len(df)} rows")
        except Exception as exc:
            logger.error(f"✗ Transform failed for '{location_name}': {exc}")

    if not frames:
        raise ValueError("No locations transformed successfully — aborting.")

    merged = pd.concat(frames, ignore_index=True)
    logger.info(f"Transform complete | total rows: {len(merged)}")
    return merged



# Single-location transform pipeline
def _transform_one(raw: dict) -> pd.DataFrame:
    """Apply all transformation steps to one location's raw data."""
    df = _flatten_to_dataframe(raw)
    df = _clean_column_names(df)           # T1
    df = _parse_dates(df)                  # T2
    df = _cast_numeric_types(df)           # T3
    df = _handle_missing_values(df)        # T4
    df = _remove_duplicates(df)            # T5
    df = _validate_measurements(df)        # T6
    df = _create_derived_fields(df)        # T7
    df = _standardize_location_name(df)    # T8
    _check_required_columns(df)            # T9
    df = _prepare_for_loading(df)          # T10
    return df



# T1 — Clean column names
def _flatten_to_dataframe(raw: dict) -> pd.DataFrame:
    """
    Unpack the nested API dict into a flat DataFrame.
    Each row is one calendar day for one location.
    """
    daily = raw["daily"]
    location = raw["_location"]

    df = pd.DataFrame(daily)

    # Attach location metadata to every row.
    df["location_name"] = location["name"]
    df["city"]          = location["city"]
    df["country"]       = location["country"]
    df["latitude"]      = location["lat"]
    df["longitude"]     = location["lon"]
    df["timezone"]      = location["timezone"]
    return df


def _clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    T1: Normalise column names to lowercase snake_case.
    Also rename verbose API names to cleaner pipeline names.
    """
    rename_map = {
        "time":                 "date",
        "temperature_2m_max":   "temp_max_c",
        "temperature_2m_min":   "temp_min_c",
        "precipitation_sum":    "precipitation_mm",
        "windspeed_10m_max":    "windspeed_max_kmh",
        "weathercode":          "weathercode",
        "sunrise":              "sunrise",
        "sunset":               "sunset",
    }
    df = df.rename(columns=rename_map)
    # Any remaining columns: strip whitespace, lowercase, underscores.
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    logger.debug(f"T1 columns: {list(df.columns)}")
    return df


# T2 — Parse dates and timestamps
def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    T2: Convert string dates/timestamps to proper datetime objects.
    'date' becomes a date only; 'sunrise'/'sunset' keep full datetime.
    """
    df["date"]    = pd.to_datetime(df["date"]).dt.date
    if "sunrise" in df.columns:
        df["sunrise"] = pd.to_datetime(df["sunrise"], errors="coerce")
    if "sunset" in df.columns:
        df["sunset"]  = pd.to_datetime(df["sunset"],  errors="coerce")
    return df


# T3 — Cast numeric types
def _cast_numeric_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    T3: Ensure all measurement columns are proper float64.
    Coerce errors (e.g. 'N/A' strings) to NaN for T4 to handle.
    """
    float_cols = ["temp_max_c", "temp_min_c", "precipitation_mm", "windspeed_max_kmh"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    if "weathercode" in df.columns:
        df["weathercode"] = pd.to_numeric(df["weathercode"], errors="coerce").astype("Int64")

    return df


# T4 — Handle missing values
def _handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    T4: Fill or drop missing values with a documented strategy.

    - precipitation_mm:  NaN → 0.0  (no data means no rain recorded)
    - temperature cols:  NaN → median of the column (rare sensor gap)
    - windspeed:         NaN → median of the column
    - weathercode:       NaN → 0  (clear sky, the safe default)

    We document the strategy with a log entry so the audit trail is clear.
    """
    fill_log = []

    precip_nulls = df["precipitation_mm"].isna().sum()
    if precip_nulls:
        df["precipitation_mm"] = df["precipitation_mm"].fillna(0.0)
        fill_log.append(f"precipitation_mm: {precip_nulls} NaN → 0.0")

    for col in ["temp_max_c", "temp_min_c", "windspeed_max_kmh"]:
        nulls = df[col].isna().sum()
        if nulls:
            median = df[col].median()
            df[col] = df[col].fillna(median)
            fill_log.append(f"{col}: {nulls} NaN → median ({median:.1f})")

    wc_nulls = df["weathercode"].isna().sum()
    if wc_nulls:
        df["weathercode"] = df["weathercode"].fillna(0)
        fill_log.append(f"weathercode: {wc_nulls} NaN → 0")

    if fill_log:
        logger.info("T4 missing value fills: " + " | ".join(fill_log))
    return df


# T5 — Remove duplicates
def _remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    T5: Drop duplicate (date, location_name) pairs.
    The API should never return duplicates, but we guard against it.
    """
    before = len(df)
    df = df.drop_duplicates(subset=["date", "location_name"], keep="first")
    dropped = before - len(df)
    if dropped:
        logger.warning(f"T5: Dropped {dropped} duplicate rows")
    return df


# T6 — Validate measurements
def _validate_measurements(df: pd.DataFrame) -> pd.DataFrame:
    """
    T6: Flag rows with out-of-range values.
    We add a 'data_quality' column: 'valid' or 'suspect'.
    Suspect rows are kept but flagged — downstream analysts can decide.
    """
    suspect_mask = (
        (df["temp_max_c"] < TEMP_MIN_VALID) | (df["temp_max_c"] > TEMP_MAX_VALID) |
        (df["temp_min_c"] < TEMP_MIN_VALID) | (df["temp_min_c"] > TEMP_MAX_VALID) |
        (df["precipitation_mm"] < PRECIP_MIN_VALID) |
        (df["windspeed_max_kmh"] < 0) | (df["windspeed_max_kmh"] > WIND_MAX_VALID) |
        (df["temp_max_c"] < df["temp_min_c"])   # max must be ≥ min
    )
    df["data_quality"] = "valid"
    df.loc[suspect_mask, "data_quality"] = "suspect"

    n_suspect = suspect_mask.sum()
    if n_suspect:
        logger.warning(f"T6: {n_suspect} suspect rows flagged")
        suspect_rows = df[suspect_mask][["date", "location_name", "temp_max_c", "temp_min_c"]]
        logger.debug(f"Suspect rows:\n{suspect_rows}")
    return df


# T7 — Create derived fields
def _create_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    T7: Add analytically useful columns derived from raw measurements.
    These are the columns analysts will actually query most.
    """
    # Temperature range — useful for identifying extreme days.
    df["temp_range_c"] = (df["temp_max_c"] - df["temp_min_c"]).round(1)

    # Simple rainy day flag.
    df["is_rainy_day"] = (df["precipitation_mm"] > 0).astype(int)

    # Temperature category — useful for dashboard segmentation.
    df["temp_category"] = pd.cut(
        df["temp_max_c"],
        bins=[-60, 10, 20, 30, 40, 60],
        labels=["Cold", "Cool", "Warm", "Hot", "Extreme"],
        right=True,
    ).astype(str)

    # West Africa has two seasons: Dry (Nov–Mar) and Wet (Apr–Oct).
    month = pd.to_datetime(df["date"].astype(str)).dt.month
    df["season"] = month.map(
        lambda m: "Dry" if m in (11, 12, 1, 2, 3) else "Wet"
    )

    return df

# T8 — Standardize location names
def _standardize_location_name(df: pd.DataFrame) -> pd.DataFrame:
    """
    T8: Ensure location_name is title-cased and stripped of whitespace.
    This prevents 'accra', 'ACCRA', ' Accra ' from being treated as
    different locations in the database.
    """
    df["location_name"] = df["location_name"].str.strip().str.title()
    df["city"]          = df["city"].str.strip().str.title()
    df["country"]       = df["country"].str.strip().str.title()
    return df


# T9 — Validate required columns
def _check_required_columns(df: pd.DataFrame) -> None:
    """
    T9: Assert all columns the load step needs are present.
    Raises ValueError early rather than letting the DB INSERT fail.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"T9: Required columns missing after transform: {missing}")
    logger.debug("T9: All required columns present.")

# T10 — Prepare for loading
def _prepare_for_loading(df: pd.DataFrame) -> pd.DataFrame:
    """
    T10: Final housekeeping before the load step.
    - Keep date as a Python date object — psycopg2 maps it to PostgreSQL DATE.
    - Keep sunrise/sunset as Python datetime or None — maps to TIMESTAMPTZ.
    - Convert pandas nullable Int64 weathercode to plain Python int.
    - Reset index.
    """
    import datetime as dt

    # date: ensure it is a Python date object (not pandas Timestamp)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # sunrise/sunset: convert to Python datetime or None
    def _to_dt_or_none(val):
        if val is None:
            return None
        try:
            ts = pd.to_datetime(val)
            return None if pd.isna(ts) else ts.to_pydatetime()
        except Exception:
            return None

    df["sunrise"] = df["sunrise"].apply(_to_dt_or_none)
    df["sunset"]  = df["sunset"].apply(_to_dt_or_none)
    df["weathercode"] = df["weathercode"].astype(int)
    df = df.reset_index(drop=True)
    return df
