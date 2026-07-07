"""API routes. Every GET here reads only local DuckDB — no Garmin calls,
ever — so pages render instantly regardless of sync/network state."""

import json
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from pydantic import BaseModel

from .auth_service import LoginNotInProgress
from .db import rows_to_dicts
from .export import build_raw_export

router = APIRouter(prefix="/api")

# user-editable training targets: key -> (type, min, max). Persisted per-instance
# in app_meta['targets'] as a JSON object of overrides over the env/config defaults.
_TARGET_SPEC = {
    "cadence_band_low": (float, 120, 220),
    "cadence_band_high": (float, 120, 220),
    "ftp_fallback_w": (float, 50, 600),
    "easy_zone_max": (int, 1, 5),
    "easy_target_pct": (float, 0, 100),
    "z2_cap_bpm_note": (int, 80, 220),
    "acwr_low": (float, 0, 3),
    "acwr_high": (float, 0, 3),
    "pool_length_m": (float, 10, 100),
}


def _db(request: Request):
    return request.app.state.db


def _persisted_targets(request: Request) -> dict:
    cur = _db(request).cursor()
    row = cur.execute("SELECT value FROM app_meta WHERE key = 'targets'").fetchone()
    return json.loads(row[0]) if row and row[0] else {}


def _effective_targets(request: Request) -> dict:
    """Env/config defaults overlaid with the user's persisted edits."""
    s = request.app.state.settings
    t = {
        "cadence_band_low": s.cadence_band_low, "cadence_band_high": s.cadence_band_high,
        "ftp_fallback_w": s.ftp_fallback_w, "easy_zone_max": s.easy_zone_max,
        "easy_target_pct": s.easy_target_pct, "z2_cap_bpm_note": s.z2_cap_bpm_note,
        "acwr_low": s.acwr_low, "acwr_high": s.acwr_high, "pool_length_m": s.pool_length_m,
    }
    t.update({k: v for k, v in _persisted_targets(request).items() if k in _TARGET_SPEC})
    t["easy_zone_max"] = max(1, min(5, int(t["easy_zone_max"])))  # SQL only produces z1..z5
    return t


def _q(request: Request, sql: str, params: list | None = None) -> list[dict]:
    cur = _db(request).cursor()
    cur.execute(sql, params or [])
    return rows_to_dicts(cur)


# ------------------------------------------------------------------ meta --

@router.get("/health")
def health():
    return {"ok": True}


@router.get("/config")
def config(request: Request):
    s = request.app.state.settings
    t = _effective_targets(request)
    return {
        "targets": {
            "cadence_band": [t["cadence_band_low"], t["cadence_band_high"]],
            "ftp_fallback_w": t["ftp_fallback_w"],
            "easy_zone_max": t["easy_zone_max"],
            "easy_target_pct": t["easy_target_pct"],
            "z2_cap_bpm_note": t["z2_cap_bpm_note"],
            "acwr_range": [t["acwr_low"], t["acwr_high"]],
            "pool_length_m": t["pool_length_m"],
        },
        "editable_targets": t,  # flat key/value form the Settings screen edits
        "sync": {
            "interval_hours": s.sync_interval_hours,
            "staleness_hours": s.staleness_hours,
        },
        "hr_zones": _q(request, "SELECT * FROM hr_zone_config"),
    }


class _TargetsBody(BaseModel):
    values: dict


@router.post("/config/targets")
def update_targets(request: Request, body: _TargetsBody):
    """Validate + persist edited training targets (partial updates allowed)."""
    persisted = _persisted_targets(request)
    for key, raw in body.values.items():
        if key not in _TARGET_SPEC:
            raise HTTPException(422, f"unknown target '{key}'")
        typ, lo, hi = _TARGET_SPEC[key]
        try:
            val = typ(raw)
        except (TypeError, ValueError):
            raise HTTPException(422, f"'{key}' must be a number")
        if not (lo <= val <= hi):
            raise HTTPException(422, f"'{key}' must be between {lo} and {hi}")
        persisted[key] = val
    merged = {**_effective_targets(request), **persisted}
    if merged["cadence_band_low"] > merged["cadence_band_high"]:
        raise HTTPException(422, "cadence band: low must be ≤ high")
    if merged["acwr_low"] > merged["acwr_high"]:
        raise HTTPException(422, "ACWR band: low must be ≤ high")
    cur = _db(request).cursor()
    cur.execute(
        "INSERT INTO app_meta (key, value) VALUES ('targets', ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        [json.dumps(persisted)],
    )
    return config(request)


@router.get("/sync/status")
def sync_status(request: Request):
    return request.app.state.engine.status()


