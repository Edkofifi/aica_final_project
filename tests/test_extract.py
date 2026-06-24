"""
Unit tests for pipeline/extract.py.
"""

import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.extract import (
    extract_all_locations,
    extract_one_location,
    _validate_response,
)


VALID_RESPONSE = {
    "latitude":            5.6037,
    "longitude":          -0.1870,
    "generationtime_ms":   0.12,
    "utc_offset_seconds":  0,
    "timezone":           "Africa/Accra",
    "timezone_abbreviation": "GMT",
    "elevation":           61.0,
    "daily_units": {
        "time": "iso8601", "temperature_2m_max": "C",
        "temperature_2m_min": "C", "precipitation_sum": "mm",
        "windspeed_10m_max": "km/h", "weathercode": "wmo code",
        "sunrise": "iso8601", "sunset": "iso8601",
    },
    "daily": {
        "time":               ["2025-06-01", "2025-06-02"],
        "temperature_2m_max": [32.1, 32.4],
        "temperature_2m_min": [24.5, 24.7],
        "precipitation_sum":  [0.0, 5.2],
        "windspeed_10m_max":  [12.4, 15.0],
        "weathercode":        [0, 61],
        "sunrise":            ["2025-06-01T06:10", "2025-06-02T06:10"],
        "sunset":             ["2025-06-01T18:30", "2025-06-02T18:30"],
    },
}

LOCATION = {
    "name": "Accra", "city": "Accra", "country": "Ghana",
    "lat": 5.6037, "lon": -0.1870, "timezone": "Africa/Accra",
}


# Tests: extract_one_location
class TestExtractOneLocation:

    def _mock_response(self, data=None, status=200):
        mock = MagicMock()
        mock.status_code = status
        mock.json.return_value = data or VALID_RESPONSE
        mock.raise_for_status = MagicMock()  # does nothing on 200
        return mock

    def test_returns_dict_with_location_metadata(self):
        """Happy path: valid response returns dict with _location attached."""
        with patch("requests.get", return_value=self._mock_response()):
            result = extract_one_location(LOCATION, "2025-06-01", "2025-06-02")

        assert isinstance(result, dict)
        assert "_location" in result
        assert result["_location"]["name"] == "Accra"
        assert "daily" in result

    def test_daily_variables_present(self):
        """All configured daily variables must be in the result."""
        with patch("requests.get", return_value=self._mock_response()):
            result = extract_one_location(LOCATION, "2025-06-01", "2025-06-02")

        daily_keys = set(result["daily"].keys())
        for var in ["temperature_2m_max", "precipitation_sum", "weathercode"]:
            assert var in daily_keys, f"Missing variable: {var}"

    def test_raises_on_connection_error(self):
        """ConnectionError should propagate after retries are exhausted."""
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError("timeout")):
            with pytest.raises(req.exceptions.ConnectionError):
                extract_one_location(LOCATION, "2025-06-01", "2025-06-02")

    def test_raises_on_http_error(self):
        """HTTP 403 should raise immediately (no retry)."""
        import requests as req
        mock = MagicMock()
        mock.raise_for_status.side_effect = req.exceptions.HTTPError(
            response=MagicMock(status_code=403)
        )
        with patch("requests.get", return_value=mock):
            with pytest.raises(req.exceptions.HTTPError):
                extract_one_location(LOCATION, "2025-06-01", "2025-06-02")

    def test_raises_on_missing_daily_key(self):
        """Response without 'daily' key should raise ValueError."""
        bad_response = {**VALID_RESPONSE}
        del bad_response["daily"]
        with patch("requests.get", return_value=self._mock_response(bad_response)):
            with pytest.raises(ValueError, match="missing keys"):
                extract_one_location(LOCATION, "2025-06-01", "2025-06-02")


# Tests: extract_all_locations
class TestExtractAllLocations:

    def test_returns_list(self):
        """Should return a list even when called with no arguments."""
        with patch("pipeline.extract.extract_one_location", return_value=VALID_RESPONSE):
            result = extract_all_locations()
        assert isinstance(result, list)

    def test_failed_location_is_skipped(self):
        """One failing location should not abort the whole run."""
        def side_effect(loc, *args, **kwargs):
            if loc["name"] == "Kumasi":
                raise ConnectionError("Network unreachable")
            return {**VALID_RESPONSE, "_location": loc}

        with patch("pipeline.extract.extract_one_location", side_effect=side_effect):
            result = extract_all_locations()

        # Kumasi is in LOCATIONS (4 total) but should be skipped.
        location_names = [r["_location"]["name"] for r in result]
        assert "Kumasi" not in location_names
        assert len(result) == 3   # 4 - 1 failed


# Tests: _validate_response
class TestValidateResponse:

    def test_passes_valid_response(self):
        """A structurally correct response should not raise."""
        _validate_response(VALID_RESPONSE, "Accra")  # no exception

    def test_fails_missing_top_level_key(self):
        bad = {k: v for k, v in VALID_RESPONSE.items() if k != "daily_units"}
        with pytest.raises(ValueError, match="missing keys"):
            _validate_response(bad, "Accra")

    def test_fails_missing_daily_variable(self):
        bad = {**VALID_RESPONSE}
        bad["daily"] = {k: v for k, v in VALID_RESPONSE["daily"].items()
                        if k != "weathercode"}
        with pytest.raises(ValueError, match="Missing daily variables"):
            _validate_response(bad, "Accra")
