"""Incremental sync engine.

Principles:
- NEVER refetch everything: per-source watermarks (activities: newest local
  start time; wellness: last fully-synced date) bound every run.
- The activities LIST already carries zones/load/dynamics/swolf, so the hot
  path is one cheap call; per-activity details are fetched once, ever.
- One sync at a time (lock). Readers never wait: all writes are quick local
  DuckDB transactions after the network I/O has completed.
- 429 is a hard stop with an exponential cooldown (base doubles per repeat).
- Auth failure flips a state the UI surfaces; it never crashes the app.
"""

import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone

from . import normalize
from .config import Settings
from .db import Database
from .derive import aerobic_decoupling_pct, power_curve
from .garmin_client import AuthRequired, GarminClient, GarminUnavailable, RateLimited, REAUTH_COMMAND

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

DETAIL_SPORTS = {"run", "ride", "swim"}  # strength/walk/mobility need no time series


def _upsert(cur, table: str, row: dict, pk: list[str]) -> None:
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    non_pk = [c for c in cols if c not in pk]
    set_clause = ", ".join(f"{c}=excluded.{c}" for c in non_pk)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {set_clause}"
    )
    cur.execute(sql, [row[c] for c in cols])


def _store_raw(cur, source: str, entity_key, ref_date, payload) -> None:
    """Archive one Garmin payload verbatim. No-op for empty/absent payloads.
    Upsert on (source, entity_key) dedups: re-syncing overwrites in place."""
    if payload in (None, [], {}):
        return
    _upsert(cur, "raw_payloads", {
        "source": source,
        "entity_key": str(entity_key),
        "ref_date": ref_date,
        "fetched_at": utcnow(),
        "payload": json.dumps(payload, default=str),
    }, pk=["source", "entity_key"])


