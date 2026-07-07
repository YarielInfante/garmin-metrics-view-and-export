"""App entry point.

    .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8722

Serves the API and (when built) the frontend from frontend/dist. Pages are
always served straight from local DuckDB; syncs run on a background
scheduler (interval + startup staleness check) and never block a request.
"""

import ipaddress
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .auth_service import AuthService
from .config import REPO_ROOT, load_settings
from .db import Database
from .garmin_client import GarminClient
from .sync import SyncEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("garmin_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: app.state.engine.trigger("scheduled"),
        "interval",
        hours=settings.sync_interval_hours,
        jitter=300,
        id="sync",
    )
    scheduler.start()
    # only auto-sync once the user has authenticated (tokens exist); before that
    # the Setup screen drives the first login.
    if app.state.client.token_file.exists() and app.state.engine.is_stale():
        log.info("local data older than %.1fh (or empty) — starting sync", settings.staleness_hours)
        app.state.engine.trigger("startup")
    yield
    scheduler.shutdown(wait=False)
    app.state.engine.shutdown()  # drain any in-flight sync before closing the DB
    app.state.db.close()


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="Garmin Training Analytics", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.db_path)
    app.state.client = GarminClient(settings.token_dir, settings.throttle_seconds)
    app.state.engine = SyncEngine(app.state.db, app.state.client, settings)
    app.state.auth = AuthService(app.state.db, app.state.client, app.state.engine, settings.token_dir)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # vite dev server
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Localhost-only guard: when configured for loopback (the default), reject any
    # non-loopback client at the app layer, so the credential-accepting /api/auth
    # endpoints stay off the network even if uvicorn is bound to 0.0.0.0 by mistake.
    # Set GARMIN_APP_HOST to a non-loopback value to opt out (Docker does this; the
    # container is instead protected by publishing the port on 127.0.0.1 only, and
    # anyone deliberately exposing it takes responsibility for fronting it safely).
    if settings.host in ("127.0.0.1", "localhost", "::1"):
        @app.middleware("http")
        async def _loopback_only(request: Request, call_next):
            peer = request.client.host if request.client else ""
            try:
                is_local = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                is_local = False
            if not is_local:
                return PlainTextResponse("This app is localhost-only.", status_code=403)
            return await call_next(request)

    app.include_router(router)

    dist = REPO_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
