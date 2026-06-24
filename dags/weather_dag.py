"""
weather_dag.py
--------------
Airflow DAG that runs the weather pipeline daily.

The pipeline is executed as a single BashOperator task which:
  1. Loads environment variables from .env
  2. Activates the project virtualenv
  3. Runs WeatherPipeline().run() which internally executes:
       Stage 0: Setup      — create schema, seed dimension tables
       Stage 1: Extract    — fetch data from Open-Meteo API
       Stage 2: Transform  — clean and validate data (10 transforms)
       Stage 3: Validate   — 9 data quality checks
       Stage 4: Load ETL   — insert into star schema
       Stage 5: Load ELT   — raw staging → SQL transform → fact table

Design note:
  BashOperator is used instead of PythonOperator to avoid a macOS-specific
  fork() conflict between Airflow's subprocess spawning and psycopg2's
  threading model (objc runtime crash). The BashOperator spawns a clean
  shell process that does not inherit the problematic forked state.

To deploy:
  1. Set environment variables (see README.md)
  2. cp dags/weather_dag.py ~/airflow/dags/
  3. airflow dags trigger weather_pipeline
"""

import os
from datetime import datetime, timedelta, date

from airflow import DAG
from airflow.operators.bash import BashOperator

# Default arguments
DEFAULT_ARGS = {
    "owner":            "data_engineering",
    "depends_on_past":  False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry":   False,
}


# DAG definition
with DAG(
    dag_id="weather_pipeline",
    description="Daily weather data pipeline — ETL + ELT via Open-Meteo API",
    default_args=DEFAULT_ARGS,
    schedule_interval="@daily",
    # start_date is always yesterday relative to when the DAG is deployed.
    start_date=datetime.combine(
        date.today() - timedelta(days=1),
        datetime.min.time(),
    ),
    catchup=False,       # Do not backfill historical runs on first deploy
    max_active_runs=1,   # Only one run at a time to prevents DB conflicts
    tags=["weather", "etl", "elt", "open-meteo"],
) as dag:

    run_pipeline = BashOperator(
        task_id="run_pipeline",
        bash_command="""#!/bin/bash
set -e  # Exit immediately if any command fails

# Load database credentials and path variables from .env
source "${PIPELINE_HOME}/.env"

# Navigate to project root
cd "${PIPELINE_HOME}"

# Activate the project virtual environment
source "${PIPELINE_VENV}/bin/activate"

# Run the full pipeline
python -c "
from pipeline.pipeline_class import WeatherPipeline
summary = WeatherPipeline().run()
print('Pipeline summary:', summary)
"
""",
        # PIPELINE_HOME and PIPELINE_VENV must be set in your shell
        env={
            "PIPELINE_HOME": os.environ.get(
                "PIPELINE_HOME", "/path/to/weather_pipeline"
            ),
            "PIPELINE_VENV": os.environ.get(
                "PIPELINE_VENV", "/path/to/venv"
            ),
            # Required on macOS to prevent fork() crashes with psycopg2
            "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        },
    )