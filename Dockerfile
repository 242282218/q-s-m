# Stage 1: Frontend Builder
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

ARG VITE_API_BASE=/api/v1
ARG VITE_API_KEY=
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_API_KEY=$VITE_API_KEY

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod=false

COPY frontend/src ./src
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json ./
RUN pnpm build && rm -rf node_modules

# Stage 2: Python Builder
FROM python:3.11-slim AS python-builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/requirements.txt backend/requirements.lock.txt ./
RUN pip install --upgrade pip && \
    pip install --prefer-binary --no-compile -r requirements.lock.txt && \
    python -c "import gunicorn, uvicorn" && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type f -name "*.pyc" -delete 2>/dev/null || true

# Stage 3: Final Runtime Image
FROM python:3.11-slim

WORKDIR /app

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    QSM_STORAGE_ROOT=/app/storage \
    QSM_DATA_DIR=/app/storage/db \
    QSM_RUNTIME_ENV_FILE=/app/storage/config/settings.env \
    LOG_DIR=/app/storage/logs

RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && adduser --disabled-password --gecos '' appuser \
    && install -d -o appuser -g appuser \
        /app/storage/db \
        /app/storage/logs \
        /app/storage/config \
        /app/storage/uploads \
        /app/storage/backups

COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN /opt/venv/bin/python -c "import gunicorn, uvicorn"

COPY --chown=appuser:appuser backend/app ./app
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --from=frontend-builder --chown=appuser:appuser /build/frontend/dist ./frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready')" || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/opt/venv/bin/python", "-m", "gunicorn", "app.main:app", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
