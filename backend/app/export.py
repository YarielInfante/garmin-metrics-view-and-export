"""Raw export: assemble the verbatim Garmin payloads for a date range.

Reads ONLY the local raw_payloads archive — no Garmin, no network. The
envelope is organized (current thresholds up front, then activities, then
per-day wellness) but every leaf value is the raw Garmin JSON, untouched,
so it can be pasted straight into a Claude chat.
"""

import json
from datetime import date, datetime, timezone

# per-activity payloads, and whether each is gated behind include_details
_ACTIVITY_SOURCES = [
    ("activity_summary", "summary", False),   # the cheap list entry
    ("activity", "activity", False),          # get_activity: summaryDTO + splitSummaries
    ("activity_details", "details", True),    # per-second streams (large)
    ("activity_splits", "splits", True),      # per-lap / per-length (large)
]

_DAILY_SOURCES = [
    "user_summary", "hrv", "sleep", "stress",
    "training_status", "training_readiness", "max_metrics", "body_battery_events",
]

_CONFIG_SOURCES = ["hr_zones", "cycling_ftp", "lactate_threshold", "race_predictions", "user_profile"]


def _loads(text: str | None):
    return json.loads(text) if text else None


def build_raw_export(cur, start: date, end: date, include_details: bool) -> dict:
    # current-state config singletons (always included, they describe the athlete)
    config: dict = {}
    for source in _CONFIG_SOURCES:
        row = cur.execute(
            "SELECT payload FROM raw_payloads WHERE source = ? AND entity_key = 'latest'",
            [source],
        ).fetchone()
        config[source] = _loads(row[0]) if row else None

    # activities whose start date is in range
    activities: list[dict] = []
    act_ids = cur.execute(
        "SELECT entity_key, ref_date FROM raw_payloads "
        "WHERE source = 'activity_summary' AND ref_date BETWEEN ? AND ? "
        "ORDER BY ref_date, entity_key",
        [start, end],
    ).fetchall()
    for entity_key, ref_date in act_ids:
        entry = {
            "activity_id": int(entity_key),
            "date": ref_date.isoformat() if ref_date else None,
        }
        for source, key, gated in _ACTIVITY_SOURCES:
            if gated and not include_details:
                continue
            row = cur.execute(
                "SELECT payload FROM raw_payloads WHERE source = ? AND entity_key = ?",
                [source, entity_key],
            ).fetchone()
            if row and row[0]:
                entry[key] = _loads(row[0])
        activities.append(entry)

    # daily wellness grouped by calendar date
    daily: dict[str, dict] = {}
    placeholders = ", ".join("?" for _ in _DAILY_SOURCES)
    rows = cur.execute(
        f"SELECT source, entity_key, payload FROM raw_payloads "
        f"WHERE source IN ({placeholders}) AND ref_date BETWEEN ? AND ? "
        f"ORDER BY entity_key",
        [*_DAILY_SOURCES, start, end],
    ).fetchall()
    for source, entity_key, payload in rows:
        daily.setdefault(entity_key, {})[source] = _loads(payload)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z",
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "include_details": include_details,
        "coverage": {"activities": len(activities), "days": len(daily)},
        "athlete_config": config,
        "activities": activities,
        "daily": dict(sorted(daily.items())),
    }
