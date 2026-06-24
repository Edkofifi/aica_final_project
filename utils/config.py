"""
Central configuration for the weather pipeline.
All constants live here — nothing is hardcoded in pipeline modules.
To add a new location, append to LOCATIONS below and the pipeline
will automatically collect data for it on the next run.
"""

import os
from dotenv import load_dotenv
load_dotenv("/Users/ed/Workspace/work/aica/weather_pipeline/.env")


# API settings
API_BASE_URL = "https://api.open-meteo.com/v1/forecast"
API_TIMEOUT_SECONDS = 15
API_MAX_RETRIES = 3

# Variables needed from the Open-Meteo daily endpoint.
# Full list: https://open-meteo.com/en/docs
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "windspeed_10m_max",
    "weathercode",
    "sunrise",
    "sunset",
]

# Locations to collect data for.
LOCATIONS = [
    {"name": "Accra",  "city": "Accra",  "country": "Ghana",   "lat": 5.6037,  "lon": -0.1870, "timezone": "Africa/Accra"},
    {"name": "Kumasi", "city": "Kumasi", "country": "Ghana",   "lat": 6.6885,  "lon": -1.6244, "timezone": "Africa/Accra"},
    {"name": "London", "city": "London", "country": "UK",      "lat": 51.5074, "lon": -0.1278, "timezone": "Europe/London"},
    {"name": "Lagos",  "city": "Lagos",  "country": "Nigeria", "lat": 6.5244,  "lon": 3.3792,  "timezone": "Africa/Lagos"},
]


BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_HOST     = os.environ.get("DB_HOST",     "localhost")
DB_PORT     = os.environ.get("DB_PORT",     "5432")
DB_NAME     = os.environ.get("DB_NAME",     "weather_db")
DB_USER     = os.environ.get("DB_USER",     "weather_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

DB_URL = os.environ.get(
    "DB_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

DB_SCHEMA = os.environ.get("DB_SCHEMA", "public")   # override for multi-tenant setups

# Logging settings
LOG_DIR    = os.path.join(BASE_DIR, "logs")
LOG_FILE   = os.path.join(LOG_DIR, "pipeline.log")
LOG_LEVEL  = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE   = "%Y-%m-%d %H:%M:%S"


# Data quality thresholds
TEMP_MIN_VALID   = -60.0
TEMP_MAX_VALID   =  60.0
PRECIP_MIN_VALID =   0.0
WIND_MAX_VALID   = 450.0

# Columns the fact table cannot load without.
REQUIRED_COLUMNS = [
    "date", "location_name", "temp_max_c", "temp_min_c",
    "precipitation_mm", "windspeed_max_kmh", "weathercode",
]
