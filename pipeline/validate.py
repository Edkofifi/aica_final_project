"""
Runs a suite of data quality checks on the transformed DataFrame
before it touches the database.
"""

import pandas as pd

from utils.config import REQUIRED_COLUMNS, TEMP_MIN_VALID, TEMP_MAX_VALID
from utils.logger import get_logger

logger = get_logger(__name__)


class DataQualityError(Exception):
    """Raised when a critical data quality check fails."""
    pass


def validate_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run all quality checks.  Logs results and raises DataQualityError
    if any critical check fails.

    Args:
        df: The transformed DataFrame from transform.py.

    Returns:
        The same DataFrame (unchanged) if all checks pass.

    Raises:
        DataQualityError: If a critical check fails.
    """
    checks = [
        ("Empty DataFrame",        _check_not_empty,          True),
        ("Required columns",       _check_required_columns,   True),
        ("No null critical cols",  _check_no_critical_nulls,  True),
        ("Temperature range",      _check_temp_range,         True),
        ("Precipitation non-neg",  _check_precip_non_neg,     False),
        ("Max ≥ Min temp",         _check_max_gte_min,        True),
        ("Row count reasonable",   _check_row_count,          False),
        ("No future dates",        _check_no_future_dates,    False),
        ("Weathercode known",      _check_weathercodes,       False),
    ]

    failures = []
    warnings = []

    for name, fn, is_critical in checks:
        passed, message = fn(df)
        status = "PASS" if passed else ("FAIL" if is_critical else "WARN")
        logger.info(f"  [{status}] {name}: {message}")
        if not passed:
            if is_critical:
                failures.append(f"{name}: {message}")
            else:
                warnings.append(f"{name}: {message}")

    if warnings:
        logger.warning(f"Validation warnings: {len(warnings)}")

    if failures:
        msg = f"Data quality CRITICAL failures:\n" + "\n".join(f"  • {f}" for f in failures)
        logger.error(msg)
        raise DataQualityError(msg)

    logger.info(f"Validation passed — {len(df)} rows cleared for loading.")
    return df


# Individual checks
def _check_not_empty(df: pd.DataFrame) -> tuple[bool, str]:
    ok = len(df) > 0
    return ok, f"{len(df)} rows" if ok else "DataFrame is empty"


def _check_required_columns(df: pd.DataFrame) -> tuple[bool, str]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, f"Missing: {missing}"
    return True, "All required columns present"


def _check_no_critical_nulls(df: pd.DataFrame) -> tuple[bool, str]:
    critical = ["date", "location_name", "temp_max_c", "temp_min_c", "precipitation_mm"]
    null_counts = {c: int(df[c].isna().sum()) for c in critical if c in df.columns}
    bad = {k: v for k, v in null_counts.items() if v > 0}
    if bad:
        return False, f"Nulls in critical columns: {bad}"
    return True, "No nulls in critical columns"


def _check_temp_range(df: pd.DataFrame) -> tuple[bool, str]:
    if "temp_max_c" not in df.columns or "temp_min_c" not in df.columns:
        return True, "Skipped (columns not present)"
    bad = df[
        (df["temp_max_c"] < TEMP_MIN_VALID) | (df["temp_max_c"] > TEMP_MAX_VALID) |
        (df["temp_min_c"] < TEMP_MIN_VALID) | (df["temp_min_c"] > TEMP_MAX_VALID)
    ]
    if len(bad):
        return False, f"{len(bad)} rows with temperatures outside [{TEMP_MIN_VALID}, {TEMP_MAX_VALID}]°C"
    return True, f"All temperatures within valid range"


def _check_precip_non_neg(df: pd.DataFrame) -> tuple[bool, str]:
    if "precipitation_mm" not in df.columns:
        return True, "Skipped (column not present)"
    bad = df[df["precipitation_mm"] < 0]
    if len(bad):
        return False, f"{len(bad)} rows with negative precipitation"
    return True, "All precipitation values non-negative"


def _check_max_gte_min(df: pd.DataFrame) -> tuple[bool, str]:
    if "temp_max_c" not in df.columns or "temp_min_c" not in df.columns:
        return True, "Skipped (columns not present)"
    bad = df[df["temp_max_c"] < df["temp_min_c"]]
    if len(bad):
        return False, f"{len(bad)} rows where temp_max < temp_min"
    return True, "temp_max ≥ temp_min in all rows"


def _check_row_count(df: pd.DataFrame) -> tuple[bool, str]:
    # Warn if an unexpectedly small batch arrives (e.g. partial API response).
    min_expected = 1
    ok = len(df) >= min_expected
    return ok, f"{len(df)} rows (min expected: {min_expected})"


def _check_no_future_dates(df: pd.DataFrame) -> tuple[bool, str]:
    if "date" not in df.columns or len(df) == 0:
        return True, "Skipped (no date column or empty)"
    from datetime import date
    today = date.today()
    # Compare as date objects (transform.py produces date objects for Postgres)
    future = df[df["date"].apply(lambda d: d > today if isinstance(d, date) else str(d) > today.isoformat())]
    if len(future):
        return False, f"{len(future)} rows with future dates"
    return True, "No future dates"


def _check_weathercodes(df: pd.DataFrame) -> tuple[bool, str]:
    if "weathercode" not in df.columns or len(df) == 0:
        return True, "Skipped (no weathercode column or empty)"
    from utils.wmo_codes import WMO_CODE_MAP
    known = set(WMO_CODE_MAP.keys())
    unknown = df[~df["weathercode"].isin(known)]["weathercode"].unique()
    if len(unknown):
        return False, f"Unknown WMO codes: {list(unknown)}"
    return True, "All weather codes recognised"
