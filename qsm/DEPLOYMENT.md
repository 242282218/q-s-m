# Docker 镜像部署指南

## 镜像信息

- **镜像名称**: tmdb_wall_tgapi-quark-search:latest
- **镜像大小**: 66.4MB
- **导出文件**: quark-search.tar (63.35MB)
- **端口**: 7799

---

## 方法1：导出/导入镜像（推荐，无需Docker Hub）

### 步骤1：本地导出镜像

```bash
# 导出镜像
docker save tmdb_wall_tgapi-quark-search:latest -o quark-search.tar
```

### 步骤2：上传到服务器

```bash
# 上传镜像和配置文件
scp quark-search.tar root@your_server_ip:/tmp/
scp docker-compose.yml root@your_server_ip:/tmp/
```

### 步骤3：服务器上部署

```bash
# SSH登录服务器
ssh root@your_server_ip

# 创建工作目录
mkdir -p /root/qsm
cd /root/qsm

# 复制文件
cp /tmp/docker-compose.yml .
cp /tmp/quark-search.tar .

# 加载镜像
docker load -i quark-search.tar

# 启动容器
docker compose up -d

# 查看状态
docker compose ps

# 测试服务
curl http://localhost:7799
curl "http://localhost:7799/api/quark/search/title?title=test"
```

### 步骤4：验证部署

```bash
# 查看容器日志
docker compose logs -f

# 查看容器状态
docker compose ps

# 测试API
curl "http://localhost:7799/api/quark/search/title?title=倚天屠龙记"
```

---

## 方法2：使用部署脚本（自动化）

### 使用一键部署脚本

```bash
# 给脚本执行权限
chmod +x deploy.sh

# 部署到服务器（替换为你的服务器IP）
bash deploy.sh your_server_ip root
```

---

## 方法3：直接在服务器构建（无需上传镜像）

### 步骤1：上传源代码

```bash
# 上传整个项目到服务器
scp -r backend root@your_server_ip:/root/qsm/
scp docker-compose.yml root@your_server_ip:/root/qsm/
scp Dockerfile root@your_server_ip:/root/qsm/
scp .dockerignore root@your_server_ip:/root/qsm/
```

### 步骤2：服务器上构建

```bash
# SSH登录服务器
ssh root@your_server_ip

# 进入项目目录
cd /root/qsm

# 构建镜像
docker compose build

# 启动容器
docker compose up -d
```

---

## 方法4：使用Docker Hub（需要账号）

### 步骤1：本地打标签并推送

```bash
# 登录Docker Hub
docker login

# 打标签（替换为你的用户名）
docker tag tmdb_wall_tgapi-quark-search:latest your_username/quark-search:latest

# 推送到Docker Hub
docker push your_username/quark-search:latest
```

### 步骤2：修改docker-compose.yml

```yaml
services:
  quark-search:
    image: your_username/quark-search:latest  # 使用Docker Hub镜像
    # build:
    #   context: .
    #   dockerfile: Dockerfile
    container_name: quark-search
    restart: unless-stopped
    ports:
      - "7799:8000"
```

### 步骤3：服务器上部署

```bash
# SSH登录服务器
ssh root@your_server_ip

# 创建工作目录
mkdir -p /root/qsm
cd /root/qsm

# 创建docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: "3.8"

services:
  quark-search:
    image: your_username/quark-search:latest
    container_name: quark-search
    restart: unless-stopped
    ports:
      - "7799:8000"
    environment:
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    networks:
      - quark-network

networks:
  quark-network:
    driver: bridge

volumes:
  logs:
  data:
EOF

# 拉取并启动
docker compose pull
docker compose up -d
```

---

## 常用管理命令

### 查看容器状态

```bash
docker compose ps
```

### 查看日志

```bash
# 实时查看日志
docker compose logs -f

# 查看最近100行日志
docker compose logs --tail=100
```

### 重启服务

```bash
docker compose restart
```

### 停止服务

```bash
docker compose down
```

### 更新镜像

```bash
# 方法1：重新加载镜像
docker compose down
docker load -i quark-search.tar
docker compose up -d

# 方法2：重新构建
docker compose down
docker compose build
docker compose up -d
```

### 进入容器

```bash
docker exec -it quark-search bash
```

---

## 防火墙配置

### Ubuntu/Debian

```bash
# 允许7799端口
ufw allow 7799/tcp

# 查看防火墙状态
ufw status
```

### CentOS/RHEL

```bash
# 允许7799端口
firewall-cmd --permanent --add-port=7799/tcp
firewall-cmd --reload

# 查看防火墙状态
firewall-cmd --list-ports
```

---

## 故障排查

### 容器无法启动

```bash
# 查看详细日志
docker compose logs

# 检查端口占用
netstat -tlnp | grep 7799

# 检查Docker服务
systemctl status docker
```

### 镜像加载失败

```bash
# 检查镜像文件完整性
ls -lh quark-search.tar

# 重新加载
docker load -i quark-search.tar

# 查看镜像列表
docker images
```

### API访问失败

```bash
# 检查容器状态
docker compose ps

# 检查端口映射
docker port quark-search

# 测试本地访问
curl http://localhost:7799

# 测试容器内部
docker exec quark-search curl http://localhost:8000
```

---

## 性能优化

### 限制资源使用

在docker-compose.yml中添加：

```yaml
services:
  quark-search:
    # ... 其他配置
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

### 日志轮转

```yaml
services:
  quark-search:
    # ... 其他配置
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 备份与恢复

### 备份数据

```bash
# 备份数据卷
docker run --rm -v qsm_logs:/data -v $(pwd):/backup alpine tar czf /backup/logs-backup.tar.gz /data

# 备份配置
tar czf config-backup.tar.gz docker-compose.yml
```

### 恢复数据

```bash
# 恢复数据卷
docker run --rm -v qsm_logs:/data -v $(pwd):/backup alpine tar xzf /backup/logs-backup.tar.gz -C /

# 恢复配置
tar xzf config-backup.tar.gz
```

---

## 监控

### 查看资源使用

```bash
# 查看容器资源使用
docker stats quark-search

# 查看磁盘使用
docker system df
```

### 健康检查

```bash
# 查看健康状态
docker inspect quark-search | grep -A 10 Health
```

---

## 安全建议

1. **使用非root用户运行容器**
2. **限制容器权限**
3. **定期更新镜像**
4. **使用HTTPS反向代理**
5. **配置防火墙规则**
6. **定期备份数据**

---

## 联系支持

如有问题，请查看：
- 容器日志: `docker compose logs -f`
- 系统日志: `journalctl -u docker`
- 应用文档: `开发进度文档.md`
