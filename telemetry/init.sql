-- Emulated telemetry database: the operational PostgreSQL that the API fills with readings
-- sent by the prosthesis chip. Seeded with 30 days of readings; the simulator keeps appending.

CREATE TABLE telemetry (
    id                BIGSERIAL PRIMARY KEY,
    prosthesis_serial TEXT        NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL,
    gesture           TEXT        NOT NULL,   -- recognised movement
    reaction_ms       INTEGER     NOT NULL,   -- myo-signal to actuator latency
    myo_noise_level   NUMERIC(4,3) NOT NULL,  -- 0..1, share of noise in the myo signal
    battery_pct       SMALLINT    NOT NULL,
    error_code        TEXT        NULL        -- actuator / BMS error, NULL when fine
);

CREATE INDEX telemetry_recorded_at_idx ON telemetry (recorded_at);

SELECT setseed(0.42);

-- One reading every 3 minutes per prosthesis for the last 30 days (~57k rows).
INSERT INTO telemetry (prosthesis_serial, recorded_at, gesture, reaction_ms, myo_noise_level, battery_pct, error_code)
SELECT
    s.serial,
    t.ts,
    (ARRAY['grip', 'release', 'pinch', 'point', 'rotate', 'rest'])[1 + floor(random() * 6)::int],
    GREATEST(35, LEAST(260, round(s.base_ms + (random() - 0.5) * 60 + CASE WHEN random() < 0.08 THEN 90 ELSE 0 END)))::int,
    round((0.05 + random() * 0.30 + CASE WHEN extract(hour FROM t.ts) BETWEEN 7 AND 9 THEN 0.10 ELSE 0 END)::numeric, 3),
    GREATEST(5, 100 - ((extract(epoch FROM t.ts)::bigint / 60 / 3) % 480) / 5)::smallint,
    CASE WHEN random() < 0.004 THEN (ARRAY['ACT_OVERCURRENT', 'BMS_OVERHEAT', 'SENSOR_DROPOUT'])[1 + floor(random() * 3)::int] END
FROM (VALUES ('BP-ARM-2024-0001', 78), ('BP-ARM-2024-0002', 92), ('BP-HND-2025-0003', 70), ('BP-ARM-2025-0004', 64)) AS s(serial, base_ms)
CROSS JOIN generate_series(now() - interval '30 days', now(), interval '3 minutes') AS t(ts);
