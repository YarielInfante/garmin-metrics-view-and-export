"""DuckDB storage.

One process owns the file. A single duckdb connection is shared; every
consumer takes a cursor (thread-safe entry point onto the same database).
Writes happen only inside the sync engine, serialized by its own lock, so
readers are never blocked on Garmin calls.
"""

import threading
from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id            BIGINT PRIMARY KEY,
    name                   VARCHAR,
    type_key               VARCHAR,
    sport                  VARCHAR,      -- run | ride | swim | strength | walk | mobility | other
    start_time_utc         TIMESTAMP,
    start_time_local       TIMESTAMP,
    duration_s             DOUBLE,
    moving_duration_s      DOUBLE,
    elapsed_duration_s     DOUBLE,
    distance_m             DOUBLE,
    avg_speed_ms           DOUBLE,
    max_speed_ms           DOUBLE,
    avg_hr                 DOUBLE,
    max_hr                 DOUBLE,
    calories               DOUBLE,
    training_load          DOUBLE,
    aerobic_te             DOUBLE,
    anaerobic_te           DOUBLE,
    te_label               VARCHAR,
    vo2max                 DOUBLE,
    steps                  BIGINT,
    hr_z1_s DOUBLE, hr_z2_s DOUBLE, hr_z3_s DOUBLE, hr_z4_s DOUBLE, hr_z5_s DOUBLE,
    power_z1_s DOUBLE, power_z2_s DOUBLE, power_z3_s DOUBLE, power_z4_s DOUBLE, power_z5_s DOUBLE,
    avg_power_w            DOUBLE,
    max_power_w            DOUBLE,
    norm_power_w           DOUBLE,
    avg_cadence_spm        DOUBLE,
    max_cadence_spm        DOUBLE,
    avg_vertical_osc_cm    DOUBLE,
    avg_gct_ms             DOUBLE,
    avg_vertical_ratio_pct DOUBLE,
    avg_stride_len_cm      DOUBLE,
    avg_gct_balance_pct    DOUBLE,      -- absent without HRM strap
    avg_gas_ms             DOUBLE,      -- grade-adjusted speed
    elevation_gain_m       DOUBLE,
    elevation_loss_m       DOUBLE,
    start_lat              DOUBLE,
    start_lon              DOUBLE,
    location_name          VARCHAR,
    pool_length_m          DOUBLE,
    active_lengths         BIGINT,
    avg_swolf              DOUBLE,
    avg_strokes_per_length DOUBLE,
    avg_swim_cadence       DOUBLE,
    total_strokes          DOUBLE,
    fastest_100m_s         DOUBLE,
    fastest_1000m_s        DOUBLE,
    moderate_im            BIGINT,
    vigorous_im            BIGINT,
    water_estimated_ml     DOUBLE,
    bb_diff                BIGINT,
    device_id              BIGINT,
    pr                     BOOLEAN,
    aerobic_decoupling_pct DOUBLE,      -- derived at detail ingest
    details_synced         BOOLEAN DEFAULT FALSE,
    detail_error           VARCHAR,
    raw                    VARCHAR,
    ingested_at            TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS activity_samples (
    activity_id     BIGINT,
    ts_utc          TIMESTAMP,
    elapsed_s       DOUBLE,
    distance_m      DOUBLE,
    hr              DOUBLE,
    speed_ms        DOUBLE,
    gas_ms          DOUBLE,
    power_w         DOUBLE,
    cadence_spm     DOUBLE,
    vertical_osc_cm DOUBLE,
    gct_ms          DOUBLE,
    vertical_ratio  DOUBLE,
    stride_len_cm   DOUBLE,
    elevation_m     DOUBLE,
    body_battery    DOUBLE,
    stamina_pct     DOUBLE,
    PRIMARY KEY (activity_id, elapsed_s)
);

