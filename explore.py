#!/usr/bin/env python3
"""STEP 1 exploration (throwaway): inspect what the FR970 actually populates.

Usage (after auth.py has been run once):
    .venv/bin/python explore.py

Pulls a representative sample — recent activities across running / cycling /
swimming with full detail payloads, plus a week of daily wellness — saves raw
JSON payloads into fixtures/, and prints a field-level report. The real data
layer gets built from what this finds, not from assumptions.

Read-only against Garmin; throttled to one call per second.
"""

import json
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_DIR = Path(os.environ.get("GARMIN_TOKEN_DIR", "~/.garminconnect")).expanduser()
FIXTURES = Path(__file__).parent / "fixtures"
THROTTLE_SECONDS = 1.0

RUN_TYPES = {"running", "trail_running", "treadmill_running", "track_running"}
RIDE_TYPES = {"cycling", "road_biking", "gravel_cycling", "indoor_cycling", "virtual_ride", "mountain_biking"}
POOL_SWIM_TYPES = {"lap_swimming"}
OWS_TYPES = {"open_water_swimming"}


def fetch(label, fn, *args, **kwargs):
    """Call one API method, throttled; return None instead of raising."""
    time.sleep(THROTTLE_SECONDS)
    try:
        result = fn(*args, **kwargs)
        status = "empty" if result in (None, [], {}) else "ok"
        print(f"  [{status:5}] {label}")
        return result
    except GarminConnectTooManyRequestsError:
        print("\nGarmin returned 429 (rate limited). Stopping — re-run later.", file=sys.stderr)
        sys.exit(3)
    except (GarminConnectConnectionError, ValueError) as exc:
        print(f"  [error] {label}: {exc}")
        return None


def save_fixture(name, payload):
    if payload in (None, [], {}):
        return
    path = FIXTURES / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  saved fixtures/{name}.json")


def type_key(activity):
    return (activity.get("activityType") or {}).get("typeKey", "unknown")


def explore_activity(api, activity, sport, with_power=False, with_typed_splits=False):
    """Pull every detail endpoint for one activity and fixture the payloads."""
    act_id = activity["activityId"]
    print(f"\n-- {sport}: {activity.get('activityName')} ({activity.get('startTimeLocal')}) id={act_id}")
    save_fixture(f"{sport}_summary_list_entry", activity)
    save_fixture(f"{sport}_activity", fetch("get_activity", api.get_activity, act_id))
    details = fetch("get_activity_details", api.get_activity_details, act_id)
    save_fixture(f"{sport}_details", details)
    save_fixture(f"{sport}_splits", fetch("get_activity_splits", api.get_activity_splits, act_id))
    save_fixture(f"{sport}_hr_zones", fetch("get_activity_hr_in_timezones", api.get_activity_hr_in_timezones, act_id))
    if with_power:
        save_fixture(f"{sport}_power_zones", fetch("get_activity_power_in_timezones", api.get_activity_power_in_timezones, act_id))
    if with_typed_splits:
        save_fixture(f"{sport}_typed_splits", fetch("get_activity_typed_splits", api.get_activity_typed_splits, act_id))
        save_fixture(f"{sport}_split_summaries", fetch("get_activity_split_summaries", api.get_activity_split_summaries, act_id))
    if details and details.get("metricDescriptors"):
        keys = sorted(d.get("key", "?") for d in details["metricDescriptors"])
        print(f"  {len(keys)} sample metrics: {', '.join(keys)}")


