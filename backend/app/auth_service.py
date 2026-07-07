"""In-app Garmin login — the web-driven replacement for the terminal auth.py.

A single-user, localhost flow: the browser posts the Garmin email/password
(and MFA code if 2FA is on) to the local backend, which performs the login
server-side, writes the OAuth token store, and never persists the password.

The garminconnect 0.3.x MFA flow requires that `resume_login` run on the SAME
Garmin instance in the SAME process as `login()`, so the pending instance is
held here between the /auth/login and /auth/mfa calls.
"""

import contextlib
import json
import logging
import threading
from pathlib import Path

from garminconnect import Garmin

log = logging.getLogger(__name__)


class LoginNotInProgress(Exception):
    """MFA code submitted with no pending login (e.g. after a restart)."""


class AuthService:
    def __init__(self, db, client, engine, token_dir: Path):
        self.db = db
        self.client = client        # token-only GarminClient — reset after new tokens land
        self.engine = engine        # SyncEngine — kick a sync once authenticated
        self.token_dir = token_dir
        self._lock = threading.Lock()
        self._pending: Garmin | None = None

    @property
    def token_file(self) -> Path:
        return self.token_dir / "garmin_tokens.json"

    # ---------------------------------------------------------- display name --

    def _set_name(self, name: str | None) -> None:
        cur = self.db.cursor()
        if name:
            cur.execute(
                "INSERT INTO app_meta (key, value) VALUES ('display_name', ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                [name],
            )
        else:
            cur.execute("DELETE FROM app_meta WHERE key = 'display_name'")

    def display_name(self) -> str | None:
        cur = self.db.cursor()
        row = cur.execute("SELECT value FROM app_meta WHERE key = 'display_name'").fetchone()
        if row and row[0]:
            return row[0]
        # older/migrated DBs (authed before the in-app login) have no stored name:
        # derive it once from an already-synced activity payload's ownerFullName.
        name = self._name_from_raw()
        if name:
            self._set_name(name)
        return name

    def _name_from_raw(self) -> str | None:
        cur = self.db.cursor()
        row = cur.execute(
            "SELECT payload FROM raw_payloads WHERE source = 'activity_summary' "
            "AND payload IS NOT NULL LIMIT 1"
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return (json.loads(row[0]) or {}).get("ownerFullName")
        except (ValueError, TypeError):
            return None

    # ---------------------------------------------------------------- status --

    def status(self) -> dict:
        with self._lock:
            pending = self._pending is not None
        # authenticated only if tokens exist AND a sync hasn't found them revoked
        authenticated = self.token_file.exists() and not self.engine.auth_required
        return {
            "authenticated": authenticated,
            "pending_mfa": pending,
            "display_name": self.display_name(),
        }

    # ----------------------------------------------------------------- login --

    def begin_login(self, email: str, password: str) -> dict:
        """Blocking (Garmin login can take a minute). Returns status 'ok' or
        'needs_mfa'. Raises the raw GarminConnect* exceptions for the caller
        to map to HTTP codes."""
        # drop any stale pending login first
        with self._lock:
            self._pending = None
        api = Garmin(email=email, password=password, return_on_mfa=True)
        result, _ = api.login()
        if result == "needs_mfa":
            with self._lock:
                self._pending = api
            log.info("garmin login: MFA required")
            return {"status": "needs_mfa"}
        self._finalize(api)
        return {"status": "ok", "display_name": self.display_name()}

    def submit_mfa(self, code: str) -> dict:
        with self._lock:
            api = self._pending
        if api is None:
            raise LoginNotInProgress()
        # raises on a bad code; keep _pending so the user can retry the code
        # without re-entering their password (begin_login clears stale pending).
        api.resume_login(None, code)
        # _finalize persists the tokens; only drop _pending once that succeeds,
        # so a token-write failure leaves the flow resumable rather than stranded.
        self._finalize(api)
        with self._lock:
            self._pending = None
        return {"status": "ok", "display_name": self.display_name()}

    def _finalize(self, api: Garmin) -> None:
        # persist tokens FIRST (required on BOTH the direct and MFA paths — login()
        # only auto-dumps when handed a tokenstore, resume_login never does). Once
        # the tokens are on disk the session is authenticated, so everything after
        # is best-effort and must not fail the request.
        self.token_dir.mkdir(parents=True, exist_ok=True)
        api.client.dump(str(self.token_dir))
        self.engine.clear_auth_required()  # valid tokens now exist → flip the gate now
        with contextlib.suppress(Exception):
            self._set_name(api.get_full_name())
        with contextlib.suppress(Exception):
            self.client.reset()            # token-only client re-resumes from the new tokens
        with contextlib.suppress(Exception):
            self.engine.trigger("login", force=True)  # first/refresh sync, bypassing cooldown
        log.info("garmin login complete for %s", self.display_name() or "(name unavailable)")

    def logout(self) -> dict:
        with self._lock:
            self._pending = None
        with contextlib.suppress(FileNotFoundError):
            self.token_file.unlink()
        self._set_name(None)
        self.client.reset()
        self.engine.clear_auth_required()
        log.info("garmin logout: tokens cleared")
        return {"status": "ok"}