CREATE TABLE IF NOT EXISTS activity_laps (
    activity_id     BIGINT,
    lap_index       INTEGER,
    start_time_utc  TIMESTAMP,
    duration_s      DOUBLE,
    distance_m      DOUBLE,
    avg_speed_ms    DOUBLE,
    avg_hr          DOUBLE,
    max_hr          DOUBLE,
    avg_power_w     DOUBLE,
    norm_power_w    DOUBLE,
    avg_cadence_spm DOUBLE,
    avg_vertical_osc_cm DOUBLE,
    avg_gct_ms      DOUBLE,
    avg_vertical_ratio_pct DOUBLE,
    avg_stride_len_cm DOUBLE,
    elevation_gain_m DOUBLE,
    raw             VARCHAR,
    PRIMARY KEY (activity_id, lap_index)
);

CREATE TABLE IF NOT EXISTS swim_intervals (
    activity_id     BIGINT,
    interval_index  INTEGER,     -- lapIndex from Garmin, 1-based
    interval_type   VARCHAR,     -- ACTIVE | REST
    start_time_utc  TIMESTAMP,
    duration_s      DOUBLE,
    distance_m      DOUBLE,
    pace_per_100m_s DOUBLE,
    num_lengths     INTEGER,
    total_strokes   DOUBLE,
    avg_strokes_per_length DOUBLE,
    avg_swolf       DOUBLE,
    avg_swim_cadence DOUBLE,
    avg_hr          DOUBLE,
    max_hr          DOUBLE,
    stroke_type     VARCHAR,
    raw             VARCHAR,
    PRIMARY KEY (activity_id, interval_index)
);

CREATE TABLE IF NOT EXISTS swim_lengths (
    activity_id     BIGINT,
    interval_index  INTEGER,
    length_index    INTEGER,     -- lengthIndex from Garmin, 1-based, unique per activity
    start_time_utc  TIMESTAMP,
    duration_s      DOUBLE,
    distance_m      DOUBLE,
    pace_per_100m_s DOUBLE,
    strokes         INTEGER,
    swolf           DOUBLE,
    avg_hr          DOUBLE,
    max_hr          DOUBLE,
    stroke_type     VARCHAR,
    PRIMARY KEY (activity_id, length_index)
);

CREATE TABLE IF NOT EXISTS power_curve (
    activity_id     BIGINT,
    duration_s      INTEGER,
    max_avg_power_w DOUBLE,
    PRIMARY KEY (activity_id, duration_s)
);

CREATE TABLE IF NOT EXISTS daily_wellness (
    date            DATE PRIMARY KEY,
    resting_hr      DOUBLE,
    hrv_last_night_ms DOUBLE,
    hrv_weekly_avg_ms DOUBLE,
    hrv_status      VARCHAR,
    sleep_s         DOUBLE,
    sleep_deep_s    DOUBLE,
    sleep_light_s   DOUBLE,
    sleep_rem_s     DOUBLE,
    sleep_awake_s   DOUBLE,
    sleep_score     DOUBLE,
    overnight_hrv_ms DOUBLE,
    bb_change_sleep DOUBLE,
    steps           BIGINT,
    total_kcal      DOUBLE,
    min_hr          DOUBLE,
    max_hr          DOUBLE,
    stress_avg      DOUBLE,
    stress_max      DOUBLE,
    bb_charged      DOUBLE,
    bb_drained      DOUBLE,
    bb_high         DOUBLE,
    bb_low          DOUBLE,
    moderate_im     BIGINT,
    vigorous_im     BIGINT
);

CREATE TABLE IF NOT EXISTS training_status (
    date            DATE PRIMARY KEY,
    acute_load      DOUBLE,
    chronic_load    DOUBLE,
    acwr            DOUBLE,
    acwr_pct        DOUBLE,
    acwr_status     VARCHAR,
    feedback_phrase VARCHAR,
    status_code     INTEGER,
    vo2max_running  DOUBLE,
    vo2max_cycling  DOUBLE
);

CREATE TABLE IF NOT EXISTS training_readiness (
    date            DATE PRIMARY KEY,
    score           DOUBLE,
    level           VARCHAR,
    feedback_short  VARCHAR,
    sleep_score     DOUBLE,
    hrv_factor_pct  DOUBLE,
    recovery_time_min DOUBLE,
    acute_load      DOUBLE,
    input_context   VARCHAR
);

CREATE TABLE IF NOT EXISTS biometrics (
    metric          VARCHAR,     -- cycling_ftp_w | running_ftp_w | lthr_bpm | lt_speed_ms | weight_kg | race_5k_s | ...
    calendar_date   DATE,
    value           DOUBLE,
    PRIMARY KEY (metric, calendar_date)
);

