#!/usr/bin/env python3
"""One-time interactive Garmin Connect login.

Usage:
    .venv/bin/python auth.py

Prompts for your Garmin email/password (and MFA code if 2FA is enabled),
then saves OAuth tokens to $GARMIN_TOKEN_DIR (default: ~/.garminconnect).

After this succeeds everything else is non-interactive: the app resumes
from the saved tokens and the access token auto-refreshes on use, with
refreshed tokens persisted back to the same directory by the library.

Re-run this script only when the app reports an authentication failure
(tokens revoked or expired — typically after ~6 months or a password
change).

Note on garth: garminconnect 0.3.x (pinned in requirements.txt) replaced
garth with its own token store — one file, <token_dir>/garmin_tokens.json,
holding di_token / di_refresh_token / di_client_id. The login/save/resume
shape is the same as garth's; only the calls differ. This is also the
format the Taxuspt/garmin_mcp server expects, so it can share this
token directory.
"""

import getpass
import os
import sys
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_DIR = Path(os.environ.get("GARMIN_TOKEN_DIR", "~/.garminconnect")).expanduser()


def main() -> int:
    print(f"Garmin Connect one-time login — tokens will be saved to {TOKEN_DIR}")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        return 1

    # return_on_mfa lets us prompt for the code ourselves instead of the
    # library owning stdin. Login can take a while: the library rotates
    # through several strategies with deliberate anti-bot delays.
    api = Garmin(email=email, password=password, return_on_mfa=True)
    print("Logging in (this can take up to a minute or two)...")
    try:
        status, _ = api.login()
        if status == "needs_mfa":
            code = input("MFA code: ").strip()
            api.resume_login(None, code)
    except GarminConnectAuthenticationError as exc:
        print(f"\nAuthentication failed: {exc}", file=sys.stderr)
        print("Check your email, password, and MFA code, then re-run.", file=sys.stderr)
        return 1
    except GarminConnectTooManyRequestsError:
        print("\nGarmin is rate-limiting login attempts (HTTP 429).", file=sys.stderr)
        print("Wait at least an hour before re-running — retrying now makes it worse.", file=sys.stderr)
        return 1
    except GarminConnectConnectionError as exc:
        print(f"\nCould not complete login: {exc}", file=sys.stderr)
        print(
            "If this mentions CAPTCHA or Cloudflare, log in once at connect.garmin.com "
            "in a browser, wait a while, then re-run.",
            file=sys.stderr,
        )
        return 1

    # login() only auto-persists when given a tokenstore, and resume_login
    # never does — so dump explicitly to cover both the MFA and non-MFA paths.
    api.client.dump(str(TOKEN_DIR))

    # Prove the saved tokens work on their own: fresh client, token-only login.
    try:
        check = Garmin()
        check.login(str(TOKEN_DIR))
        name = check.get_full_name() or "(name unavailable)"
    except Exception as exc:  # noqa: BLE001 — any failure here means the store is bad
        print(f"\nTokens were saved but could not be used to log back in: {exc}", file=sys.stderr)
        return 1

    print(f"\nLogged in as {name}.")
    print(f"Tokens saved to {TOKEN_DIR / 'garmin_tokens.json'}.")
    print("You will not need this script again until Garmin invalidates the tokens (~6 months).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
