"""
Creates the star schema tables (if they do not exist) and loads
clean data from the transformed DataFrame.
"""

import os
from datetime import date, timedelta

import pandas as pd

from utils.config import LOCATIONS
from utils.db_connection import get_connection
from utils.logger import get_logger
from utils.wmo_codes import WMO_CODE_MAP

logger = get_logger(__name__)


# Schema creation

def create_schema() -> None:
    """
    Execute schema.sql to create all tables, indexes, and views.
    Safe to run on every startup — all statements use IF NOT EXISTS
    or CREATE OR REPLACE.
    """
    sql_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sql", "schema.sql"
    )
    with open(sql_path, "r") as f:
        schema_sql = f.read()

    with get_connection() as conn:
        cursor = conn.cursor()
        statements = []
        current = []
        for line in schema_sql.splitlines():
            stripped = line.strip()
            if stripped.startswith("--") or not stripped:
                continue
            current.append(line)
            if stripped.endswith(";"):
                statements.append("\n".join(current))
                current = []

        for stmt in statements:
            clean = stmt.strip().rstrip(";")
            if clean:
                cursor.execute(clean)

    logger.info("Schema created / verified.")



# Dimension table population
def populate_dim_condition() -> None:
    """Pre-populate dim_condition from the WMO code lookup table."""
    with get_connection() as conn:
        cursor = conn.cursor()
        rows = [
            (code, label, severity)
            for code, (label, severity) in WMO_CODE_MAP.items()
        ]
        cursor.executemany(
            """INSERT INTO dim_condition (wmo_code, condition_label, severity)
               VALUES (%s, %s, %s)
               ON CONFLICT (wmo_code) DO NOTHING""",
            rows,
        )
    logger.info(f"dim_condition populated with {len(rows)} WMO codes.")


def populate_dim_location() -> None:
    """Pre-populate dim_location from config.LOCATIONS."""
    with get_connection() as conn:
        cursor = conn.cursor()
        rows = [
            (loc["name"], loc["city"], loc["country"],
             loc["lat"], loc["lon"], loc["timezone"])
            for loc in LOCATIONS
        ]
        cursor.executemany(
            """INSERT INTO dim_location
               (location_name, city, country, latitude, longitude, timezone)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (location_name) DO NOTHING""",
            rows,
        )
    logger.info(f"dim_location populated with {len(rows)} locations.")


def populate_dim_date(years_back: int = 2, years_forward: int = 1) -> None:
    """
    Pre-populate dim_date for a rolling date window.
    Passes Python date objects — psycopg2 maps them to PostgreSQL DATE.
    """
    today = date.today()
    start = today - timedelta(days=years_back * 365)
    end   = today + timedelta(days=years_forward * 365)

    rows = []
    current = start
    while current <= end:
        month = current.month
        season = "Dry" if month in (11, 12, 1, 2, 3) else "Wet"
        rows.append((
            current,                              # full_date  (DATE)
            current.strftime("%A"),               # day_of_week
            current.weekday(),                    # day_num
            current.month,                        # month
            current.strftime("%B"),               # month_name
            (current.month - 1) // 3 + 1,        # quarter
            current.year,                         # year
            season,                               # season
            current.weekday() >= 5,               # is_weekend (True/False → BOOLEAN)
        ))
        current += timedelta(days=1)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """INSERT INTO dim_date
               (full_date, day_of_week, day_num, month, month_name,
                quarter, year, season, is_weekend)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (full_date) DO NOTHING""",
            rows,
        )
    logger.info(f"dim_date populated with {len(rows)} dates ({start} → {end}).")


