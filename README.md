# QSM Movie Wall

QSM is a full-stack media collection tool built with FastAPI and Vue 3. It integrates TMDB for metadata and Quark services for search, verification, transfer, and rename workflows.

## Project Structure

```text
qsm/
├─ backend/             # FastAPI application
├─ frontend/            # Vue 3 + Vite application
├─ storage/             # Runtime data, logs, config snapshots, backups
├─ ops/backup/          # Backup and restore scripts
├─ Dockerfile
├─ docker-compose.yml
└─ .env.example
```

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
pnpm install
pnpm dev
```

## Continuous QA Loop

Use the built-in continuous runner to execute default backend/frontend checks in a loop:

```bash
python ops/continuous/continuous_runner.py --max-workers 2 --interval 60
```

Default task config lives in `ops/continuous/tasks.default.json`.
It is pre-split into `backend-agent` and `frontend-agent` lanes:

- tasks in the same agent run sequentially (stable context, less interference)
- different agents can run in parallel (controlled by `--max-workers`)
- the default frontend lane uses read-only `lint:check` + `format:check`, so continuous checks fail on drift instead of auto-rewriting the worktree
- `agent.model` is fixed to `gpt-5.4` and invalid models fail fast
- `enabled=false` only skips execution; task schema + duplicate name checks still fail fast
- `task.cwd` must stay inside `repo_root`; absolute path / `..` escape is rejected
- `task.cwd` must resolve to an existing directory; missing/non-directory paths fail fast
- unhandled task errors and unexpected lane-level errors are downgraded to failed task results (`exit_code=70`); finished lane tasks are preserved, incomplete lane result sets only backfill missing tasks, and invalid lane indexes are treated as lane-level failures
- next iteration id resumes from `latest.json`; if `latest.json` is broken/stale, runner falls back to highest `iteration-*.json`
- runners that share the same `log_dir` reserve iteration ids through a lock-backed counter, so updated processes do not reuse the same iteration number concurrently

## Environment

1. Copy the template:
```bash
cp .env.example .env
```
2. Fill in at least:
   - `TMDB_API_KEY`
   - `QUARK_TRANSFER_COOKIE`
   - `API_KEY`
3. For multi-worker deployment, set `CACHE_TYPE=redis` and a reachable `REDIS_URL`
   so cache + rate limiting stay consistent across processes.
4. Optional: tune `RATE_LIMIT_REDIS_FAILURE_COOLDOWN_SECONDS` (default `30`) to
   control how long rate limiting stays on in-memory fallback after a Redis failure.
5. Behind Nginx/Ingress, set `TRUST_PROXY_HEADERS=true` and configure
   `TRUSTED_PROXY_IPS` to your proxy source addresses only, otherwise keep it disabled.
   `TRUSTED_PROXY_IPS` supports both JSON array (recommended) and comma-separated string.
   Example: `["127.0.0.1","::1"]` or `127.0.0.1,::1`.
   The limiter resolves `X-Forwarded-For` from right to left and skips trusted proxy hops.
   Non-IP or malformed header values are ignored and fallback to the connection source IP.
6. Keep `CORS_ORIGINS` production-safe by default (for example `["https://your-domain.com"]`).
   For local split frontend/backend development, temporarily set it to localhost origins and enable `DEBUG=true`.

Runtime settings updates are persisted to `storage/config/settings.env` by default. Existing local deployments that still use `backend/data/settings.env` remain compatible until migrated.

## Docker Deployment

### Option A: Build locally

```bash
cp .env.example .env
# Edit .env and fill in API_KEY, TMDB_API_KEY, QUARK_TRANSFER_COOKIE
docker compose up -d --build
```

### Option B: Pull from GitHub Container Registry

Every push to `main` automatically builds and publishes an image to `ghcr.io`.

```bash
# 1. Create project directory on your server
mkdir -p ~/qsm && cd ~/qsm

# 2. Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  app:
    image: ghcr.io/YOUR_GITHUB_USERNAME/qsm:latest
    environment:
      ENV: production
      QSM_STORAGE_ROOT: /app/storage
      QSM_DATA_DIR: /app/storage/db
      QSM_RUNTIME_ENV_FILE: /app/storage/config/settings.env
      LOG_DIR: /app/storage/logs
      API_KEY: your-api-key
      TMDB_API_KEY: your-tmdb-key
      QUARK_TRANSFER_COOKIE: your-quark-cookie
    ports:
      - "8000:8000"
    volumes:
      - ./storage/db:/app/storage/db
      - ./storage/logs:/app/storage/logs
      - ./storage/config:/app/storage/config
      - ./storage/uploads:/app/storage/uploads
      - ./storage/backups:/app/storage/backups
    restart: unless-stopped
EOF

# 3. Create storage directories
mkdir -p storage/{db,logs,config,uploads,backups}

# 4. Pull and start
docker compose pull
docker compose up -d
```

### First-time API Key setup

If `API_KEY` is set in the environment, the frontend needs to know it too.
Open the browser console on `http://your-server:8000` and run:

```javascript
localStorage.setItem('qsm_api_key', 'your-api-key')
```

Then refresh the page. Alternatively, go to **Settings**, enter the key in the
"API 访问 Key" field, and save — this persists it to `localStorage` automatically.

### Persistent data

All runtime data is stored under:
- `storage/db`
- `storage/logs`
- `storage/config`
- `storage/uploads`
- `storage/backups`

The API and SPA are served from the same container on `http://localhost:8000`.

## Backup

Create a database snapshot:
```bash
python ops/backup/backup_sqlite.py
```

Restore from a snapshot:
```bash
python ops/backup/restore_sqlite.py --backup-file storage/backups/qsm-YYYYmmdd-HHMMSS.db
```

The backup script also copies the runtime settings snapshot when `storage/config/settings.env` exists.
