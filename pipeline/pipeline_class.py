"""
WeatherPipeline is a reusable class that encapsulates one complete
pipeline run.  Instantiate it with optional date overrides and call
run() to execute all stages in order.
"""

import json
from datetime import date, timedelta

from pipeline.extract   import extract_all_locations
from pipeline.transform import transform_all_locations
from pipeline.validate  import validate_dataframe
from pipeline.load      import (
    create_schema,
    populate_dim_condition,
    populate_dim_location,
    populate_dim_date,
    load_fact_weather,
    load_raw_staging,
    transform_staging_to_fact,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class WeatherPipeline:
    """
    Orchestrates a complete ETL (and optionally ELT) pipeline run.

    Args:
        start_date: ISO date string. Defaults to yesterday.
        end_date:   ISO date string. Defaults to yesterday.
        run_elt:    If True, also executes the ELT staging workflow.
    """

    def __init__(
        self,
        start_date: str | None = None,
        end_date:   str | None = None,
        run_elt:    bool = True,
        ):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.start_date = start_date or yesterday
        self.end_date   = end_date   or yesterday
        self.run_elt    = run_elt
        self._raw: list[dict] | None = None

    # Main entry point

    def run(self) -> dict:
        """
        Execute the full pipeline.  Returns a summary dict suitable
        for logging or Airflow XCom.
        """
        logger.info("=" * 60)
        logger.info(f"WeatherPipeline starting | {self.start_date} → {self.end_date}")
        logger.info("=" * 60)

        self.setup()
        raw     = self.extract()
        df      = self.transform(raw)
        df      = self.validate(df)
        etl_n   = self.load(df)

        elt_n = 0
        if self.run_elt:
            elt_n = self.run_elt_workflow(raw)

        summary = {
            "start_date":      self.start_date,
            "end_date":        self.end_date,
            "locations":       len(raw),
            "rows_transformed": len(df),
            "rows_loaded_etl": etl_n,
            "rows_loaded_elt": elt_n,
            "status":          "success",
        }
        logger.info(f"Pipeline complete: {summary}")
        return summary

    # Individual stage methods
    def setup(self) -> None:
        """Create schema and pre-populate dimension tables."""
        logger.info("Stage 0: Setup")
        create_schema()
        populate_dim_condition()
        populate_dim_location()
        populate_dim_date()

    def extract(self) -> list[dict]:
        """Stage 1: Extract raw data from the API."""
        logger.info("Stage 1: Extract")
        raw = extract_all_locations(self.start_date, self.end_date)
        if not raw:
            raise RuntimeError("Extraction returned no data.")
        self._raw = raw
        return raw

    def transform(self, raw: list[dict]):
        """Stage 2: Transform raw dicts into clean DataFrame."""
        logger.info("Stage 2: Transform")
        return transform_all_locations(raw)

    def validate(self, df):
        """Stage 3: Validate transformed data."""
        logger.info("Stage 3: Validate")
        return validate_dataframe(df)

    def load(self, df) -> int:
        """Stage 4: Load to star schema."""
        logger.info("Stage 4: Load (ETL)")
        return load_fact_weather(df)

    def run_elt_workflow(self, raw: list[dict]) -> int:
        """
        Part B: ELT workflow.
        Load raw → staging, then transform in SQL → fact table.
        """
        logger.info("Stage 5: ELT workflow")
        load_raw_staging(raw)
        return transform_staging_to_fact()
