#!/bin/bash

set -e

echo "=========================================="
echo "  夸克网盘搜索服务 - Docker安装脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误: 请使用root用户运行此脚本${NC}"
    echo "使用: sudo ./install.sh"
    exit 1
fi

# 配置变量
APP_NAME="quark-search"
APP_DIR="/opt/$APP_NAME"
PORT=8000

echo -e "${GREEN}[1/7] 检查系统环境...${NC}"

# 检查操作系统
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo "检测到操作系统: $PRETTY_NAME"
else
    echo -e "${RED}错误: 无法检测操作系统${NC}"
    exit 1
fi

# 检查Docker是否已安装
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker未安装，开始安装Docker...${NC}"
    
    echo ""
    echo -e "${GREEN}[2/7] 安装Docker...${NC}"
    
    # 安装Docker
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        apt-get update -y
        apt-get install -y \
            apt-transport-https \
            ca-certificates \
            curl \
            gnupg \
            lsb-release
        
        # 添加Docker官方GPG密钥
        curl -fsSL https://download.docker.com/linux/$OS/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        
        # 添加Docker仓库
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/$OS $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        # 安装Docker
        apt-get update -y
        apt-get install -y docker-ce docker-ce-cli containerd.io
        
    elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
        yum install -y yum-utils
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        yum install -y docker-ce docker-ce-cli containerd.io
    fi
    
    # 启动Docker服务
    systemctl start docker
    systemctl enable docker
    
    # 安装Docker Compose
    curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    echo -e "${GREEN}Docker安装完成${NC}"
else
    DOCKER_VERSION=$(docker --version)
    echo "Docker已安装: $DOCKER_VERSION"
fi

# 检查Docker Compose是否已安装
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Docker Compose未安装，开始安装...${NC}"
    curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}Docker Compose安装完成${NC}"
else
    COMPOSE_VERSION=$(docker-compose --version)
    echo "Docker Compose已安装: $COMPOSE_VERSION"
fi

echo ""
echo -e "${GREEN}[3/7] 创建应用目录...${NC}"

# 创建应用目录
mkdir -p $APP_DIR
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/data

echo "应用目录: $APP_DIR"

echo ""
echo -e "${GREEN}[4/7] 部署应用文件...${NC}"

# 检查是否从当前目录部署
if [ -f "./backend" ] && [ -d "./backend" ]; then
    echo "从当前目录部署应用文件..."
    cp -r ./backend $APP_DIR/
    cp -r ./frontend $APP_DIR/ 2>/dev/null || echo "前端目录不存在，跳过"
    cp requirements.txt $APP_DIR/ 2>/dev/null || echo "requirements.txt不存在，跳过"
    cp Dockerfile $APP_DIR/ 2>/dev/null || echo "Dockerfile不存在，跳过"
    cp docker-compose.yml $APP_DIR/ 2>/dev/null || echo "docker-compose.yml不存在，跳过"
else
    echo -e "${YELLOW}警告: 未找到backend目录，请确保在项目根目录运行此脚本${NC}"
    echo "您需要手动将应用文件复制到 $APP_DIR"
fi

echo ""
echo -e "${GREEN}[5/7] 检查端口占用...${NC}"

# 检查端口是否被占用
if netstat -tlnp 2>/dev/null | grep -q ":$PORT "; then
    echo -e "${YELLOW}警告: 端口 $PORT 已被占用${NC}"
    echo "占用进程:"
    netstat -tlnp 2>/dev/null | grep ":$PORT "
    read -p "是否继续? (yes/no): " continue_install
    if [ "$continue_install" != "yes" ]; then
        echo "安装已取消"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}[6/7] 构建Docker镜像...${NC}"

# 构建Docker镜像
cd $APP_DIR
if [ -f "docker-compose.yml" ]; then
    docker-compose build
    echo -e "${GREEN}Docker镜像构建完成${NC}"
else
    echo -e "${RED}错误: docker-compose.yml不存在${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}[7/7] 启动容器...${NC}"

# 启动容器
docker-compose up -d

# 等待容器启动
sleep 5

# 检查容器状态
if docker ps | grep -q "$APP_NAME"; then
    echo -e "${GREEN}容器启动成功！${NC}"
else
    echo -e "${RED}容器启动失败！${NC}"
    echo ""
    echo "查看容器日志:"
    echo "  cd $APP_DIR && docker-compose logs"
    echo ""
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}安装完成！${NC}"
echo "=========================================="
echo ""
echo "应用目录: $APP_DIR"
echo "容器名称: $APP_NAME"
echo "访问地址: http://$(hostname -I | awk '{print $2}'):$PORT"
echo ""
echo "使用以下命令管理服务:"
echo "  查看状态: cd $APP_DIR && docker-compose ps"
echo "  查看日志: cd $APP_DIR && docker-compose logs -f"
echo "  停止服务: cd $APP_DIR && docker-compose stop"
echo "  启动服务: cd $APP_DIR && docker-compose start"
echo "  重启服务: cd $APP_DIR && docker-compose restart"
echo "  停止并删除: cd $APP_DIR && docker-compose down"
echo ""
echo -e "${YELLOW}提示: 宝塔面板配置${NC}"
echo "  在宝塔面板中添加反向代理:"
echo "  - 代理名称: $APP_NAME"
echo "  - 目标URL: http://127.0.0.1:$PORT"
echo "  - 发送域名: \$host"
echo ""
