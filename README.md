# QSM 影视墙

QSM 是一个基于 FastAPI + Vue 3 的影视收藏工具，提供：

- TMDB 元数据展示
- 夸克资源搜索
- 资源校验、转存、重命名
- Docker 部署

## 目录结构

```text
qsm/
├─ backend/             # FastAPI 后端
├─ frontend/            # Vue 3 前端
├─ storage/             # 运行期数据、日志、配置、备份
├─ ops/backup/          # 备份与恢复脚本
├─ Dockerfile
├─ docker-compose.yml
└─ .env.example
```

## 本地开发

### 后端

```bash
cd backend
pip install --prefer-binary --no-compile -r requirements-dev.lock.txt
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

## 环境变量

先复制模板：

```bash
cp .env.example .env
```

至少填写：

- `API_KEY`
- `TMDB_API_KEY`
- `QUARK_TRANSFER_COOKIE`

生产环境建议同时检查：

- `CORS_ORIGINS=["https://your-domain.com"]`
- `TRUST_PROXY_HEADERS=true`
- `TRUSTED_PROXY_IPS=["127.0.0.1","::1"]`

运行期配置默认保存在：

- `storage/config/settings.env`

## Docker 部署

### 方式 A：服务器拉代码后本地构建

```bash
mkdir -p /opt/qsm
cd /opt/qsm
git clone https://github.com/242282218/q-s-m.git .
cp .env.example .env
mkdir -p storage/db storage/logs storage/config storage/uploads storage/backups
# 编辑 .env
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f app
```

### 方式 B：直接使用 GHCR 镜像

每次推送到 `main` 都会自动发布多架构镜像到 GHCR：

- `ghcr.io/242282218/q-s-m:latest`
- `linux/amd64`
- `linux/arm64`

默认容器启动为单 worker，避免 SQLite 与内存缓存状态在多进程下不一致。For multi-worker deployment, set `CACHE_TYPE=redis` and configure `REDIS_URL` first.

CI 中的 `quality-gates.yml` 会执行 `Docker image build`，并通过 `health/live` 与 `health/ready` 检查镜像启动状态。

本地可执行 Docker 冒烟测试：

```bash
python ops/deploy/docker_smoke.py
```

示例 `docker-compose.yml`：

```yaml
services:
  app:
    image: ghcr.io/242282218/q-s-m:latest
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
```

启动：

```bash
mkdir -p storage/db storage/logs storage/config storage/uploads storage/backups
docker compose pull
docker compose up -d
```

## 健康检查

```bash
curl -f http://127.0.0.1:8000/api/v1/health/ready
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/live
```

## 更新

### 代码构建部署

```bash
cd /opt/qsm
git pull
docker compose up -d --build
```

### GHCR 镜像部署

```bash
cd /opt/qsm
docker compose pull
docker compose up -d
```

## 备份与恢复

备份：

```bash
python ops/backup/backup_sqlite.py
```

恢复：

```bash
python ops/backup/restore_sqlite.py --backup-file storage/backups/qsm-YYYYmmdd-HHMMSS.db
```

## 详细文档

详细部署说明见：

- [docs/deployment/docker-with-nginx.md](docs/deployment/docker-with-nginx.md)

当前默认部署配置见：

- [docker-compose.yml](docker-compose.yml)
- [Dockerfile](Dockerfile)
- [.github/workflows/docker-ghcr-main.yml](.github/workflows/docker-ghcr-main.yml)
