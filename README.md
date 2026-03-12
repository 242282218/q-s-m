# QSM Movie Wall

## Docker 部署

数据长期存储目录：
- 数据库：`/root/qsm-movie-wall/data`
- 日志：`/root/qsm-movie-wall/logs`

```bash
mkdir -p /root/qsm-movie-wall/data
mkdir -p /root/qsm-movie-wall/logs

wget -O /root/qsm-movie-wall/.env https://raw.githubusercontent.com/242282218/q-s-m/main/.env.example
# 编辑 /root/qsm-movie-wall/.env，填写 TMDB_API_KEY、QUARK_TRANSFER_COOKIE、API_KEY

docker pull ghcr.io/242282218/q-s-m:latest

docker rm -f qsm-movie-wall 2>/dev/null || true
docker run -d \
  --name qsm-movie-wall \
  --restart unless-stopped \
  --env-file /root/qsm-movie-wall/.env \
  -p 8000:8000 \
  -v /root/qsm-movie-wall/data:/app/data \
  -v /root/qsm-movie-wall/logs:/app/logs \
  ghcr.io/242282218/q-s-m:latest
```

访问：`http://localhost:8000`