@router.post("/sync/now")
def sync_now(request: Request):
    return request.app.state.engine.trigger("manual", force=True)


# ----------------------------------------------------------------- auth --

class _LoginBody(BaseModel):
    email: str
    password: str


class _MfaBody(BaseModel):
    code: str


@router.get("/auth/status")
def auth_status(request: Request):
    return request.app.state.auth.status()


@router.post("/auth/login")
def auth_login(request: Request, body: _LoginBody):
    """Garmin email/password login. Runs off the event loop (this is a plain
    def, so FastAPI runs it in a threadpool). Returns 'ok' or 'needs_mfa'."""
    try:
        return request.app.state.auth.begin_login(body.email.strip(), body.password)
    except GarminConnectAuthenticationError:
        raise HTTPException(401, "Garmin rejected those credentials — check your email and password.")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(429, "Garmin is rate-limiting logins. Wait at least an hour, then try again.")
    except GarminConnectConnectionError as exc:
        raise HTTPException(
            502,
            f"Couldn't complete the Garmin login: {exc}. If this mentions CAPTCHA or "
            "Cloudflare, sign in once at connect.garmin.com in a browser, wait a bit, and retry.",
        )


@router.post("/auth/mfa")
def auth_mfa(request: Request, body: _MfaBody):
    try:
        return request.app.state.auth.submit_mfa(body.code.strip())
    except LoginNotInProgress:
        raise HTTPException(409, "No login is in progress — start again with your email and password.")
    except GarminConnectAuthenticationError:
        raise HTTPException(401, "That code was rejected. Start over and enter a fresh MFA code.")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(429, "Garmin is rate-limiting logins. Wait at least an hour, then try again.")
    except GarminConnectConnectionError as exc:
        raise HTTPException(502, f"Couldn't complete the Garmin login: {exc}")


@router.post("/auth/logout")
def auth_logout(request: Request):
    return request.app.state.auth.logout()


# --------------------------------------------------------------- export --

@router.get("/export/raw")
def export_raw(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    include_details: int = 0,
):
    """Verbatim Garmin payloads for a date range, assembled from the local
    archive only. No Garmin call; nothing leaves the machine here."""
    try:
        end_d = date.fromisoformat(end) if end else date.today()
        start_d = date.fromisoformat(start) if start else date(2000, 1, 1)  # 'all'
    except ValueError as exc:
        raise HTTPException(422, f"bad date (use YYYY-MM-DD): {exc}") from exc
    if start_d > end_d:
        raise HTTPException(422, "start must be on or before end")
    cur = _db(request).cursor()
    return build_raw_export(cur, start_d, end_d, bool(include_details))


@router.get("/export/coverage")
def export_coverage(request: Request):
    """Earliest/latest archived dates + row counts, to seed the date picker."""
    rows = _q(request, """
        SELECT min(ref_date) AS earliest, max(ref_date) AS latest,
               count(*) FILTER (WHERE source = 'activity_summary') AS activities,
               count(DISTINCT ref_date) FILTER (WHERE ref_date IS NOT NULL) AS days,
               count(*) AS payloads
        FROM raw_payloads""")
    return rows[0] if rows else {}


# ------------------------------------------------------------ activities --

@router.get("/activities")
def activities(request: Request, sport: str | None = None, limit: int = 100):
    where = "WHERE sport = ?" if sport else ""
    params = [sport] if sport else []
    return _q(request, f"""
        SELECT activity_id, name, type_key, sport, start_time_local, duration_s,
               distance_m, avg_hr, training_load, details_synced
        FROM activities {where}
        ORDER BY start_time_local DESC LIMIT ?""", [*params, limit])


# --------------------------------------------------------------- summary --

@router.get("/summary/weekly")
def summary_weekly(request: Request, weeks: int = 16):
    return _q(request, """
        SELECT date_trunc('week', start_time_local)::DATE AS week, sport,
               count(*) AS sessions,
               sum(duration_s) AS duration_s,
               sum(distance_m) AS distance_m,
               sum(coalesce(training_load, 0)) AS training_load
        FROM activities
        WHERE start_time_local >= current_date - INTERVAL (? * 7) DAY
        GROUP BY 1, 2 ORDER BY 1, 2""", [weeks])


