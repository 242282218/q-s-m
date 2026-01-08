# Ubuntu服务器部署 - 快速开始（Docker方式）

## 前置要求

- Ubuntu 18.04+ / Debian 10+ / CentOS 7+
- Root权限
- 稳定的网络连接
- 宝塔面板（可选，用于反向代理）

## 第一步：上传文件到服务器

### 方法1：使用SCP上传（推荐）

```bash
# 在本地Windows PowerShell中执行
scp -r backend root@your-server-ip:/tmp/
scp -r frontend root@your-server-ip:/tmp/
scp requirements.txt root@your-server-ip:/tmp/
scp Dockerfile root@your-server-ip:/tmp/
scp docker-compose.yml root@your-server-ip:/tmp/
scp deploy/*.sh root@your-server-ip:/tmp/
```

### 方法2：使用SFTP工具

使用FileZilla、WinSCP等工具上传：
- `backend/` 目录 → `/tmp/backend/`
- `frontend/` 目录 → `/tmp/frontend/`
- `requirements.txt` → `/tmp/requirements.txt`
- `Dockerfile` → `/tmp/Dockerfile`
- `docker-compose.yml` → `/tmp/docker-compose.yml`
- `deploy/*.sh` → `/tmp/deploy/`

## 第二步：SSH登录服务器

```bash
ssh root@your-server-ip
```

## 第三步：运行安装脚本

```bash
# 创建部署目录并复制脚本
mkdir -p /opt/deploy
cp /tmp/deploy/*.sh /opt/deploy/
chmod +x /opt/deploy/*.sh

# 运行安装脚本
cd /opt/deploy
sudo ./install.sh
```

安装脚本会自动：
1. 检查系统环境
2. 安装Docker和Docker Compose（如果未安装）
3. 创建应用目录
4. 部署应用文件
5. 构建Docker镜像
6. 启动容器

## 第四步：启动服务

```bash
cd /opt/deploy
sudo ./start.sh
```

## 第五步：配置宝塔面板反向代理（可选）

### 1. 添加站点

在宝塔面板中：
1. 进入"网站" → "添加站点"
2. 填写域名（如：quark.example.com）
3. 点击"提交"

### 2. 配置反向代理

1. 进入站点设置 → "反向代理"
2. 点击"添加反向代理"
3. 填写以下信息：
   - 代理名称：`quark-search`
   - 目标URL：`http://127.0.0.1:8000`
   - 发送域名：`$host`
4. 点击"提交"

### 3. 配置SSL证书（推荐）

1. 进入站点设置 → "SSL"
2. 选择证书类型（Let's Encrypt免费证书或上传自有证书）
3. 点击"申请"或"上传"
4. 开启"强制HTTPS"

## 第六步：访问服务

安装完成后，服务将在以下地址运行：
- **本地测试**：http://localhost:8000
- **网络访问**：http://your-server-ip:8000
- **宝塔代理**：http://your-domain.com

## 常用命令

### 服务管理

```bash
# 启动服务
cd /opt/deploy && sudo ./start.sh

# 停止服务
cd /opt/deploy && sudo ./stop.sh

# 重启服务
cd /opt/deploy && sudo ./restart.sh

# 查看容器状态
cd /opt/quark-search && docker-compose ps

# 查看实时日志
cd /opt/quark-search && docker-compose logs -f

# 查看容器资源使用
docker stats quark-search
```

### Docker管理

```bash
# 查看所有容器
docker ps -a

# 查看容器日志
docker logs quark-search

# 进入容器内部
docker exec -it quark-search bash

# 重新构建镜像
cd /opt/quark-search && docker-compose build --no-cache

# 停止并删除容器
cd /opt/quark-search && docker-compose down
```

## 故障排查

### 容器无法启动

1. 检查Docker服务状态：
```bash
sudo systemctl status docker
```

2. 查看容器日志：
```bash
cd /opt/quark-search && docker-compose logs
```

3. 检查端口是否被占用：
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

