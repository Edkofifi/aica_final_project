"""
extract.py
----------
fetching raw weather data from the
Open-Meteo API and returning it as a plain Python dict.
"""

import time
from datetime import date, timedelta

import requests

from utils.config import (
    API_BASE_URL,
    API_TIMEOUT_SECONDS,
    API_MAX_RETRIES,
    DAILY_VARIABLES,
    LOCATIONS,
)
from utils.logger import get_logger

logger = get_logger(__name__)

def extract_all_locations(
    start_date: str | None = None,
    end_date:   str | None = None,
    ) -> list[dict]:
    """
    Extract weather data for every location defined in config.LOCATIONS.

    Args:
        start_date: ISO date string 'YYYY-MM-DD'. Defaults to yesterday.
        end_date:   ISO date string 'YYYY-MM-DD'. Defaults to yesterday.

    Returns:
        List of raw API response dicts, one per location.
        Failed locations are skipped (logged as errors) so one bad
        location does not abort the whole run.
    """
    # Default to yesterday ie the most recent complete day.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    start_date = start_date or yesterday
    end_date   = end_date   or yesterday

    logger.info(
        f"Starting extraction | locations={len(LOCATIONS)} "
        f"| period={start_date} → {end_date}"
    )

    results = []
    for loc in LOCATIONS:
        try:
            raw = extract_one_location(loc, start_date, end_date)
            results.append(raw)
            logger.info(f"✓ Extracted '{loc['name']}'")
        except Exception as exc:
            logger.error(f"✗ Failed to extract '{loc['name']}': {exc}")

    logger.info(f"Extraction complete | {len(results)}/{len(LOCATIONS)} succeeded")
    return results


def extract_one_location(
    location:   dict,
    start_date: str,
    end_date:   str,
    ) -> dict:
    """
    Extract weather data for a single location dict.

    Args:
        location:   A dict from config.LOCATIONS (name, lat, lon, timezone …).
        start_date: ISO date string.
        end_date:   ISO date string.

    Returns:
        The parsed API JSON dict, augmented with the location metadata
        so downstream modules always have full context.

    Raises:
        requests.exceptions.RequestException on network/HTTP failure.
        ValueError if the API returns an unexpected payload shape.
    """
    params = {
        "latitude":   location["lat"],
        "longitude":  location["lon"],
        "daily":      ",".join(DAILY_VARIABLES),
        "timezone":   location["timezone"],
        "start_date": start_date,
        "end_date":   end_date,
    }

    raw = _get_with_retry(API_BASE_URL, params, location["name"])

    # Validate the response has the shape we expect.
    _validate_response(raw, location["name"])

    # Attach the location metadata so transform.py doesn't need config.
    raw["_location"] = location
    return raw



#  helper functions
def _get_with_retry(url: str, params: dict, location_name: str) -> dict:
    """
    GET the URL with exponential back-off retry.
    Raises the last exception if all retries are exhausted.
    """
    last_exc: Exception | None = None

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            logger.debug(
                f"[{location_name}] GET attempt {attempt}/{API_MAX_RETRIES}"
            )
            #response = requests.get(url, params=params, timeout=API_TIMEOUT_SECONDS)
            response = requests.get(url, params=params, timeout=(5, API_TIMEOUT_SECONDS))
            response.raise_for_status()        # Raises HTTPError for 4xx/5xx
            return response.json()

        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            logger.warning(f"[{location_name}] Connection error on attempt {attempt}: {exc}")
        except requests.exceptions.Timeout as exc:
            last_exc = exc
            logger.warning(f"[{location_name}] Timeout on attempt {attempt}")
        except requests.exceptions.HTTPError as exc:
            # 4xx errors won't be fixed by retrying.
            logger.error(f"[{location_name}] HTTP {exc.response.status_code}: {exc}")
            raise
        except requests.exceptions.JSONDecodeError as exc:
            last_exc = exc
            logger.warning(f"[{location_name}] JSON decode error on attempt {attempt}")

        if attempt < API_MAX_RETRIES:
            wait = 2 ** attempt          # 2s, 4s, 8s …
            logger.info(f"[{location_name}] Retrying in {wait}s …")
            time.sleep(wait)

    raise last_exc  # All retries exhausted.


def _validate_response(raw: dict, location_name: str) -> None:
    """
    Raise ValueError if the response is missing expected top-level keys.
    Open-Meteo always returns 'daily' and 'daily_units' on success.
    """
    required_keys = {"daily", "daily_units", "latitude", "longitude"}
    missing = required_keys - raw.keys()
    if missing:
        raise ValueError(
            f"[{location_name}] API response missing keys: {missing}. "
            f"Got: {list(raw.keys())}"
        )

    daily_keys = set(raw["daily"].keys())
    expected   = set(DAILY_VARIABLES) | {"time"}
    missing_vars = expected - daily_keys
    if missing_vars:
        raise ValueError(
            f"[{location_name}] Missing daily variables: {missing_vars}"
        )
    logger.debug(f"[{location_name}] Response validated OK ({len(raw['daily']['time'])} days)")
