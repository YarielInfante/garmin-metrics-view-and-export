"""App configuration: everything env-overridable, defaults per project spec.

Env vars use the GARMIN_APP_ prefix (except GARMIN_TOKEN_DIR, shared with
auth.py and garmin_mcp). Analytics targets are exposed to the frontend via
GET /api/config so charts stay config-driven.
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _f(name: str, default: float) -> float:
    return float(os.environ.get(f"GARMIN_APP_{name}", default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(f"GARMIN_APP_{name}", default))


def _s(name: str, default: str) -> str:
    return os.environ.get(f"GARMIN_APP_{name}", default)


@dataclass(frozen=True)
class Settings:
    # infrastructure
    token_dir: Path
    db_path: Path
    host: str
    port: int

    # freshness
    sync_interval_hours: float
    staleness_hours: float
    throttle_seconds: float
    detail_batch: int             # max per-activity detail fetches per sync run
    wellness_start: str           # explicit first date to backfill wellness (blank = use window below)
    wellness_backfill_days: int   # when wellness_start blank: how far back to backfill daily wellness
    activity_backfill_days: int
    rate_limit_cooldown_min: int  # base cooldown after a 429; doubles per repeat

    # analytics targets (defaults from project spec)
    cadence_band_low: float
    cadence_band_high: float
    ftp_fallback_w: float         # used only if Garmin has no FTP
    easy_zone_max: int            # zones <= this count as "easy" for 80/20
    easy_target_pct: float
    z2_cap_bpm_note: int          # user's nominal easy-day cap, display-only
    acwr_low: float
    acwr_high: float
    pool_length_m: float


def load_settings() -> Settings:
    return Settings(
        token_dir=Path(os.environ.get("GARMIN_TOKEN_DIR", "~/.garminconnect")).expanduser(),
        db_path=Path(_s("DB_PATH", str(REPO_ROOT / "data" / "garmin.duckdb"))),
        host=_s("HOST", "127.0.0.1"),
        port=_i("PORT", 8722),
        sync_interval_hours=_f("SYNC_INTERVAL_HOURS", 3.0),
        staleness_hours=_f("STALENESS_HOURS", 6.0),
        throttle_seconds=_f("THROTTLE_SECONDS", 1.0),
        detail_batch=_i("DETAIL_BATCH", 25),
        wellness_start=_s("WELLNESS_START", ""),  # blank = last WELLNESS_BACKFILL_DAYS days
        wellness_backfill_days=_i("WELLNESS_BACKFILL_DAYS", 180),
        activity_backfill_days=_i("ACTIVITY_BACKFILL_DAYS", 5 * 365),
        rate_limit_cooldown_min=_i("RATE_LIMIT_COOLDOWN_MIN", 120),
        cadence_band_low=_f("CADENCE_BAND_LOW", 165.0),
        cadence_band_high=_f("CADENCE_BAND_HIGH", 175.0),
        ftp_fallback_w=_f("FTP_FALLBACK_W", 200.0),
        easy_zone_max=_i("EASY_ZONE_MAX", 2),
        easy_target_pct=_f("EASY_TARGET_PCT", 80.0),
        z2_cap_bpm_note=_i("Z2_CAP_BPM_NOTE", 145),
        acwr_low=_f("ACWR_LOW", 0.8),
        acwr_high=_f("ACWR_HIGH", 1.3),
        pool_length_m=_f("POOL_LENGTH_M", 25.0),
    )
