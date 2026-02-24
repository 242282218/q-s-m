# AI-Powered Cloud Media Center (QSM)

基于夸克网盘的智能云端媒体中心，集成了海报墙管理、自动转存和智能重命名功能。

## 🚀 功能特性

### 1. 🎬 智能海报墙
- **TMDB 集成**: 自动获取电影/电视剧元数据（海报、简介、评分）。
- **收藏管理**: 可视化管理待看列表。
- **状态追踪**: 实时跟踪资源状态（已收藏、已转存、已失效）。

### 2. ⚡ 极速转存引擎
- **自动化转存**: 从分享链接一键转存到夸克网盘。
- **链接验证**: 自动检测分享链接有效性。
- **自动分类**: 根据媒体类型智能归档到 `/收藏TV/Movies` 或 `/收藏TV/TV Shows`。

### 3. 🏷️ 智能重命名 (Renamer)
- **Emby/Kodi 兼容**: 自动将文件名标准化为媒体库友好格式。
- **规则引擎**:
  - 电影: `Title (Year).ext`
  - 剧集: `Title (Year)/Season S/Title - SxxExx.ext`
- **中文支持**: 完美处理中文文件名和特殊字符。

## 🛠️ 安装与部署

### 1. 环境要求
- Python 3.10+ (传统部署)
- Docker 和 Docker Compose (推荐，简化部署)
- 夸克网盘账号 (VIP 账号体验更佳)
- TMDB API Key

### 2. 部署方式

#### 2.1 传统部署

**安装依赖**
```bash
cd backend
pip install -r requirements.txt
```

**配置**
在 `backend` 目录下创建 `.env` 文件：
```ini
# TMDB 配置
TMDB_API_KEY=your_tmdb_api_key
DEFAULT_LANG=zh-CN
TMDB_IMAGE_BASE_URL=https://image.tmdb.org/t/p/original

# 夸克网盘配置
QUARK_COOKIE=your_quark_cookie_string

# 数据库配置
DATABASE_URL=sqlite:///./qsm.db
```

**运行服务**
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 7809
```

#### 2.2 Docker 部署 (推荐)

**环境准备**
```bash
# 安装 Docker 和 Docker Compose
# Ubuntu/Debian
apt update && apt install -y docker.io docker-compose

# CentOS/RHEL
yum install -y docker docker-compose
systemctl start docker
systemctl enable docker
```

**配置 Docker 镜像加速器（推荐）**
```bash
# 创建配置目录
sudo mkdir -p /etc/docker

# 写入配置（使用国内镜像源）
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}
EOF

# 重启 Docker
sudo systemctl daemon-reload
sudo systemctl restart docker

# 验证配置
sudo docker info | grep -A 10 "Registry Mirrors"
```

**配置环境变量**
```bash
cd backend
cp .env.example .env  # 如果没有示例文件，直接创建
nano .env  # 编辑配置
```

**构建并启动**
```bash
# 在项目根目录执行
docker compose up -d --build
```

**管理命令**
```bash
docker compose ps  # 查看容器状态
docker compose logs -f  # 查看实时日志
docker compose down  # 停止服务
docker compose restart  # 重启服务
docker compose up -d --build  # 更新代码后重新构建
```

**清理 Docker 资源**
```bash
# 使用清理脚本（推荐）
chmod +x DOCKER_CLEANUP.sh
./DOCKER_CLEANUP.sh

# 或手动清理
docker system prune -a --volumes  # 清理所有未使用的资源
```

**性能优化**
- 首次构建时间：2-3 分钟（使用国内镜像源）
- 重复构建时间：30-60 秒（利用 Docker 层缓存）
- 镜像大小：600-700 MB

详细优化说明请查看 [DOCKER_OPTIMIZATION.md](DOCKER_OPTIMIZATION.md)

### 3. 访问应用

部署完成后，通过以下地址访问：
- 首页：http://your-server-ip:7809
- 收藏页面：http://your-server-ip:7809/collection
- API 端点：http://your-server-ip:7809/api

## 📖 使用指南

1. **浏览与收藏**: 访问首页，搜索电影/剧集，点击海报进入详情页。
2. **添加资源**: 在详情页点击"收藏"，输入夸克分享链接（支持自动识别）。
3. **我的收藏**: 点击顶部"我的收藏"查看已添加的资源。
4. **转存资源**: 在收藏列表点击转存按钮，将资源保存到网盘。

## 🏗️ 项目结构
```
qsm/
├── backend/
│   ├── app/
│   │   ├── collection/   # 收藏管理模块
│   │   ├── db/          # 数据库模型
│   │   ├── quark/       # 搜索与元数据
│   │   ├── templates/   # 前端模板 (Jinja2)
│   │   ├── transfer/    # 转存与重命名引擎
│   │   └── main.py      # 应用入口
│   ├── tests/           # 测试用例
│   └── requirements.txt
├── docs/                # 开发文档
└── README.md
```

## 📄 许可证
MIT License
