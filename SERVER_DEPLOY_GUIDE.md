# QSM Media Center - 服务器部署指南

## 📋 部署前准备

### 1. 服务器要求
- 操作系统：Ubuntu 20.04+ / Debian 10+ / CentOS 7+
- Python版本：Python 3.8+
- 内存：至少 512MB RAM
- 磁盘空间：至少 1GB 可用空间
- 网络：可以访问 TMDB API 和夸克网盘

### 2. 需要的文件

**必需文件清单**（只上传这些文件）：

```
qsm/
├── backend/
│   ├── app/                          # 应用代码
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI 主应用
│   │   ├── config.py                 # 配置文件
│   │   ├── tmdb.py                   # TMDB API 客户端
│   │   ├── collection/               # 收藏功能
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   ├── db/                       # 数据库
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── session.py
│   │   ├── quark/                    # 夸克网盘功能
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   └── schemas/
│   │   ├── transfer/                 # 转存功能
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── quark_client.py
│   │   │   └── renamer.py
│   │   ├── webdav/                   # WebDAV 服务
│   │   │   ├── __init__.py
│   │   │   └── provider.py
│   │   ├── static/                   # 静态文件
│   │   │   └── css/
│   │   │       └── main.css
│   │   └── templates/                # 模板文件
│   │       ├── base.html
│   │       ├── home.html
│   │       ├── detail.html
│   │       ├── search.html
│   │       ├── collection.html
│   │       ├── person.html
│   │       └── partials/
│   │           └── poster_card.html
│   ├── requirements.txt              # Python 依赖
│   ├── .env.example                  # 环境变量示例
│   └── start_server.py               # 启动脚本
├── Dockerfile                        # Docker 配置
├── docker-compose.yml                # Docker Compose 配置
├── README.md                         # 项目说明
└── SERVER_DEPLOY.sh                  # 服务器部署脚本（新增）
```

**不要上传的文件**：
- `__pycache__/` - Python 缓存
- `*.pyc` - 编译的 Python 文件
- `venv/` - 虚拟环境
- `*.db` - 数据库文件
- `logs/` - 日志文件
- `.ai/` - AI 工具配置
- `.trae/` - Trae 配置
- `docs/` - 文档
- `scripts/` - 测试脚本
- `参考项目/` - 参考项目
- `.env` - 环境变量（包含敏感信息）

## 🚀 部署步骤

### 方法一：使用部署脚本（推荐）

#### 1. 在本地准备文件

```bash
# 在 Windows 上，使用以下命令打包必要文件
cd C:\Users\24228\Desktop\qsm

# 创建部署包
tar -czf qsm-deploy.tar.gz \
  backend/app \
  backend/requirements.txt \
  backend/.env.example \
  backend/start_server.py \
  Dockerfile \
  docker-compose.yml \
  README.md \
  SERVER_DEPLOY.sh
```

#### 2. 上传到服务器

```bash
# 使用 SCP 上传
scp qsm-deploy.tar.gz root@103.149.91.156:~/qsm-deploy.tar.gz

# 或使用 SFTP 工具（如 FileZilla、WinSCP）
```

#### 3. 在服务器上部署

```bash
# SSH 登录到服务器
ssh root@103.149.91.156

# 解压部署包
cd ~
tar -xzf qsm-deploy.tar.gz

# 运行部署脚本
chmod +x SERVER_DEPLOY.sh
./SERVER_DEPLOY.sh
```

### 方法二：手动部署

#### 1. 上传文件到服务器

```bash
# 在服务器上创建目录
mkdir -p ~/qsm/backend
cd ~/qsm

# 上传 backend/app 目录
scp -r backend/app root@103.149.91.156:~/qsm/backend/

# 上传其他必需文件
scp backend/requirements.txt root@103.149.91.156:~/qsm/backend/
scp backend/.env.example root@103.149.91.156:~/qsm/backend/
scp backend/start_server.py root@103.149.91.156:~/qsm/backend/
scp Dockerfile root@103.149.91.156:~/qsm/
scp docker-compose.yml root@103.149.91.156:~/qsm/
```

#### 2. 在服务器上配置

```bash
# SSH 登录到服务器
ssh root@103.149.91.156

# 进入项目目录
cd ~/qsm/backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建环境变量文件
cp .env.example .env

# 编辑 .env 文件，填入您的配置
nano .env
```

#### 3. 配置环境变量

编辑 `backend/.env` 文件：

