# Weather Analytics Pipeline

A production-style data pipeline that extracts daily weather data from the [Open-Meteo API](https://open-meteo.com), transforms and validates it, loads it into a star-schema SQLite database, and runs automatically every day via Apache Airflow.

Built as part of the AICA Data Engineering Capstone Project (2025/2026 Cohort 2).

---

## Architecture

```
Open-Meteo API
      │
      ▼
┌─────────────────────────────────────────────────┐
│  ETL Pipeline (pipeline/)                        │
│                                                  │
│  extract.py → transform.py → validate.py → load.py │
└─────────────────────────────────────────────────┘
      │                            │
      │                            ▼
      │                    ┌───────────────┐
      │                    │  Postgres DB    │
      │                    │  (star schema)│
      │                    └───────────────┘
      │                            ▲
      ▼                            │
┌─────────────────────────────────────────────────┐
│  ELT Workflow (Part B)                           │
│                                                  │
│  extract → stg_weather_raw → SQL transform → fact │
└─────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────┐
│  Airflow DAG (dags/weather_dag.py)               │
│  schedule: @daily                                │
│  setup → extract → transform → validate → load  │
└─────────────────────────────────────────────────┘
```

---

## Star Schema

```
                  dim_date
                 ┌──────────────┐
                 │ date_id (PK) │
                 │ full_date    │
                 │ day_of_week  │
                 │ month        │
                 │ quarter      │
                 │ year         │
                 │ season       │
                 │ is_weekend   │
                 └──────┬───────┘
                        │
dim_location            │            dim_condition
┌─────────────┐         │         ┌───────────────────┐
│location_id  │         │         │ condition_id (PK) │
│location_name│    ┌────┴──────┐  │ wmo_code          │
│city         │◄───┤fact_weather├─►│ condition_label   │
│country      │    │(weather_id│  │ severity          │
│latitude     │    │ date_id   │  └───────────────────┘
│longitude    │    │ location_id│
│timezone     │    │condition_id│
└─────────────┘    │ temp_max_c │
                   │ temp_min_c │
                   │precipitation│
                   │ windspeed  │
                   │ is_rainy_day│
                   └────────────┘
```

---

## Project Structure

```
weather_pipeline/
├── dags/
│   └── weather_dag.py          Airflow DAG (daily schedule)
├── pipeline/
│   ├── extract.py              Open-Meteo API extraction
│   ├── transform.py            10 transformation steps (T1–T10)
│   ├── validate.py             9 data quality checks
│   ├── load.py                 Schema creation + star schema loading
│   └── pipeline_class.py      WeatherPipeline orchestrator class
├── utils/
│   ├── config.py               All constants (locations, thresholds, paths)
│   ├── logger.py               Shared logging configuration
│   ├── db_connection.py        SQLAlchemy engine + context manager
│   └── wmo_codes.py            WMO weather code lookup table
├── tests/
│   ├── fixtures.json           Realistic mock API response data
│   ├── test_extract.py         10 tests for extract module
│   ├── test_transform.py       25 tests for all 10 transforms (T1–T9)
│   └── test_validate.py        18 tests for all 9 quality checks
├── sql/
│   └── schema.sql              CREATE TABLE + VIEW statements
├── logs/
│   └── pipeline.log            Pipeline run logs (auto-generated)
├── sample_output/              Sample DB query results (screenshots)
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/weather_pipeline.git
cd weather_pipeline
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running the pipeline

### Run once (ETL + ELT)

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from pipeline.pipeline_class import WeatherPipeline
pipeline = WeatherPipeline(start_date='2026-06-23', end_date='2026-06-30')
summary = pipeline.run()
print(summary)
"
```

### Run for a specific date range

```python
from pipeline.pipeline_class import WeatherPipeline

pipeline = WeatherPipeline(
    start_date="2025-01-01",
    end_date="2025-01-31",
    run_elt=True,
)
pipeline.run()
```

---

## Running the tests

```bash
# Run all 53 tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_transform.py -v

# Run with coverage (if pytest-cov installed)
pytest tests/ --cov=pipeline --cov-report=term-missing
```

---

## Setting up Airflow

```bash
# Set the project root on Python path
export PYTHONPATH=$(pwd)

# Initialise Airflow (first time only)
export AIRFLOW_HOME=~/airflow
airflow db init

# Copy the DAG
cp dags/weather_dag.py ~/airflow/dags/

# Create an admin user
airflow users create \
    --username admin --password admin \
    --firstname Data --lastname Engineer \
    --role Admin --email ed@gmail.com

# Start webserver (terminal 1)
airflow webserver --port 8080

# Start scheduler (terminal 2)
airflow scheduler

# Trigger a manual run
airflow dags trigger weather_pipeline
```

Open `http://localhost:8080` to view the DAG and task logs.

---

## Technologies used

| Technology | Purpose | Why |
|---|---|---|
| Python 3.12 | Primary language | Readable, well-supported in data engineering |
| requests | API extraction | Standard HTTP library; clean error handling |
| pandas | Transformation | Vectorised operations; rich data type support |
| SQLAlchemy | Database ORM | Abstraction layer; easy to swap SQLite → Postgres |
| SQLite | Database | Zero-setup; portable; identical SQL to Postgres |
| Apache Airflow | Orchestration | Industry standard; retry logic; dependency graph |
| pytest | Testing | Fixtures, mocking, parametrize — all built in |

---

## Data quality checks

The validate module runs 9 checks on every batch before it touches the database:

| Check | Type | Action on fail |
|---|---|---|
| Empty DataFrame | Critical | Abort |
| Required columns present | Critical | Abort |
| No nulls in critical columns | Critical | Abort |
| Temperatures within −60 to 60°C | Critical | Abort |
| Max temp ≥ min temp | Critical | Abort |
| Precipitation non-negative | Warning | Log only |
| Row count reasonable | Warning | Log only |
| No future dates | Warning | Log only |
| WMO codes recognised | Warning | Log only |

---

## Adding a new location

Edit `utils/config.py` — append to the `LOCATIONS` list:

```python
{"name": "Takoradi", "city": "Takoradi", "country": "Ghana",
 "lat": 4.8867, "lon": -1.7554, "timezone": "Africa/Accra"},
```

The pipeline will collect data for the new location on the next run. No other code changes required.

---

## Known limitations and future improvements

- **SQLite** is used for portability. For production, set `DB_URL` in `config.py` to a PostgreSQL connection string.
- **Open-Meteo API** is blocked from some server/CI environments. Use `tests/fixtures.json` for offline runs.
- **Historical backfill** can be done by setting `start_date` / `end_date` on `WeatherPipeline` and running manually.
- Future: add a `dim_quality` table to track data quality results per batch.
- Future: add email alerting on pipeline failure via Airflow's `email_on_failure`.
- Future: add a reporting layer (e.g. Metabase, Superset) querying `vw_daily_summary`.
# aica_final_project
