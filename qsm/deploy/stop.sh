#!/bin/bash

set -e

echo "=========================================="
echo "  夸克网盘搜索服务 - 停止脚本"
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
    echo "使用: sudo ./stop.sh"
    exit 1
fi

# 配置变量
APP_NAME="quark-search"
APP_DIR="/opt/$APP_NAME"

echo -e "${GREEN}[1/2] 检查容器状态...${NC}"

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    exit 1
fi

# 检查应用目录是否存在
if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}错误: 应用目录不存在: $APP_DIR${NC}"
    exit 1
fi

# 检查容器是否存在
cd $APP_DIR
if ! docker ps -a | grep -q "$APP_NAME"; then
    echo -e "${YELLOW}容器不存在${NC}"
    exit 0
fi

# 检查容器是否在运行
if ! docker ps | grep -q "$APP_NAME"; then
    echo -e "${YELLOW}容器未运行${NC}"
    exit 0
fi

echo -e "${GREEN}[2/2] 停止容器...${NC}"

# 停止容器
docker-compose stop

# 等待容器停止
sleep 2

# 检查容器状态
if docker ps | grep -q "$APP_NAME"; then
    echo -e "${RED}容器停止失败！${NC}"
    echo ""
    echo "尝试强制停止:"
    echo "  cd $APP_DIR && docker-compose kill"
    echo ""
    exit 1
else
    echo -e "${GREEN}容器已成功停止！${NC}"
    echo ""
    echo "=========================================="
    echo "服务信息"
    echo "=========================================="
    echo "容器名称: $APP_NAME"
    echo "容器状态: 已停止"
    echo "应用目录: $APP_DIR"
    echo ""
    echo "重新启动服务:"
    echo "  sudo ./start.sh"
    echo "  或: sudo ./restart.sh"
    echo ""
fi
