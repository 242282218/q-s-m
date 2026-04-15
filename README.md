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