@router.get("/intensity/weekly")
def intensity_weekly(request: Request, weeks: int = 16):
    t = _effective_targets(request)  # easy_zone_max clamped to 1..5 here
    ez = t["easy_zone_max"]
    rows = _q(request, """
        SELECT date_trunc('week', start_time_local)::DATE AS week,
               sum(coalesce(hr_z1_s, 0)) AS z1, sum(coalesce(hr_z2_s, 0)) AS z2,
               sum(coalesce(hr_z3_s, 0)) AS z3, sum(coalesce(hr_z4_s, 0)) AS z4,
               sum(coalesce(hr_z5_s, 0)) AS z5
        FROM activities
        WHERE start_time_local >= current_date - INTERVAL (? * 7) DAY
        GROUP BY 1 ORDER BY 1""", [weeks])
    easy_zones = [f"z{i}" for i in range(1, ez + 1)]
    for r in rows:
        total = sum(r[f"z{i}"] for i in range(1, 6))
        easy = sum(r[z] for z in easy_zones)
        r["total_s"] = total
        r["easy_pct"] = round(easy / total * 100.0, 1) if total else None
        r["hard_pct"] = round(100.0 - r["easy_pct"], 1) if total else None
    return {"weeks": rows, "easy_target_pct": t["easy_target_pct"], "easy_zone_max": ez}


@router.get("/load/daily")
def load_daily(request: Request, days: int = 120):
    t = _effective_targets(request)
    rows = _q(request, """
        WITH bounds AS (
            SELECT greatest(coalesce(min(start_time_local)::DATE, current_date),
                            current_date - INTERVAL (?) DAY) AS min_d
            FROM activities
        ),
        days AS (
            SELECT unnest(generate_series(min_d, current_date, INTERVAL 1 DAY))::DATE AS date
            FROM bounds
        ),
        daily AS (
            SELECT start_time_local::DATE AS date, sum(coalesce(training_load, 0)) AS load
            FROM activities GROUP BY 1
        )
        SELECT d.date,
               coalesce(l.load, 0) AS daily_load,
               -- Garmin-comparable: acute = 7d sum, chronic = 28d sum scaled to a week
               sum(coalesce(l.load, 0)) OVER w7        AS acute_local,
               sum(coalesce(l.load, 0)) OVER w28 / 4.0 AS chronic_local,
               ts.acute_load AS acute_garmin,
               ts.chronic_load AS chronic_garmin,
               ts.acwr AS acwr_garmin,
               ts.acwr_status,
               ts.feedback_phrase,
               tr.score AS readiness_score,
               tr.level AS readiness_level
        FROM days d
        LEFT JOIN daily l USING (date)
        LEFT JOIN training_status ts ON ts.date = d.date
        LEFT JOIN training_readiness tr ON tr.date = d.date
        WINDOW w7  AS (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
               w28 AS (ORDER BY d.date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW)
        ORDER BY d.date""", [days])
    for r in rows:
        c = r["chronic_local"]
        r["acwr_local"] = round(r["acute_local"] / c, 2) if c else None
    return {"days": rows, "acwr_range": [t["acwr_low"], t["acwr_high"]]}


@router.get("/wellness/daily")
def wellness_daily(request: Request, days: int = 90):
    return _q(request, """
        SELECT w.*, r.score AS readiness_score, r.level AS readiness_level,
               ts.vo2max_running, ts.vo2max_cycling
        FROM daily_wellness w
        LEFT JOIN training_readiness r USING (date)
        LEFT JOIN training_status ts USING (date)
        WHERE w.date >= current_date - INTERVAL (?) DAY
        ORDER BY w.date""", [days])


# --------------------------------------------------------------- running --

@router.get("/running/trends")
def running_trends(request: Request, limit: int = 200):
    rows = _q(request, """
        SELECT activity_id, name, start_time_local, distance_m, duration_s,
               moving_duration_s, avg_hr, max_hr,
               avg_cadence_spm, max_cadence_spm,
               avg_vertical_osc_cm, avg_gct_ms, avg_vertical_ratio_pct,
               avg_stride_len_cm, avg_gct_balance_pct,
               avg_power_w, norm_power_w, avg_gas_ms,
               aerobic_decoupling_pct, training_load, vo2max,
               hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
        FROM activities WHERE sport = 'run'
        ORDER BY start_time_local DESC LIMIT ?""", [limit])
    for r in rows:
        km = (r["distance_m"] or 0) / 1000.0
        r["pace_s_per_km"] = round(r["duration_s"] / km, 1) if km > 0.1 else None
    return list(reversed(rows))


