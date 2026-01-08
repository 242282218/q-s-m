#!/bin/bash

set -e

echo "=========================================="
echo "  夸克网盘搜索服务 - 启动脚本"
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
    echo "使用: sudo ./start.sh"
    exit 1
fi

# 配置变量
APP_NAME="quark-search"
APP_DIR="/opt/$APP_NAME"
PORT=8000

echo -e "${GREEN}[1/3] 检查Docker环境...${NC}"

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    echo "请先运行 ./install.sh 安装Docker"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}错误: Docker Compose未安装${NC}"
    echo "请先运行 ./install.sh 安装Docker Compose"
    exit 1
fi

echo -e "${GREEN}[2/3] 检查容器状态...${NC}"

# 检查应用目录是否存在
if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}错误: 应用目录不存在: $APP_DIR${NC}"
    echo "请先运行 ./install.sh 安装应用"
    exit 1
fi

# 检查容器是否已存在
cd $APP_DIR
if docker ps -a | grep -q "$APP_NAME"; then
    # 检查容器是否已在运行
    if docker ps | grep -q "$APP_NAME"; then
        echo -e "${YELLOW}容器已在运行中${NC}"
        echo "如需重启，请使用: sudo ./restart.sh"
        exit 0
    else
        echo "容器已存在但未运行，正在启动..."
    fi
else
    echo "容器不存在，正在创建并启动..."
fi

echo -e "${GREEN}[3/3] 启动容器...${NC}"

# 启动容器
docker-compose up -d

# 等待容器启动
sleep 3

# 检查容器状态
if docker ps | grep -q "$APP_NAME"; then
    echo -e "${GREEN}容器启动成功！${NC}"
    
    # 获取服务器IP
    SERVER_IP=$(hostname -I | awk '{print $2}')
    
    echo ""
    echo "=========================================="
    echo -e "${GREEN}服务信息${NC}"
    echo "=========================================="
    echo "容器名称: $APP_NAME"
    echo "容器状态: 运行中"
    echo "访问地址: http://$SERVER_IP:$PORT"
    echo "应用目录: $APP_DIR"
    echo ""
    echo "管理命令:"
    echo "  查看状态: cd $APP_DIR && docker-compose ps"
    echo "  查看日志: cd $APP_DIR && docker-compose logs -f"
    echo "  停止服务: sudo ./stop.sh"
    echo "  重启服务: sudo ./restart.sh"
    echo ""
    echo -e "${YELLOW}宝塔面板配置${NC}"
    echo "  在宝塔面板中添加反向代理:"
    echo "  - 代理名称: $APP_NAME"
    echo "  - 目标URL: http://127.0.0.1:$PORT"
    echo "  - 发送域名: \$host"
    echo ""
else
    echo -e "${RED}容器启动失败！${NC}"
    echo ""
    echo "查看容器日志:"
    echo "  cd $APP_DIR && docker-compose logs"
    echo ""
    exit 1
fi
