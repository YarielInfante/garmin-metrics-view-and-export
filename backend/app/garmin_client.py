"""Thin wrapper around garminconnect: token-only login, throttling, and
translation of library exceptions into app-level ones the sync engine and
API understand.

Read-only: nothing here ever writes to Garmin.
"""

import logging
import random
import re
import threading
import time
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

log = logging.getLogger(__name__)

REAUTH_COMMAND = ".venv/bin/python auth.py"


class AuthRequired(Exception):
    """Tokens missing/expired/revoked — user must re-run auth.py."""


class RateLimited(Exception):
    """Garmin returned 429. Hard stop; cool down before any further calls."""


class GarminUnavailable(Exception):
    """Network problem or Garmin-side error; retry at the next sync."""


class GarminClient:
    def __init__(self, token_dir: Path, throttle_seconds: float = 1.0):
        self._token_dir = token_dir
        self._throttle = throttle_seconds
        self._api: Garmin | None = None
        self._lock = threading.Lock()
        self._last_call = 0.0

    @property
    def token_file(self) -> Path:
        return self._token_dir / "garmin_tokens.json"

    def _login(self) -> Garmin:
        if not self.token_file.exists():
            raise AuthRequired(f"No tokens at {self._token_dir}. Run: {REAUTH_COMMAND}")
        api = Garmin()  # no credentials on purpose: token-only, never a credential login
        try:
            api.login(str(self._token_dir))
        except GarminConnectAuthenticationError as exc:
            raise AuthRequired(f"Saved tokens rejected: {exc}. Run: {REAUTH_COMMAND}") from exc
        except GarminConnectTooManyRequestsError as exc:
            raise RateLimited(str(exc)) from exc
        except GarminConnectConnectionError as exc:
            raise GarminUnavailable(f"Login failed: {exc}") from exc
        return api

    def api(self) -> Garmin:
        with self._lock:
            if self._api is None:
                self._api = self._login()
            return self._api

    def reset(self) -> None:
        """Drop the session so the next call re-resumes from the token store."""
        with self._lock:
            self._api = None

    def call(self, method: str, *args, **kwargs):
        """Throttled call of a Garmin method by name; maps errors.

        The library already retries transient 5xx/network errors internally
        (3 attempts, jittered backoff) but never retries 401/429 — those are
        surfaced as AuthRequired / RateLimited and abort the current sync.
        A 404 means "no data for this date/activity" and returns None so the
        sync engine can tell missing data apart from a real outage.
        """
        wait = self._throttle - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.25))
        self._last_call = time.monotonic()
        api = self.api()
        try:
            return getattr(api, method)(*args, **kwargs)
        except GarminConnectAuthenticationError as exc:
            self.reset()
            raise AuthRequired(f"Authentication failed mid-sync: {exc}. Run: {REAUTH_COMMAND}") from exc
        except GarminConnectTooManyRequestsError as exc:
            raise RateLimited(str(exc)) from exc
        except GarminConnectConnectionError as exc:
            match = re.search(r"(?:API Error|client error \(|HTTP )\s*(\d{3})", str(exc))
            if match and match.group(1) == "404":
                return None
            raise GarminUnavailable(str(exc)) from exc