CREATE TABLE IF NOT EXISTS hr_zone_config (
    sport           VARCHAR PRIMARY KEY,
    training_method VARCHAR,
    z1_floor INTEGER, z2_floor INTEGER, z3_floor INTEGER, z4_floor INTEGER, z5_floor INTEGER,
    max_hr          INTEGER,
    lthr            INTEGER,
    resting_hr      INTEGER,
    updated_at      TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS sync_state (
    source          VARCHAR PRIMARY KEY,   -- activities | wellness | global
    watermark       VARCHAR,
    last_success_at TIMESTAMP,
    status          VARCHAR,
    error           VARCHAR,
    consecutive_failures INTEGER DEFAULT 0
);

CREATE SEQUENCE IF NOT EXISTS seq_sync_runs;
CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_sync_runs'),
    trigger     VARCHAR,
    started_at  TIMESTAMP,
    finished_at TIMESTAMP,
    status      VARCHAR,      -- ok | error | rate_limited | auth_required
    error       VARCHAR,
    stats       VARCHAR       -- JSON: counts per phase
);

-- Complete verbatim archive of every Garmin payload we fetch. The derived
-- tables above are a curated projection for the dashboard, whereas this is
-- the lossless record the Export tab hands out. One row per endpoint+entity,
-- upserted every sync so re-syncing dedups in place. payload is raw JSON text.
CREATE TABLE IF NOT EXISTS raw_payloads (
    source     VARCHAR,       -- activity_summary | activity | activity_details | activity_splits
                              -- | user_summary | hrv | sleep | stress | training_status
                              -- | training_readiness | max_metrics | body_battery_events
                              -- | cycling_ftp | lactate_threshold | race_predictions
                              -- | hr_zones | user_profile
    entity_key VARCHAR,       -- activityId | ISO date | 'latest' (current-state singletons)
    ref_date   DATE,          -- activity start date / daily calendar date (NULL for singletons)
    fetched_at TIMESTAMP DEFAULT current_timestamp,
    payload    VARCHAR,       -- the raw Garmin response, verbatim (JSON text)
    PRIMARY KEY (source, entity_key)
);

-- small key/value store for app-level state (e.g. the Garmin profile display name)
CREATE TABLE IF NOT EXISTS app_meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);
"""

# Bump when a migration must run once against existing databases.
RAW_SCHEMA_VERSION = 3


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(path))
        self.write_lock = threading.Lock()
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                self._conn.execute(stmt)
        self._migrate()

    def _migrate(self) -> None:
        """Idempotent, run-once backfill for the raw archive (guarded by a
        schema_version row). Seeds activity_summary raw from the retained
        activities.raw column, then resets the detail flag and wellness
        watermark so the next sync repopulates the rest of raw_payloads."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT watermark FROM sync_state WHERE source = 'schema_version'"
        ).fetchone()
        current = int(row[0]) if row and row[0] else 0
        if current >= RAW_SCHEMA_VERSION:
            return
        if current < 2:
            # v2: seed the raw archive from existing derived data, then force a
            # one-time re-pull of details/wellness so raw_payloads fills.
            cur.execute(
                "INSERT INTO raw_payloads (source, entity_key, ref_date, fetched_at, payload) "
                "SELECT 'activity_summary', CAST(activity_id AS VARCHAR), "
                "       CAST(start_time_local AS DATE), current_timestamp, raw "
                "FROM activities WHERE raw IS NOT NULL "
                "ON CONFLICT (source, entity_key) DO NOTHING"
            )
            cur.execute("UPDATE activities SET details_synced = FALSE")
            cur.execute("DELETE FROM sync_state WHERE source = 'wellness'")
        # v3: app_meta table (created by SCHEMA above) — no backfill needed.
        cur.execute(
            "INSERT INTO sync_state (source, watermark) VALUES ('schema_version', ?) "
            "ON CONFLICT (source) DO UPDATE SET watermark = excluded.watermark",
            [str(RAW_SCHEMA_VERSION)],
        )

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self._conn.cursor()

    def close(self) -> None:
        self._conn.close()


def rows_to_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
