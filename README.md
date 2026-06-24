# Weather Analytics Pipeline

A production-style data pipeline that extracts daily weather data from the [Open-Meteo API](https://open-meteo.com), transforms and validates it, loads it into a star-schema PostgreSQL database, and runs automatically every day via Apache Airflow.

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
      │                    │  PostgreSQL   │
      │                    │  (star schema)│
      │                    └───────────────┘
      │                            ▲
      ▼                            │
┌─────────────────────────────────────────────────┐
│  ELT Workflow (Part B)                           │
│                                                  │
│  extract → stg_weather_raw → SQL transform → fact│
└─────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────┐
│  Airflow DAG (dags/weather_dag.py)               │
│  schedule: @daily                                │
│  BashOperator → WeatherPipeline().run()          │
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
│country      │    │ weather_id│  │ severity          │
│latitude     │    │ date_id   │  └───────────────────┘
│longitude    │    │location_id│
│timezone     │    │condition_id│
└─────────────┘    │ temp_max_c │
                   │ temp_min_c │
                   │precipitation│
                   │ windspeed  │
                   │ is_rainy_day│
                   └────────────┘
```

---


## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Edkofifi/aica_final_project.git
cd aica_final_project/weather_pipeline
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

### 4. Create the PostgreSQL database and user

```bash
psql -U postgres -c "CREATE DATABASE weather_db;"
psql -U postgres -c "CREATE USER weather_user WITH PASSWORD 'yourpassword';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE weather_db TO weather_user;"
```

### 5. Create a `.env` file in the project root

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=weather_db
DB_USER=weather_user
DB_PASSWORD=yourpassword
```

---

## Running the pipeline

### Run once manually (ETL + ELT)

```bash
source .env   # or export the variables manually
python -c "
from pipeline.pipeline_class import WeatherPipeline
pipeline = WeatherPipeline()
summary = pipeline.run()
print(summary)
"
```

### Run for a specific date range

```python
from pipeline.pipeline_class import WeatherPipeline

pipeline = WeatherPipeline(
    start_date="2026-01-01",
    end_date="2026-01-31",
    run_elt=True,
)
pipeline.run()
```

---

## Running the tests

```bash
# Run all  tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_transform.py -v

# Run with coverage
pytest tests/ --cov=pipeline --cov-report=term-missing
```

---

## Setting up Airflow

### 1. Set required environment variables

```bash
# Required on macOS to prevent fork() crashes with psycopg2
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Point Airflow to your project and virtualenv
export PIPELINE_HOME=/path/to/weather_pipeline
export PIPELINE_VENV=/path/to/venv

# Add permanently to avoid setting on every session
echo 'export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES' >> ~/.zshrc
echo 'export PIPELINE_HOME=/path/to/weather_pipeline' >> ~/.zshrc
echo 'export PIPELINE_VENV=/path/to/venv' >> ~/.zshrc
source ~/.zshrc
```

### 2. Initialise Airflow

```bash
export AIRFLOW_HOME=~/airflow
mkdir -p ~/airflow/dags
airflow db init
```

### 3. Create an admin user

```bash
airflow users create \
    --username admin --password admin \
    --firstname your_first_name --lastname your_last_name \
    --role Admin --email admin@example.com
```

### 4. Copy the DAG

```bash
cp dags/weather_dag.py ~/airflow/dags/
```

### 5. Start Airflow (two separate terminals)

```bash
# Terminal 1
source .env
airflow webserver --port 8080

# Terminal 2
source .env
airflow scheduler
```

### 6. Trigger a manual run

```bash
airflow dags trigger weather_pipeline
```

Open `http://localhost:8080` to view the DAG and task logs.



## Adding a new location

Edit `utils/config.py` — append to the `LOCATIONS` list:

```python
{"name": "Takoradi", "city": "Takoradi", "country": "Ghana",
 "lat": 4.8867, "lon": -1.7554, "timezone": "Africa/Accra"},
```
