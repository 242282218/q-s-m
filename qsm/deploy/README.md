# 夸克网盘搜索服务 - Docker部署指南

本目录包含在Ubuntu服务器上使用Docker部署夸克网盘搜索服务的所有脚本。

## 文件说明

- `Dockerfile` - Docker镜像构建文件
- `docker-compose.yml` - Docker Compose配置文件
- `install.sh` - 安装脚本（首次部署使用）
- `start.sh` - 启动脚本
- `stop.sh` - 停止脚本
- `restart.sh` - 重启脚本
- `uninstall.sh` - 卸载脚本
- `README.md` - 本说明文档
- `QUICKSTART.md` - 快速开始指南

## 快速开始

### 1. 安装服务

```bash
# 上传整个项目到服务器
scp -r ./backend root@your-server:/tmp/
scp -r ./frontend root@your-server:/tmp/  # 如果有前端
scp requirements.txt root@your-server:/tmp/
scp Dockerfile root@your-server:/tmp/
scp docker-compose.yml root@your-server:/tmp/

# SSH登录服务器
ssh root@your-server

# 进入临时目录
cd /tmp

# 上传部署脚本
mkdir -p /opt/deploy
cp deploy/*.sh /opt/deploy/
chmod +x /opt/deploy/*.sh

# 运行安装脚本
cd /opt/deploy
sudo ./install.sh
```

### 2. 启动服务

```bash
cd /opt/deploy
sudo ./start.sh
```

### 3. 配置宝塔面板反向代理

在宝塔面板中添加反向代理：

1. 登录宝塔面板
2. 进入"网站" → "添加站点"
3. 填写域名（如：quark.example.com）
4. 点击"提交"
5. 进入站点设置 → "反向代理"
6. 点击"添加反向代理"
7. 填写以下信息：
   - 代理名称：`quark-search`
   - 目标URL：`http://127.0.0.1:8000`
   - 发送域名：`$host`
8. 点击"提交"

### 4. 访问服务

安装完成后，服务将在以下地址运行：
- 本地访问：http://localhost:8000
- 网络访问：http://your-server-ip:8000
- 宝塔代理：http://your-domain.com

## 服务管理

### 启动服务

```bash
cd /opt/deploy
sudo ./start.sh
```

### 停止服务

```bash
cd /opt/deploy
sudo ./stop.sh
```

### 重启服务

```bash
cd /opt/deploy
sudo ./restart.sh
```

### 查看服务状态

```bash
cd /opt/quark-search
docker-compose ps
```

### 查看服务日志

```bash
cd /opt/quark-search
docker-compose logs -f
```

### 查看容器资源使用

```bash
docker stats quark-search
```

## 卸载服务

```bash
cd /opt/deploy
sudo ./uninstall.sh
```

**注意**：卸载操作会删除所有数据，请谨慎操作！

## 目录结构

安装后的目录结构：

```
/opt/quark-search/
├── backend/              # 后端代码
│   ├── app/
│   ├── requirements.txt
│   └── ...
├── frontend/             # 前端代码（如果有）
├── Dockerfile           # Docker镜像构建文件
├── docker-compose.yml   # Docker Compose配置
├── logs/                # 日志目录（挂载到宿主机）
└── data/                # 数据目录（挂载到宿主机）
```

## 配置文件

主要配置文件位于：
- `/opt/quark-search/backend/app/config.py` - 应用配置
- `/opt/quark-search/docker-compose.yml` - Docker配置

## 系统要求

- 操作系统：Ubuntu 18.04+ / Debian 10+ / CentOS 7+
- Docker：20.10+
- Docker Compose：2.0+
- 内存：至少 2GB RAM
- 磁盘：至少 10GB 可用空间
- 网络：稳定的互联网连接

## 端口说明

- 8000 - 应用服务端口（Docker容器内部）

## 宝塔面板配置

### 反向代理配置

在宝塔面板中配置反向代理：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # WebSocket支持
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### SSL证书配置

在宝塔面板中配置SSL：

1. 进入站点设置 → "SSL"
2. 选择证书类型（Let's Encrypt免费证书或上传自有证书）
3. 点击"申请"或"上传"
4. 开启"强制HTTPS"

### 防火墙配置