@router.get("/running/weekly")
def running_weekly(request: Request, weeks: int = 16):
    return _q(request, """
        SELECT date_trunc('week', start_time_local)::DATE AS week,
               count(*) AS runs,
               sum(distance_m) AS distance_m,
               sum(duration_s) AS duration_s,
               sum(duration_s) / nullif(sum(distance_m) / 1000.0, 0) AS pace_s_per_km,
               sum(duration_s * coalesce(avg_hr, 0)) / nullif(sum(duration_s * (avg_hr IS NOT NULL)::INT), 0) AS avg_hr,
               sum(coalesce(hr_z1_s,0)) AS z1, sum(coalesce(hr_z2_s,0)) AS z2, sum(coalesce(hr_z3_s,0)) AS z3,
               sum(coalesce(hr_z4_s,0)) AS z4, sum(coalesce(hr_z5_s,0)) AS z5
        FROM activities WHERE sport = 'run'
          AND start_time_local >= current_date - INTERVAL (? * 7) DAY
        GROUP BY 1 ORDER BY 1""", [weeks])


@router.get("/activities/{activity_id}/samples")
def activity_samples(request: Request, activity_id: int, every: int = 1):
    rows = _q(request, """
        SELECT elapsed_s, distance_m, hr, speed_ms, gas_ms, power_w, cadence_spm,
               vertical_osc_cm, gct_ms, vertical_ratio, stride_len_cm, elevation_m
        FROM activity_samples WHERE activity_id = ? ORDER BY elapsed_s""", [activity_id])
    if not rows:
        raise HTTPException(404, "no samples for this activity (details not synced yet?)")
    return rows[::max(1, every)]


# --------------------------------------------------------------- cycling --

@router.get("/cycling/trends")
def cycling_trends(request: Request, limit: int = 200):
    rides = _q(request, """
        SELECT activity_id, name, start_time_local, distance_m, duration_s,
               avg_speed_ms, max_speed_ms, avg_hr, max_hr, elevation_gain_m,
               avg_power_w, norm_power_w, training_load,
               hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
        FROM activities WHERE sport = 'ride'
        ORDER BY start_time_local DESC LIMIT ?""", [limit])
    ftp = _q(request, "SELECT calendar_date, value FROM biometrics WHERE metric = 'cycling_ftp_w' ORDER BY 1")
    weight = _q(request, "SELECT calendar_date, value FROM biometrics WHERE metric = 'weight_kg' ORDER BY 1")
    pdc = _q(request, """
        SELECT pc.duration_s, max(pc.max_avg_power_w) AS best_w
        FROM power_curve pc JOIN activities a USING (activity_id)
        WHERE a.sport = 'ride' GROUP BY 1 ORDER BY 1""")
    t = _effective_targets(request)
    has_rides = len(rides) > 0
    # Garmin FTP wins; else the config fallback only if there are rides; else none
    # (don't present a fallback FTP as a real value to a non-cyclist).
    current_ftp = ftp[-1]["value"] if ftp else (t["ftp_fallback_w"] if has_rides else None)
    ftp_source = "garmin" if ftp else ("config_fallback" if has_rides else "none")
    current_weight = weight[-1]["value"] if weight else None
    return {
        "rides": list(reversed(rides)),
        "ftp_history": ftp,
        "current_ftp_w": current_ftp,
        "ftp_source": ftp_source,
        "weight_kg": current_weight,
        "w_per_kg": round(current_ftp / current_weight, 2) if (current_ftp and current_weight) else None,
        "power_duration_curve": pdc,
        "has_ride_power": any(r["avg_power_w"] for r in rides),
    }


# -------------------------------------------------------------- swimming --

@router.get("/swimming/trends")
def swimming_trends(request: Request, limit: int = 200):
    rows = _q(request, """
        SELECT activity_id, name, start_time_local, distance_m, duration_s,
               moving_duration_s, avg_hr, pool_length_m, active_lengths,
               avg_swolf, avg_strokes_per_length, avg_swim_cadence,
               total_strokes, fastest_100m_s, training_load
        FROM activities WHERE sport = 'swim'
        ORDER BY start_time_local DESC LIMIT ?""", [limit])
    for r in rows:
        d = r["distance_m"] or 0
        r["pace_per_100m_s"] = round(r["duration_s"] / d * 100.0, 1) if d > 0 else None
    return list(reversed(rows))


@router.get("/swimming/sessions/{activity_id}")
def swim_session(request: Request, activity_id: int):
    activity = _q(request, "SELECT * EXCLUDE (raw) FROM activities WHERE activity_id = ?", [activity_id])
    if not activity:
        raise HTTPException(404, "unknown activity")
    intervals = _q(request, """
        SELECT * EXCLUDE (raw) FROM swim_intervals
        WHERE activity_id = ? ORDER BY interval_index""", [activity_id])
    lengths = _q(request, """
        SELECT * FROM swim_lengths
        WHERE activity_id = ? ORDER BY length_index""", [activity_id])
    return {"activity": activity[0], "intervals": intervals, "lengths": lengths}
