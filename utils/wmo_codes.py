"""
Maps WMO weather interpretation codes (returned by Open-Meteo as
'weathercode') to human-readable labels and severity levels.

"""

# Each entry: wmo_code -> (label, severity)
# Severity: "Low" / "Moderate" / "High"
WMO_CODE_MAP: dict[int, tuple[str, str]] = {
    0:  ("Clear sky",                       "Low"),
    1:  ("Mainly clear",                    "Low"),
    2:  ("Partly cloudy",                   "Low"),
    3:  ("Overcast",                         "Low"),
    45: ("Fog",                              "Moderate"),
    48: ("Depositing rime fog",              "Moderate"),
    51: ("Light drizzle",                    "Low"),
    53: ("Moderate drizzle",                 "Low"),
    55: ("Dense drizzle",                    "Moderate"),
    56: ("Light freezing drizzle",           "Moderate"),
    57: ("Heavy freezing drizzle",           "High"),
    61: ("Slight rain",                      "Low"),
    63: ("Moderate rain",                    "Moderate"),
    65: ("Heavy rain",                       "High"),
    66: ("Light freezing rain",              "Moderate"),
    67: ("Heavy freezing rain",              "High"),
    71: ("Slight snowfall",                  "Low"),
    73: ("Moderate snowfall",                "Moderate"),
    75: ("Heavy snowfall",                   "High"),
    77: ("Snow grains",                      "Low"),
    80: ("Slight rain showers",              "Low"),
    81: ("Moderate rain showers",            "Moderate"),
    82: ("Violent rain showers",             "High"),
    85: ("Slight snow showers",              "Low"),
    86: ("Heavy snow showers",               "High"),
    95: ("Thunderstorm",                     "High"),
    96: ("Thunderstorm with slight hail",    "High"),
    99: ("Thunderstorm with heavy hail",     "High"),
}


def get_condition(wmo_code: int) -> tuple[str, str]:
    """
    Return (label, severity) for a WMO code.
    Falls back to ('Unknown', 'Low') for unrecognised codes.
    """
    return WMO_CODE_MAP.get(wmo_code, ("Unknown", "Low"))