在宝塔面板中配置防火墙：

1. 进入"安全"
2. 添加端口规则：
   - 端口：8000
   - 协议：TCP
   - 策略：放行（仅限内网访问）

## 故障排查

### 容器无法启动

1. 检查Docker服务状态：
   ```bash
   sudo systemctl status docker
   ```

2. 查看容器日志：
   ```bash
   cd /opt/quark-search
   docker-compose logs
   ```

3. 检查端口占用：
   ```bash
   sudo netstat -tlnp | grep 8000
   ```

4. 重新构建镜像：
   ```bash
   cd /opt/quark-search
   docker-compose build --no-cache
   docker-compose up -d
   ```

### 宝塔代理无法访问

1. 检查宝塔Nginx状态：
   ```bash
   sudo systemctl status nginx
   ```

2. 检查反向代理配置：
   - 进入宝塔面板 → 站点设置 → 反向代理
   - 确认目标URL为 `http://127.0.0.1:8000`

3. 查看宝塔Nginx错误日志：
   - 进入宝塔面板 → 软件商店 → Nginx → 设置 → 错误日志

### 容器资源占用过高

1. 查看容器资源使用：
   ```bash
   docker stats quark-search
   ```

2. 限制容器资源使用：
   编辑 `docker-compose.yml`：
   ```yaml
   services:
     quark-search:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 2G
           reservations:
             cpus: '1'
             memory: 1G
   ```

### Python依赖问题

重新构建镜像：

```bash
cd /opt/quark-search
docker-compose build --no-cache
docker-compose up -d
```

## 更新应用

更新应用代码：

```bash
# 1. 停止容器
cd /opt/deploy
sudo ./stop.sh

# 2. 备份当前版本
sudo cp -r /opt/quark-search /opt/quark-search.backup

# 3. 上传新代码
# 使用scp或其他方式上传新代码到 /opt/quark-search/

# 4. 重新构建镜像
cd /opt/quark-search
docker-compose build --no-cache

# 5. 启动容器
cd /opt/deploy
sudo ./start.sh
```

## 安全建议

1. **修改默认端口**：编辑 `docker-compose.yml` 中的端口映射
2. **配置防火墙**：确保端口 8000 仅允许内网访问
3. **使用HTTPS**：在宝塔面板中配置SSL证书
4. **定期备份**：备份 `/opt/quark-search/data` 目录
5. **限制访问**：在宝塔面板中配置IP访问控制
6. **更新Docker**：定期更新Docker和Docker Compose版本

## 性能优化

1. **使用多阶段构建**：优化Docker镜像大小
2. **配置资源限制**：在 `docker-compose.yml` 中设置资源限制
3. **使用缓存**：配置Redis缓存
4. **数据库优化**：如果使用数据库，优化数据库配置
5. **日志轮转**：配置Docker日志轮转

## 监控建议

1. **容器监控**：使用Docker stats监控容器资源
2. **日志监控**：配置日志轮转和日志分析
3. **性能监控**：使用Prometheus + Grafana监控应用性能
4. **告警配置**：配置邮件或短信告警

## 常见问题

### Q: 如何修改服务端口？

A: 编辑 `/opt/quark-search/docker-compose.yml` 中的端口映射，然后重启容器。

### Q: 如何查看实时日志？

A: 使用 `docker-compose logs -f` 命令：
```bash
cd /opt/quark-search
docker-compose logs -f
```

### Q: 容器崩溃后如何自动重启？

A: Docker Compose已配置 `restart: unless-stopped`，容器崩溃后会自动重启。

### Q: 如何查看应用版本？

A: 查看代码中的版本信息或Git提交记录：
```bash
cd /opt/quark-search
git log -1 --oneline
```

### Q: 如何进入容器内部？

A: 使用 `docker exec` 命令：
```bash
docker exec -it quark-search bash
```

### Q: 如何备份容器数据？

A: 备份挂载的目录：
```bash
sudo tar -czf quark-search-backup.tar.gz /opt/quark-search/data /opt/quark-search/logs
```

## 技术支持

如遇到问题，请：
1. 查看容器日志
2. 检查容器状态
3. 参考本文档的故障排查部分
4. 联系技术支持

## 许可证

本脚本遵循项目的开源许可证。
