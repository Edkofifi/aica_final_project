

-- Staging table (ELT workflow)
CREATE TABLE IF NOT EXISTS stg_weather_raw (
    stg_id          SERIAL          PRIMARY KEY,
    location_name   TEXT            NOT NULL,
    raw_date        DATE            NOT NULL,
    temp_max_raw    NUMERIC(5,1),
    temp_min_raw    NUMERIC(5,1),
    precipitation   NUMERIC(6,1),
    windspeed_max   NUMERIC(6,1),
    weathercode     SMALLINT,
    sunrise         TIMESTAMPTZ,
    sunset          TIMESTAMPTZ,
    loaded_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);


-- dim_date — one row per calendar date
CREATE TABLE IF NOT EXISTS dim_date (
    date_id         SERIAL          PRIMARY KEY,
    full_date       DATE            NOT NULL UNIQUE,
    day_of_week     TEXT            NOT NULL,
    day_num         SMALLINT        NOT NULL,   
    month           SMALLINT        NOT NULL,
    month_name      TEXT            NOT NULL,
    quarter         SMALLINT        NOT NULL,
    year            SMALLINT        NOT NULL,
    season          TEXT            NOT NULL,   
    is_weekend      BOOLEAN         NOT NULL
);


-- dim_location — one row per monitored city
CREATE TABLE IF NOT EXISTS dim_location (
    location_id     SERIAL          PRIMARY KEY,
    location_name   TEXT            NOT NULL UNIQUE,
    city            TEXT            NOT NULL,
    country         TEXT            NOT NULL,
    latitude        NUMERIC(8,4)    NOT NULL,
    longitude       NUMERIC(8,4)    NOT NULL,
    timezone        TEXT            NOT NULL
);


-- dim_condition — one row per WMO weather code
CREATE TABLE IF NOT EXISTS dim_condition (
    condition_id    SERIAL          PRIMARY KEY,
    wmo_code        SMALLINT        NOT NULL UNIQUE,
    condition_label TEXT            NOT NULL,
    severity        TEXT            NOT NULL    -- 'Low' / 'Moderate' / 'High'
);


-- fact_weather — one row per (date, location) observation
CREATE TABLE IF NOT EXISTS fact_weather (
    weather_id          SERIAL          PRIMARY KEY,
    date_id             INTEGER         NOT NULL REFERENCES dim_date(date_id),
    location_id         INTEGER         NOT NULL REFERENCES dim_location(location_id),
    condition_id        INTEGER         NOT NULL REFERENCES dim_condition(condition_id),
    temp_max_c          NUMERIC(5,1)    NOT NULL,
    temp_min_c          NUMERIC(5,1)    NOT NULL,
    temp_range_c        NUMERIC(5,1)    NOT NULL,
    precipitation_mm    NUMERIC(6,1)    NOT NULL,
    windspeed_max_kmh   NUMERIC(6,1)    NOT NULL,
    is_rainy_day        BOOLEAN         NOT NULL,
    sunrise             TIMESTAMPTZ,
    sunset              TIMESTAMPTZ,
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    UNIQUE (date_id, location_id)
);


-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_fact_date     ON fact_weather (date_id);
CREATE INDEX IF NOT EXISTS idx_fact_location ON fact_weather (location_id);
CREATE INDEX IF NOT EXISTS idx_stg_date      ON stg_weather_raw (raw_date);
CREATE INDEX IF NOT EXISTS idx_stg_location  ON stg_weather_raw (location_name);


-- Analytical view
CREATE OR REPLACE VIEW vw_daily_summary AS
SELECT
    d.full_date,
    d.day_of_week,
    d.season,
    l.city,
    l.country,
    c.condition_label,
    c.severity,
    f.temp_max_c,
    f.temp_min_c,
    f.temp_range_c,
    f.precipitation_mm,
    f.windspeed_max_kmh,
    f.is_rainy_day
FROM fact_weather  f
JOIN dim_date      d ON f.date_id      = d.date_id
JOIN dim_location  l ON f.location_id  = l.location_id
JOIN dim_condition c ON f.condition_id = c.condition_id;