### Docker相关问题

#### Docker未安装

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh

# CentOS
yum install -y docker
systemctl start docker
systemctl enable docker
```

#### Docker Compose未安装

```bash
# 下载Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# 添加执行权限
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker-compose --version
```

#### 容器资源占用过高

1. 查看容器资源使用：
```bash
docker stats quark-search
```

2. 限制容器资源使用：
编辑 `/opt/quark-search/docker-compose.yml`：
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

3. 重启容器：
```bash
cd /opt/quark-search
docker-compose down
docker-compose up -d
```

## 卸载服务

```bash
cd /opt/deploy
sudo ./uninstall.sh
```

**注意**：卸载会删除所有数据，请谨慎操作！

## 更新应用

```bash
# 1. 停止容器
cd /opt/deploy && sudo ./stop.sh

# 2. 备份当前版本
sudo cp -r /opt/quark-search /opt/quark-search.backup

# 3. 上传新代码（使用SCP或其他方式）

# 4. 重新构建镜像
cd /opt/quark-search
docker-compose build --no-cache

# 5. 启动容器
cd /opt/deploy && sudo ./start.sh
```

## 安全建议

1. **修改默认端口**：编辑 `docker-compose.yml` 中的端口映射
2. **配置防火墙**：
   ```bash
   # Ubuntu/Debian
   sudo ufw allow 8000/tcp
   
   # CentOS/RHEL
   sudo firewall-cmd --permanent --add-port=8000/tcp
   sudo firewall-cmd --reload
   ```
3. **使用HTTPS**：在宝塔面板中配置SSL证书
4. **定期备份**：备份 `/opt/quark-search/data` 目录
5. **限制访问**：在宝塔面板中配置IP访问控制

## 性能优化

### 1. 配置资源限制

编辑 `/opt/quark-search/docker-compose.yml`：
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

### 2. 配置日志轮转

编辑 `/etc/docker/daemon.json`：
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

重启Docker：
```bash
sudo systemctl restart docker
```

## 获取帮助

查看详细的部署文档：
```bash
cat /opt/deploy/README.md
```

查看快速开始指南：
```bash
cat /opt/deploy/QUICKSTART.md
```

## 技术支持

如遇到问题，请：
1. 查看容器日志
2. 检查容器状态
3. 参考故障排查部分
4. 联系技术支持

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

/opt/deploy/
├── install.sh           # 安装脚本
├── start.sh             # 启动脚本
├── stop.sh              # 停止脚本
├── restart.sh           # 重启脚本
├── uninstall.sh         # 卸载脚本
├── README.md            # 详细文档
└── QUICKSTART.md        # 快速开始指南
```

## 常见问题

### Q: 如何修改服务端口？

A: 编辑 `/opt/quark-search/docker-compose.yml` 中的端口映射：
```yaml
ports:
  - "9000:8000"  # 将外部端口改为9000
```
然后重启容器：
```bash
cd /opt/deploy && sudo ./restart.sh
```

### Q: 如何查看实时日志？

A: 使用 `docker-compose logs -f` 命令：
```bash
cd /opt/quark-search
docker-compose logs -f
```

### Q: 容器崩溃后如何自动重启？

A: Docker Compose已配置 `restart: unless-stopped`，容器崩溃后会自动重启。

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

### Q: 如何清理Docker资源？

A: 清理未使用的Docker资源：
```bash
docker system prune -a
```

### Q: 如何查看Docker版本？

A: 查看Docker和Docker Compose版本：
```bash
docker --version
docker-compose --version
```

### Q: 如何重启Docker服务？

A: 重启Docker服务：
```bash
sudo systemctl restart docker
```

### Q: 如何查看Docker日志？

A: 查看Docker服务日志：
```bash
sudo journalctl -u docker -f
```

### Q: 如何更新Docker？

A: 更新Docker到最新版本：
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io

# CentOS/RHEL
sudo yum update docker-ce docker-ce-cli containerd.io
```
