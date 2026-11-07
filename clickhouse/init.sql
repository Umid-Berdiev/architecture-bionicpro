-- OLAP storage for the reports service (ClickHouse).
-- Raw layer: copies of CRM dimensions and telemetry facts loaded by Airflow.
-- Mart layer: reports_mart, one row per user / prosthesis / day, ordered by user for fast lookups.

CREATE DATABASE IF NOT EXISTS reports;

CREATE TABLE IF NOT EXISTS reports.crm_customers
(
    customer_id  UInt32,
    idp_user_id  UUID,
    username     String,
    full_name    String,
    email        String,
    country      LowCardinality(String),
    loaded_at    DateTime
)
ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY customer_id;

CREATE TABLE IF NOT EXISTS reports.crm_prostheses
(
    prosthesis_id    UInt32,
    customer_id      UInt32,
    serial_number    String,
    model            LowCardinality(String),
    side             LowCardinality(String),
    firmware_version LowCardinality(String),
    delivered_at     Date,
    loaded_at        DateTime
)
ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY prosthesis_id;

CREATE TABLE IF NOT EXISTS reports.telemetry_raw
(
    telemetry_id      UInt64,
    prosthesis_serial String,
    recorded_at       DateTime,
    gesture           LowCardinality(String),
    reaction_ms       UInt16,
    myo_noise_level   Float32,
    battery_pct       UInt8,
    error_code        LowCardinality(String)   -- '' when no error
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(recorded_at)
ORDER BY (prosthesis_serial, recorded_at, telemetry_id);

-- The report mart. Primary key starts with the user id, so "all rows of one user for a date range"
-- is a single range read of the primary index without touching other users' data.
CREATE TABLE IF NOT EXISTS reports.reports_mart
(
    idp_user_id        UUID,
    report_date        Date,
    prosthesis_serial  String,
    username           String,
    full_name          String,
    model              LowCardinality(String),
    side               LowCardinality(String),
    actions_count      UInt32,     -- readings with a gesture other than rest
    readings_count     UInt32,
    avg_reaction_ms    Float32,
    p95_reaction_ms    UInt16,
    max_reaction_ms    UInt16,
    slow_actions_count UInt32,     -- reaction above the 100 ms target
    avg_noise_level    Float32,
    avg_battery_pct    Float32,
    min_battery_pct    UInt8,
    error_count        UInt32,
    active_hours       UInt8,      -- distinct hours with readings
    gestures           Map(String, UInt32),
    built_at           DateTime
)
ENGINE = ReplacingMergeTree(built_at)
PARTITION BY toYYYYMM(report_date)
ORDER BY (idp_user_id, report_date, prosthesis_serial);

-- Period already processed by the ETL. The API never reports beyond processed_until.
CREATE TABLE IF NOT EXISTS reports.etl_watermark
(
    pipeline        String,
    processed_until DateTime,
    dag_run_id      String,
    updated_at      DateTime
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY pipeline;