```bash
# TMDB API 配置
TMDB_API_KEY=your_tmdb_api_key_here
DEFAULT_LANG=zh-CN
TMDB_API_BASE=https://api.themoviedb.org/3
TMDB_IMAGE_BASE=https://image.tmdb.org/t/p/

# 夸克网盘配置
QUARK_TRANSFER_COOKIE=your_quark_cookie_here

# 可选：代理配置（如果需要）
# HTTP_PROXY=http://proxy.example.com:8080
# HTTPS_PROXY=http://proxy.example.com:8080
```

**获取 TMDB API Key**：
1. 访问 https://www.themoviedb.org/
2. 注册账号并登录
3. 访问 https://www.themoviedb.org/settings/api
4. 申请 API Key

**获取夸克 Cookie**：
1. 登录夸克网盘网页版
2. 打开浏览器开发者工具（F12）
3. 切换到 Network 标签
4. 刷新页面
5. 找到任意请求，复制 Cookie 值

#### 4. 启动服务

```bash
# 激活虚拟环境
cd ~/qsm/backend
source venv/bin/activate

# 启动服务
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7809 --reload
```

#### 5. 验证部署

```bash
# 在服务器上测试
curl http://localhost:7809/api/health

# 应该返回：
# {"status":"ok","service":"qsm-media-center","timestamp":"..."}

# 从外部访问
curl http://103.149.91.156:7809/api/health
```

## 🐳 使用 Docker 部署（可选）

### 1. 上传文件

```bash
# 上传 Dockerfile 和 docker-compose.yml
scp Dockerfile root@103.149.91.156:~/qsm/
scp docker-compose.yml root@103.149.91.156:~/qsm/
```

### 2. 构建并启动

```bash
# SSH 登录到服务器
ssh root@103.149.91.156

# 进入项目目录
cd ~/qsm

# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 🔧 常见问题

### 问题1：ModuleNotFoundError

**错误信息**：
```
ModuleNotFoundError: No module named 'xxx'
```

**解决方案**：
```bash
# 确保在虚拟环境中
source venv/bin/activate

# 重新安装依赖
pip install -r requirements.txt
```

### 问题2：端口被占用

**错误信息**：
```
OSError: [Errno 48] Address already in use
```

**解决方案**：
```bash
# 查找占用端口的进程
lsof -i :7809

# 杀死进程
kill -9 <PID>

# 或使用其他端口
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7810 --reload
```

### 问题3：TMDB API 失败

**错误信息**：
```
httpx.HTTPStatusError: 401 Unauthorized
```

**解决方案**：
```bash
# 检查 TMDB_API_KEY 是否正确
nano backend/.env

# 确保 TMDB_API_KEY 有效
# 访问 https://www.themoviedb.org/settings/api 重新申请
```

### 问题4：数据库错误

**错误信息**：
```
sqlite3.OperationalError: unable to open database file
```

**解决方案**：
```bash
# 创建 data 目录
mkdir -p backend/data

# 检查权限
chmod 755 backend/data
```

## 📊 监控和维护

### 查看日志

```bash
# 如果使用 systemd
journalctl -u qsm-media-center -f

# 如果使用 docker
docker-compose logs -f

# 如果直接运行
# 日志会输出到终端
```

### 重启服务

```bash
# 如果使用 systemd
systemctl restart qsm-media-center

# 如果使用 docker
docker-compose restart

# 如果直接运行
# Ctrl+C 停止，然后重新启动
```

### 更新代码

```bash
# 停止服务
# 如果使用 systemd
systemctl stop qsm-media-center

# 如果使用 docker
docker-compose down

# 上传新文件
scp -r backend/app root@103.149.91.156:~/qsm/backend/

# 重新启动
systemctl start qsm-media-center
# 或
docker-compose up -d
```

## 🔒 安全建议

1. **使用防火墙**：
```bash
# 只允许特定端口
ufw allow 22/tcp    # SSH
ufw allow 7809/tcp  # 应用端口
ufw enable
```

2. **使用 HTTPS**：
- 配置 Nginx 反向代理
- 使用 Let's Encrypt 免费证书

3. **定期更新**：
```bash
# 更新系统
apt update && apt upgrade -y

# 更新 Python 依赖
pip install --upgrade -r requirements.txt
```

4. **备份数据**：
```bash
# 备份数据库
cp backend/data/qsm.db ~/backup/qsm-$(date +%Y%m%d).db

# 备份配置
cp backend/.env ~/backup/.env-$(date +%Y%m%d)
```

## 📞 技术支持

如果遇到问题，请检查：
1. 日志文件
2. 环境变量配置
3. 网络连接
4. 依赖版本

---

**部署完成后，访问地址**：
- 本地：http://localhost:7809
- 服务器：http://103.149.91.156:7809
