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

Runtime settings updates are persisted to `storage/config/settings.env` by default. Existing local deployments that still use `backend/data/settings.env` remain compatible until migrated.

## Docker Deployment

```bash
docker compose up -d --build
```

Persistent data is stored under:
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