# Fact table loading
def load_fact_weather(df: pd.DataFrame) -> int:
    """
    Load the transformed DataFrame into fact_weather.
    Resolves FK ids from dimension tables, then batch-inserts.
    Returns the number of rows successfully inserted.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Build FK lookup dicts in one query each — far faster than
        # one SELECT per row when loading hundreds of rows at a time.
        cursor.execute("SELECT full_date, date_id FROM dim_date")
        date_map = {str(r[0]): r[1] for r in cursor.fetchall()}

        cursor.execute("SELECT location_name, location_id FROM dim_location")
        location_map = {r[0]: r[1] for r in cursor.fetchall()}

        cursor.execute("SELECT wmo_code, condition_id FROM dim_condition")
        condition_map = {r[0]: r[1] for r in cursor.fetchall()}

        rows_to_insert = []
        skipped = 0

        for _, row in df.iterrows():
            date_id      = date_map.get(str(row["date"]))
            location_id  = location_map.get(row["location_name"])
            condition_id = condition_map.get(int(row["weathercode"]))

            if not all([date_id, location_id, condition_id]):
                logger.warning(
                    f"Skipping ({row['date']}, {row['location_name']}): "
                    f"unresolved FK — date_id={date_id}, "
                    f"location_id={location_id}, condition_id={condition_id}"
                )
                skipped += 1
                continue

            # Parse sunrise/sunset: keep as None if not a valid timestamp.
            sunrise = _parse_optional_ts(row.get("sunrise"))
            sunset  = _parse_optional_ts(row.get("sunset"))

            rows_to_insert.append((
                date_id,
                location_id,
                condition_id,
                float(row["temp_max_c"]),
                float(row["temp_min_c"]),
                float(row["temp_range_c"]),
                float(row["precipitation_mm"]),
                float(row["windspeed_max_kmh"]),
                bool(row["is_rainy_day"]),
                sunrise,
                sunset,
            ))

        if rows_to_insert:
            cursor.executemany(
                """INSERT INTO fact_weather
                   (date_id, location_id, condition_id,
                    temp_max_c, temp_min_c, temp_range_c,
                    precipitation_mm, windspeed_max_kmh,
                    is_rainy_day, sunrise, sunset)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (date_id, location_id) DO NOTHING""",
                rows_to_insert,
            )

    inserted = len(rows_to_insert) - skipped
    logger.info(f"fact_weather: {inserted}/{len(df)} rows inserted ({skipped} skipped).")
    return inserted


# ELT staging load
def load_raw_staging(raw_list: list[dict]) -> int:
    """
    ELT Step 2: Load raw API data into stg_weather_raw.
    Passes Python date/datetime objects — psycopg2 handles the casting.
    """
    from datetime import datetime

    rows = []
    for raw in raw_list:
        loc_name = raw["_location"]["name"]
        daily = raw["daily"]
        n = len(daily["time"])
        for i in range(n):
            # Parse raw_date to a Python date object.
            raw_date = date.fromisoformat(daily["time"][i])

            # Parse sunrise/sunset strings to datetime or None.
            sunrise = _parse_optional_ts(daily.get("sunrise", [None]*n)[i])
            sunset  = _parse_optional_ts(daily.get("sunset",  [None]*n)[i])

            rows.append((
                loc_name,
                raw_date,
                daily.get("temperature_2m_max", [None]*n)[i],
                daily.get("temperature_2m_min", [None]*n)[i],
                daily.get("precipitation_sum",  [None]*n)[i],
                daily.get("windspeed_10m_max",  [None]*n)[i],
                daily.get("weathercode",        [None]*n)[i],
                sunrise,
                sunset,
            ))

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """INSERT INTO stg_weather_raw
               (location_name, raw_date, temp_max_raw, temp_min_raw,
                precipitation, windspeed_max, weathercode, sunrise, sunset)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            rows,
        )
    logger.info(f"stg_weather_raw: {len(rows)} raw rows loaded.")
    return len(rows)


def transform_staging_to_fact() -> int:
    """
    Transform staged data to final tables using SQL.
    This is the key ELT distinction: transformation happens inside the DB.
    """
    sql = """
    INSERT INTO fact_weather
        (date_id, location_id, condition_id,
         temp_max_c, temp_min_c, temp_range_c,
         precipitation_mm, windspeed_max_kmh, is_rainy_day)
    SELECT
        d.date_id,
        l.location_id,
        COALESCE(c.condition_id, 1),
        CAST(s.temp_max_raw AS NUMERIC(5,1)),
        CAST(s.temp_min_raw AS NUMERIC(5,1)),
        ROUND(CAST(s.temp_max_raw AS NUMERIC) - CAST(s.temp_min_raw AS NUMERIC), 1),
        COALESCE(CAST(s.precipitation AS NUMERIC(6,1)), 0.0),
        CAST(s.windspeed_max AS NUMERIC(6,1)),
        COALESCE(s.precipitation, 0) > 0
    FROM stg_weather_raw s
    JOIN dim_date     d ON d.full_date      = s.raw_date
    JOIN dim_location l ON l.location_name  = s.location_name
    LEFT JOIN dim_condition c ON c.wmo_code = s.weathercode
    WHERE s.temp_max_raw IS NOT NULL
      AND s.temp_min_raw IS NOT NULL
    ON CONFLICT (date_id, location_id) DO NOTHING
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        inserted = cursor.rowcount

    logger.info(f"ELT: {inserted} rows moved from staging → fact_weather.")
    return inserted



# Helper function to parse optional
def _parse_optional_ts(value):
    """
    Parse a sunrise/sunset string to a Python datetime, or return None.
    psycopg2 maps Python datetime to PostgreSQL TIMESTAMPTZ automatically.
    """
    if value is None or str(value) in ("None", "NaT", ""):
        return None
    try:
        from datetime import datetime
        if isinstance(value, str):
            # Open-Meteo format: '2025-06-01T06:10'
            return datetime.fromisoformat(value)
        return value
    except (ValueError, TypeError):
        return None