class SyncEngine:
    def __init__(self, db: Database, client: GarminClient, settings: Settings):
        self.db = db
        self.client = client
        self.settings = settings
        self._lock = threading.Lock()
        self._trigger_mutex = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._phase: str | None = None
        self._auth_required_msg: str | None = None

    def shutdown(self, timeout: float = 30.0) -> None:
        """Ask an in-flight sync to stop at the next boundary and wait for it."""
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise GarminUnavailable("shutdown requested")

    @property
    def auth_required(self) -> bool:
        """True when a sync hit an unrecoverable auth failure (tokens revoked/expired)."""
        return self._auth_required_msg is not None

    def clear_auth_required(self) -> None:
        """Fresh valid tokens just landed via the in-app login — drop the stale
        revoked-tokens flag now so the auth gate flips immediately, without
        waiting for the triggered background sync (which could itself 429)."""
        self._auth_required_msg = None

    # ------------------------------------------------------------- state --

    def _get_state(self, source: str) -> dict | None:
        cur = self.db.cursor()
        row = cur.execute(
            "SELECT watermark, last_success_at, status, error, consecutive_failures "
            "FROM sync_state WHERE source = ?", [source]
        ).fetchone()
        if not row:
            return None
        return dict(zip(["watermark", "last_success_at", "status", "error", "consecutive_failures"], row))

    def _set_state(self, source: str, **fields) -> None:
        state = self._get_state(source) or {
            "watermark": None, "last_success_at": None, "status": None,
            "error": None, "consecutive_failures": 0,
        }
        state.update(fields)
        cur = self.db.cursor()
        _upsert(cur, "sync_state", {"source": source, **state}, pk=["source"])

    def cooldown_until(self) -> datetime | None:
        state = self._get_state("rate_limit")
        if state and state["watermark"]:
            return datetime.fromisoformat(state["watermark"])
        return None

    def last_success_at(self) -> datetime | None:
        state = self._get_state("global")
        return state["last_success_at"] if state else None

    def is_stale(self) -> bool:
        last = self.last_success_at()
        if last is None:
            return True
        return utcnow() - last > timedelta(hours=self.settings.staleness_hours)

    def status(self) -> dict:
        cur = self.db.cursor()
        last_run = cur.execute(
            "SELECT trigger, started_at, finished_at, status, error, stats "
            "FROM sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        counts = cur.execute(
            "SELECT (SELECT count(*) FROM activities), "
            "(SELECT max(start_time_local) FROM activities), "
            "(SELECT max(date) FROM daily_wellness)"
        ).fetchone()
        cooldown = self.cooldown_until()
        return {
            "running": self._lock.locked(),
            "phase": self._phase,
            "auth_required": self._auth_required_msg is not None,
            "auth_message": self._auth_required_msg,
            "reauth_command": REAUTH_COMMAND,
            "last_success_at": self.last_success_at(),
            "rate_limit_cooldown_until": cooldown if cooldown and cooldown > utcnow() else None,
            "last_run": dict(zip(
                ["trigger", "started_at", "finished_at", "status", "error", "stats"], last_run
            )) if last_run else None,
            "activity_count": counts[0],
            "newest_activity_at": counts[1],
            "newest_wellness_date": counts[2],
        }

    # ------------------------------------------------------------ trigger --

    def trigger(self, trigger: str, force: bool = False) -> dict:
        """Start a sync in a background thread. Returns immediately."""
        cooldown = self.cooldown_until()
        if not force and cooldown and cooldown > utcnow():
            return {"started": False, "reason": f"rate-limit cooldown until {cooldown.isoformat()}Z"}
        with self._trigger_mutex:
            if self._stop.is_set() or self._lock.locked():
                return {"started": False, "reason": "sync already running"}
            self._thread = threading.Thread(
                target=self.run, args=(trigger,), daemon=True, name=f"sync-{trigger}"
            )
            self._thread.start()
        return {"started": True}

    # ---------------------------------------------------------------- run --

    def run(self, trigger: str) -> None:
        if not self._lock.acquire(blocking=False):
            return
        started = utcnow()
        stats: dict = {}
        status, error = "ok", None
        try:
            with self.db.write_lock:
                self._phase = "activities"
                self._check_stop()
                stats["activities"] = self._sync_activities()
                self._phase = "details"
                self._check_stop()
                stats["details"] = self._sync_details()
                self._phase = "wellness"
                self._check_stop()
                stats["wellness"] = self._sync_wellness()
                self._phase = "biometrics"
                self._check_stop()
                stats["biometrics"] = self._sync_biometrics()
            self._auth_required_msg = None
            self._set_state("global", last_success_at=utcnow(), status="ok", error=None,
                            consecutive_failures=0)
            self._set_state("rate_limit", watermark=None, consecutive_failures=0, status=None, error=None)
        except AuthRequired as exc:
            status, error = "auth_required", str(exc)
            self._auth_required_msg = str(exc)
            log.warning("sync aborted, re-auth needed: %s", exc)
        except RateLimited as exc:
            status, error = "rate_limited", str(exc)
            state = self._get_state("rate_limit") or {"consecutive_failures": 0}
            n = (state.get("consecutive_failures") or 0) + 1
            minutes = min(self.settings.rate_limit_cooldown_min * 2 ** (n - 1), 24 * 60)
            until = utcnow() + timedelta(minutes=minutes)
            self._set_state("rate_limit", watermark=until.isoformat(), consecutive_failures=n,
                            status="rate_limited", error=str(exc))
            log.warning("sync rate-limited (429 #%d); cooling down %d min", n, minutes)
        except GarminUnavailable as exc:
            status, error = "error", str(exc)
            state = self._get_state("global") or {"consecutive_failures": 0}
            self._set_state("global", status="error", error=str(exc),
                            consecutive_failures=(state.get("consecutive_failures") or 0) + 1)
            log.warning("sync failed, will retry next interval: %s", exc)
        except Exception as exc:  # noqa: BLE001 — a bug must not kill the scheduler thread
            status, error = "error", f"{type(exc).__name__}: {exc}"
            log.exception("unexpected sync failure")
        finally:
            self._phase = None
            try:
                cur = self.db.cursor()
                cur.execute(
                    "INSERT INTO sync_runs (trigger, started_at, finished_at, status, error, stats) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [trigger, started, utcnow(), status, error, json.dumps(stats)],
                )
            except Exception:  # noqa: BLE001 — never leak the sync lock
                log.exception("failed to record sync run")
            finally:
                self._lock.release()
            log.info("sync (%s) finished: %s %s", trigger, status, stats)

    # ------------------------------------------------------------- phases --

    def _sync_activities(self) -> dict:
        cur = self.db.cursor()
        newest = cur.execute("SELECT max(start_time_local) FROM activities").fetchone()[0]
        if newest:
            # overlap window: catch late uploads and edits to recent activities
            start = (newest - timedelta(days=3)).date().isoformat()
        else:
            start = (date.today() - timedelta(days=self.settings.activity_backfill_days)).isoformat()
        entries = self.client.call("get_activities_by_date", start, date.today().isoformat()) or []
        for entry in entries:
            _upsert(cur, "activities", normalize.activity_row(entry), pk=["activity_id"])
            started_local = normalize._parse_dt(entry.get("startTimeLocal"))
            _store_raw(cur, "activity_summary", entry["activityId"],
                       started_local.date() if started_local else None, entry)
        self._set_state("activities", watermark=start, last_success_at=utcnow(),
                        status="ok", error=None, consecutive_failures=0)
        return {"fetched": len(entries), "since": start}

    def _sync_details(self) -> dict:
        cur = self.db.cursor()
        pending = cur.execute(
            "SELECT activity_id, sport, type_key, start_time_local FROM activities "
            "WHERE NOT details_synced AND sport IN ('run', 'ride', 'swim') "
            "ORDER BY start_time_utc DESC LIMIT ?",
            [self.settings.detail_batch],
        ).fetchall()
        done = failed = 0
        for activity_id, sport, type_key, start_local in pending:
            self._check_stop()
            ref_date = start_local.date() if start_local else None
            try:
                self._ingest_details(cur, activity_id, sport, type_key, ref_date)
                done += 1
            except (AuthRequired, RateLimited):
                raise
            except GarminUnavailable as exc:
                # transient outage: leave details_synced FALSE so the next
                # sync retries this activity; keep going with the rest
                failed += 1
                log.warning("detail sync failed for %s (will retry next sync): %s", activity_id, exc)
                cur.execute(
                    "UPDATE activities SET detail_error = ? WHERE activity_id = ?",
                    [f"transient: {exc}", activity_id],
                )
            except Exception as exc:  # noqa: BLE001 — a poison-pill payload must not block the rest
                failed += 1
                log.warning("detail ingest failed permanently for %s: %s", activity_id, exc)
                cur.execute(
                    "UPDATE activities SET details_synced = TRUE, detail_error = ? WHERE activity_id = ?",
                    [f"{type(exc).__name__}: {exc}", activity_id],
                )
        return {"synced": done, "failed": failed, "remaining_backlog": max(0, len(pending) - done - failed)}

    def _ingest_details(self, cur, activity_id: int, sport: str, type_key: str, ref_date=None) -> None:
        # all network I/O first, then one atomic write transaction
        details = self.client.call("get_activity_details", activity_id)
        splits = self.client.call("get_activity_splits", activity_id)
        activity = self.client.call("get_activity", activity_id)  # summaryDTO + splitSummaries

        samples = normalize.sample_rows(activity_id, details or {})
        laps = normalize.lap_rows(activity_id, splits or {})
        decoupling = aerobic_decoupling_pct(samples) if sport == "run" else None
        curve = power_curve(samples)

        cur.execute("BEGIN TRANSACTION")
        try:
            _store_raw(cur, "activity_details", activity_id, ref_date, details)
            _store_raw(cur, "activity_splits", activity_id, ref_date, splits)
            _store_raw(cur, "activity", activity_id, ref_date, activity)
            cur.execute("DELETE FROM activity_samples WHERE activity_id = ?", [activity_id])
            for row in samples:
                _upsert(cur, "activity_samples", row, pk=["activity_id", "elapsed_s"])

            cur.execute("DELETE FROM activity_laps WHERE activity_id = ?", [activity_id])
            for row in laps:
                _upsert(cur, "activity_laps", row, pk=["activity_id", "lap_index"])

            if type_key == "lap_swimming":
                # intervals + per-length rows come from the splits payload we already have
                intervals, lengths = normalize.swim_interval_rows(activity_id, splits or {})
                cur.execute("DELETE FROM swim_intervals WHERE activity_id = ?", [activity_id])
                cur.execute("DELETE FROM swim_lengths WHERE activity_id = ?", [activity_id])
                for row in intervals:
                    _upsert(cur, "swim_intervals", row, pk=["activity_id", "interval_index"])
                for row in lengths:
                    _upsert(cur, "swim_lengths", row, pk=["activity_id", "length_index"])

            cur.execute("DELETE FROM power_curve WHERE activity_id = ?", [activity_id])
            for dur, watts in curve:
                _upsert(cur, "power_curve",
                        {"activity_id": activity_id, "duration_s": dur, "max_avg_power_w": watts},
                        pk=["activity_id", "duration_s"])

            cur.execute(
                "UPDATE activities SET details_synced = TRUE, detail_error = NULL, "
                "aerobic_decoupling_pct = ? WHERE activity_id = ?",
                [decoupling, activity_id],
            )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise

    def _wellness_start(self) -> date:
        """First day to backfill wellness from: an explicit config date, else a
        rolling window (keeps a new account's first sync bounded and gentle)."""
        if self.settings.wellness_start:
            return date.fromisoformat(self.settings.wellness_start)
        return date.today() - timedelta(days=self.settings.wellness_backfill_days)

    def _sync_wellness(self) -> dict:
        state = self._get_state("wellness")
        start = date.fromisoformat(state["watermark"]) if state and state["watermark"] \
            else self._wellness_start()
        today = date.today()
        days = 0
        d = start
        while d <= today:
            self._check_stop()
            ds = d.isoformat()
            try:
                # a 404 ("no data that day") comes back as None; a transport
                # failure raises and must NOT be recorded as an empty day
                daily = {
                    "user_summary": self.client.call("get_user_summary", ds),
                    "hrv": self.client.call("get_hrv_data", ds),
                    "sleep": self.client.call("get_sleep_data", ds),
                    "stress": self.client.call("get_stress_data", ds),
                    "training_status": self.client.call("get_training_status", ds),
                    "training_readiness": self.client.call("get_training_readiness", ds),
                    "max_metrics": self.client.call("get_max_metrics", ds),
                    "body_battery_events": self.client.call("get_body_battery_events", ds),
                }
            except GarminUnavailable as exc:
                # keep the watermark at the last fully-synced day so this day
                # and everything after it are refetched next run
                self._set_state("wellness",
                                watermark=max(start, d - timedelta(days=1)).isoformat(),
                                status="error", error=f"{ds}: {exc}")
                raise

            cur = self.db.cursor()
            _upsert(cur, "daily_wellness",
                    normalize.wellness_row(ds, daily["user_summary"], daily["hrv"], daily["sleep"]),
                    pk=["date"])
            ts_row = normalize.training_status_row(ds, daily["training_status"], daily["max_metrics"])
            if ts_row:
                _upsert(cur, "training_status", ts_row, pk=["date"])
            r_row = normalize.readiness_row(ds, daily["training_readiness"])
            if r_row:
                _upsert(cur, "training_readiness", r_row, pk=["date"])
            for source, payload in daily.items():
                _store_raw(cur, source, ds, d, payload)
            days += 1
            d += timedelta(days=1)
        # yesterday is the last date we consider final; today gets refetched next run
        self._set_state("wellness", watermark=max(start, today - timedelta(days=1)).isoformat(),
                        last_success_at=utcnow(), status="ok", error=None, consecutive_failures=0)
        return {"days": days, "from": start.isoformat()}

    def _sync_biometrics(self) -> dict:
        cycling_ftp = self._try("get_cycling_ftp")
        lactate = self._try("get_lactate_threshold")
        races = self._try("get_race_predictions")
        zones = self._try("connectapi", "/biometric-service/heartRateZones")
        profile = self._try("get_user_profile")

        cur = self.db.cursor()
        rows = normalize.biometric_rows(cycling_ftp, lactate, races, profile)
        for row in rows:
            _upsert(cur, "biometrics", row, pk=["metric", "calendar_date"])
        for row in normalize.hr_zone_rows(zones):
            _upsert(cur, "hr_zone_config", {**row, "updated_at": utcnow()}, pk=["sport"])
        # archive the current-state singletons verbatim (key='latest', no ref_date)
        for source, payload in [
            ("cycling_ftp", cycling_ftp), ("lactate_threshold", lactate),
            ("race_predictions", races), ("hr_zones", zones), ("user_profile", profile),
        ]:
            _store_raw(cur, source, "latest", None, payload)
        return {"snapshots": len(rows)}

    def _try(self, method: str, *args):
        """Fetch one endpoint; tolerate its absence, abort on auth/429."""
        try:
            return self.client.call(method, *args)
        except (AuthRequired, RateLimited):
            raise
        except GarminUnavailable as exc:
            log.info("no data from %s%s: %s", method, args, exc)
            return None
