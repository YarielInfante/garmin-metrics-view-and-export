# Garmin Training Analytics

A **local-only, self-hosted** analytics dashboard for your own Garmin training
data — running, cycling, swimming, and daily wellness — plus a one-click raw
export you can paste into an AI chat for coaching. You run it on your own
machine; your data never leaves it.

Python/FastAPI + DuckDB backend, React/Vite/Tailwind/Recharts frontend, shipped
as a single Docker container that keeps itself synced in the background.

## TL;DR — get it running

[Install Docker](https://docs.docker.com/get-docker/), then:

```bash
git clone https://github.com/YarielInfante/garmin-metrics-view-and-export.git
cd garmin-metrics-view-and-export
docker compose up -d --build
```

Open **http://127.0.0.1:8722**, sign in with your Garmin account (email + password,
plus the MFA code if you use 2-factor), and you're done — it syncs in the
background and restarts on reboot. Requirements and details are below.

> **Unofficial & use at your own risk.** Garmin has no official public API; this
> reads your data through the unofficial [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
> library. It is **not affiliated with or endorsed by Garmin**. Automated logins
> can occasionally trigger rate-limits or CAPTCHAs on your account. Nothing here
> is medical advice. You are responsible for your own use and for complying with
> Garmin's Terms of Service.

---

## Requirements

**To run it (recommended, Docker path):**

- **[Docker](https://docs.docker.com/get-docker/)** with Compose v2 — Docker
  Desktop on macOS or Windows, Docker Engine + `docker compose` on Linux. That's
  the only thing you install; Python, Node, and all dependencies are inside the
  image.
- A **Garmin Connect account** with your own login (email + password, plus your
  MFA method if 2-factor is enabled) and a Garmin device that syncs data to it.
- **Outbound internet** so it can reach Garmin during sync. Nothing inbound is
  needed — the app is reachable only from your own machine (`127.0.0.1`).
- A **modern web browser** to open the dashboard.
- Roughly **1–2 GB free disk** for the image, plus a little for your data (a few
  MB to tens of MB depending on history).
- Works on **macOS, Linux, and Windows** (Windows via Docker Desktop / WSL2). Both
  Intel/AMD (amd64) and Apple Silicon / ARM (arm64) are supported.

**To run from source instead (developers):** Python **3.13** and Node **≥ 18**
(the repo pins Node 22 for the frontend). See *Running from source* below.

---

## Quick start (Docker)

You need [Docker](https://docs.docker.com/get-docker/) (Desktop on macOS/Windows,
Engine on Linux). Then:

```bash
git clone https://github.com/YarielInfante/garmin-metrics-view-and-export.git
cd garmin-metrics-view-and-export
docker compose up -d --build
```

Open **http://127.0.0.1:8722**, and on the setup screen sign in with your Garmin
email and password (and the MFA code if you have 2-factor enabled). That's it —
the dashboard fills in as the first sync runs, and the app keeps itself fresh and
restarts on reboot.

- **Localhost only.** The port is published on `127.0.0.1` — it is *not* reachable
  from your network.
- **Your data stays on your machine** in Docker named volumes (`garmin-data` for
  the database, `garmin-tokens` for the OAuth tokens). Both persist across
  restarts; neither is ever sent anywhere but Garmin. (A backup command is in the
  compose file.)
- **Timezone:** set `TZ` in [docker-compose.yml](docker-compose.yml) to your local
  zone so daily boundaries line up with your day.

Everyday commands:

```bash
docker compose logs -f     # watch sync activity
docker compose down        # stop (data + tokens stay on disk)
docker compose pull        # (if using a prebuilt image) get the latest, then `up -d`
```

> Exactly **one** process may own the DuckDB file. Don't run the container and a
> from-source server against the same `./data` at the same time.

---

## Signing in

The setup screen performs the Garmin login **once** to obtain OAuth tokens, which
are then stored locally. **Your password is never stored** — only the tokens are,
and they auto-refresh (lasting ~6 months). If they ever expire or get revoked, the
app drops you back to the setup screen to sign in again.

Everything is done from your own machine talking directly to Garmin; the app has
no server of its own and sends your credentials nowhere else.

---

## What's in the dashboard

- **Load & 80/20** — training load (acute vs chronic, ACWR band, Garmin readiness),
  weekly time-in-HR-zone, % easy vs your 80/20 target, weekly multisport hours.
- **Running** — cadence trend with a target band, running dynamics (vertical
  oscillation, ground contact time, vertical ratio), aerobic decoupling per run,
  weekly volume and pace-vs-HR.
- **Cycling** — FTP (Garmin as source of truth) and W/kg, speed/distance
  progression, effort per ride, and a power-duration curve that lights up if a
  ride carries power-meter data.
- **Swimming** — pace/100 m, SWOLF, stroke trends, and a within-session durability
  view (per-length SWOLF/strokes/pace).
- **Recovery** — HRV vs baseline, resting HR, sleep, body battery, stress.
- **Export** — pick a date range and get **every Garmin payload in that window as
  raw JSON** to copy or download and paste into an AI chat for analysis (see below).

Metrics your watch/sensors don't record show a "no data" state instead of breaking,
so a runner-only account (or a watch without running-dynamics/power) works fine.

## Raw archive & Export (feed your data to an AI yourself)

Every sync also stores each Garmin response **verbatim** in the local database —
nothing dropped, deduplicated by upsert. The **Export** tab turns any date range
into one raw JSON bundle (current thresholds up front, then activities, then
per-day wellness). Copy it into a chat, or download it. This is deliberately **not**
an AI-provider integration — the app never calls one and needs no API key; your
data leaves your machine only when *you* copy or download the bundle.

---

## Configuration

Training targets are editable in-app via the **Settings** button (cadence band,
FTP fallback, pool length, the 80/20 easy-zone definition and target, Z2 cap, and
the ACWR band). HR zones come from Garmin.

Everything else is env-driven (prefix `GARMIN_APP_`; set under `environment:` in
`docker-compose.yml`). Common ones:

| Variable | Default | Meaning |
|---|---|---|
| `TZ` | `Etc/UTC` | your local timezone |
| `GARMIN_APP_SYNC_INTERVAL_HOURS` | `3` | background sync cadence |
| `GARMIN_APP_STALENESS_HOURS` | `6` | startup staleness threshold |
| `GARMIN_APP_WELLNESS_BACKFILL_DAYS` | `180` | how far back to backfill daily wellness |
| `GARMIN_APP_THROTTLE_SECONDS` | `1.0` | min gap between Garmin calls (be gentle) |
| `GARMIN_TOKEN_DIR` | `/tokens` (container) | OAuth token directory |
| `GARMIN_APP_DB_PATH` | `data/garmin.duckdb` | DuckDB file |

## Data & privacy

- The DuckDB database and your OAuth tokens live in Docker named volumes
  (`garmin-data`, `garmin-tokens`) — on your machine, never leaving it.
- The server binds `127.0.0.1` only. The **only** outbound calls are the Garmin
  sync; the Export endpoint reads the local database only.

## How freshness works

Incremental only — the app tracks a per-source watermark and never refetches
everything. A background scheduler syncs on an interval, a startup sync runs if the
data is stale, and there's a manual "Sync now" button. It's gentle on Garmin
(throttled, exponential backoff, a hard stop with cooldown on HTTP 429).

---

## Running from source (development)

Requires Python 3.13 and Node ≥ 18 (a `.nvmrc` pins Node 22 for the frontend).

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8722
```

Open http://127.0.0.1:8722 and sign in on the setup screen. For frontend hot
reload during development: `cd frontend && npm run dev` (proxies `/api` to the
backend on 8722).

To keep it running without Docker, see [deploy/garmin-app.plist](deploy/garmin-app.plist)
(macOS launchd) or [deploy/garmin-app.service](deploy/garmin-app.service) (Linux
systemd).

## Publishing your own image

Tagging a release (`git tag v0.1.0 && git push --tags`) builds a multi-arch image
and pushes it to the GitHub Container Registry via
[.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml).
Point `image:` in `docker-compose.yml` at `ghcr.io/<owner>/<repo>:latest` to run
it without building locally.

## License

[MIT](LICENSE).
