# QSM Movie Wall

## Release Docker 部署

1. 在 GitHub 创建并发布一个 Release，例如 `v0.1.0`。
2. GitHub Actions 会自动构建 Docker 镜像，并把这两个文件挂到该 Release：
   - `qsm-movie-wall-<tag>-linux-amd64.tar.gz`
   - `qsm-movie-wall-<tag>-linux-amd64.tar.gz.sha256`
3. 下载镜像包后执行：

```bash
cp .env.example .env
# 填写 TMDB_API_KEY、QUARK_TRANSFER_COOKIE、API_KEY
gunzip -c qsm-movie-wall-v0.1.0-linux-amd64.tar.gz | docker load
mkdir -p logs
docker run -d \
  --name qsm-movie-wall \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/logs:/app/logs" \
  qsm-movie-wall:v0.1.0
```

访问：`http://localhost:8000`

## 本地构建部署

```bash
cp .env.example .env
# 填写 TMDB_API_KEY、QUARK_TRANSFER_COOKIE、API_KEY
docker compose up -d --build
```
