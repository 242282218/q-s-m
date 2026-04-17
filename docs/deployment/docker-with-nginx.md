# Docker + Nginx 部署说明

本项目推荐以单容器应用方式部署，由宿主机 Nginx 反向代理到 `127.0.0.1:8000`。

## 1. 服务器准备

```bash
mkdir -p /opt/qsm
cd /opt/qsm
git clone <your-repo-url> .
cp .env.example .env
mkdir -p storage/db storage/logs storage/config storage/uploads storage/backups
```

编辑 `.env`，至少填写：

```env
ENV=production
APP_PORT=8000
API_KEY=replace-with-a-long-random-string
TMDB_API_KEY=replace-with-your-tmdb-api-key
QUARK_TRANSFER_COOKIE=replace-with-your-quark-cookie
CORS_ORIGINS=["https://your-domain.com"]
# Optional: trust proxy headers for rate limiting
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IPS=["127.0.0.1","::1"]
```

如果 Nginx 与应用不在同一网络命名空间，请把 `TRUSTED_PROXY_IPS` 改为实际代理来源 IP；不要配置为 `*` 或整个网段，避免头部伪造绕过限流。
`TRUSTED_PROXY_IPS` 推荐使用 JSON 数组，也兼容逗号分隔字符串（如 `127.0.0.1,::1`）。
限流器会从 `X-Forwarded-For` 右侧开始剥离可信代理节点，取第一个非代理 IP 作为限流键，避免左侧伪造 IP 影响限流。
`X-Forwarded-For` / `X-Real-IP` 里非标准 IP（含非法字符串）会被忽略并回退到连接源 IP。

## 2. 启动容器

```bash
cd /opt/qsm
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## 3. Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
        proxy_buffering off;
    }
}
```

如果你已经配置 HTTPS，把同样的 `location /` 放进 `443` 的 server 块即可。

## 4. 更新

```bash
cd /opt/qsm
git pull
docker compose up -d --build
```

## 5. 回滚

如果只是代码版本回滚：

```bash
cd /opt/qsm
git checkout <old-commit>
docker compose up -d --build
```

如果需要数据回滚：

```bash
python ops/backup/restore_sqlite.py --backup-file storage/backups/<backup-file>.db
docker compose restart app
```

如果同名的 `storage/backups/<backup-file>.settings.env` 存在，恢复脚本会一并回滚运行期设置；当前数据库与当前设置会先各自留下一份 `*.pre-restore-*` 快照，便于快速撤销本次恢复。

## 6. 备份

```bash
cd /opt/qsm
python ops/backup/backup_sqlite.py
```

脚本会按当前生效的 `QSM_DATA_DIR` / `QSM_RUNTIME_ENV_FILE` 解析数据库和运行期设置路径，而不是写死到单一路径。

关键数据目录：
- `storage/db`
- `storage/config`
- `storage/backups`
