# syntax=docker/dockerfile:1

# ---- stage 1: build the React frontend (Node only at build time) ----
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /fe/dist (self-contained; fonts bundled, no CDN)

# ---- stage 2: python runtime ----
FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # served on all interfaces INSIDE the container; the host only publishes it
    # on 127.0.0.1 (see compose), so it stays off the network.
    GARMIN_APP_HOST=0.0.0.0 \
    GARMIN_APP_PORT=8722 \
    GARMIN_APP_DB_PATH=/app/data/garmin.duckdb \
    GARMIN_TOKEN_DIR=/tokens

# tzdata lets TZ=<zone> drive the scheduler + daily wellness date boundaries
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./backend/
COPY auth.py ./
COPY --from=frontend /fe/dist ./frontend/dist

# run unprivileged; /app/data + /tokens are mounted at runtime
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data /tokens \
    && chown -R app:app /app /tokens
USER app

EXPOSE 8722
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8722/api/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8722"]