def main() -> int:
    if not (TOKEN_DIR / "garmin_tokens.json").exists():
        print(f"No tokens at {TOKEN_DIR}. Run:  .venv/bin/python auth.py", file=sys.stderr)
        return 2

    api = Garmin()
    try:
        api.login(str(TOKEN_DIR))
    except GarminConnectAuthenticationError as exc:
        print(f"Saved tokens were rejected ({exc}).\nRe-authenticate with:  .venv/bin/python auth.py", file=sys.stderr)
        return 2

    FIXTURES.mkdir(exist_ok=True)
    print(f"Logged in as {api.get_full_name()} (unit system: {api.get_unit_system()})")

    # --- profile, zones, devices -----------------------------------------
    print("\n== Profile / settings ==")
    save_fixture("user_profile", fetch("get_user_profile", api.get_user_profile))
    save_fixture("hr_zones_config", fetch("heartRateZones (raw)", api.connectapi, "/biometric-service/heartRateZones"))
    save_fixture("primary_device", fetch("get_primary_training_device", api.get_primary_training_device))

    # --- activity census ---------------------------------------------------
    print("\n== Activity census (last ~1 year) ==")
    today = date.today()
    year_ago = today - timedelta(days=365)
    activities = fetch(
        "get_activities_by_date (1y)", api.get_activities_by_date, year_ago.isoformat(), today.isoformat()
    ) or []
    counts = Counter(type_key(a) for a in activities)
    print(f"  {len(activities)} activities in the last year:")
    for key, n in counts.most_common():
        print(f"    {key:30} {n}")
    save_fixture("activities_list_sample", activities[:5])

    def newest(types):
        return next((a for a in activities if type_key(a) in types), None)

    # --- per-sport deep dives ---------------------------------------------
    run, ride, pool, ows = newest(RUN_TYPES), newest(RIDE_TYPES), newest(POOL_SWIM_TYPES), newest(OWS_TYPES)
    if run:
        explore_activity(api, run, "run")
    if ride:
        explore_activity(api, ride, "ride", with_power=True)
    if pool:
        explore_activity(api, pool, "swim_pool", with_typed_splits=True)
    if ows:
        explore_activity(api, ows, "swim_ows")
    for sport, act in [("run", run), ("ride", ride), ("pool swim", pool), ("open-water swim", ows)]:
        if not act:
            print(f"  (no {sport} found in the last year)")

    # --- daily wellness: which endpoints have data, last 7 days ------------
    print("\n== Daily wellness (last 7 days) ==")
    daily_endpoints = {
        "hrv": api.get_hrv_data,
        "sleep": api.get_sleep_data,
        "rhr": api.get_rhr_day,
        "stress": api.get_stress_data,
        "training_status": api.get_training_status,
        "training_readiness": api.get_training_readiness,
        "user_summary": api.get_user_summary,
        "max_metrics_vo2": api.get_max_metrics,
    }
    presence = {}
    fixture_done = set()
    for offset in range(1, 8):  # yesterday back 7 days; today is often partial
        d = (today - timedelta(days=offset)).isoformat()
        for name, fn in daily_endpoints.items():
            payload = fetch(f"{name} {d}", fn, d)
            has = payload not in (None, [], {})
            presence.setdefault(name, []).append((d, has))
            if has and name not in fixture_done:
                save_fixture(f"daily_{name}", payload)
                fixture_done.add(name)
        if fixture_done == set(daily_endpoints):
            break  # one populated fixture of each is enough

    save_fixture(
        "daily_body_battery",
        fetch("body_battery (7d)", api.get_body_battery, (today - timedelta(days=7)).isoformat(), today.isoformat()),
    )

    # --- biometrics / predictions -------------------------------------------
    print("\n== Biometrics ==")
    save_fixture("cycling_ftp", fetch("get_cycling_ftp", api.get_cycling_ftp))
    save_fixture("lactate_threshold", fetch("get_lactate_threshold", api.get_lactate_threshold))
    save_fixture("race_predictions", fetch("get_race_predictions", api.get_race_predictions))

    # --- report ----------------------------------------------------------
    print("\n== Wellness endpoint presence (per day) ==")
    for name, days in presence.items():
        marks = " ".join(f"{d[5:]}:{'Y' if has else '-'}" for d, has in days)
        print(f"  {name:20} {marks}")

    print(f"\nDone. Fixtures in {FIXTURES}/ — build the schema from these.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
