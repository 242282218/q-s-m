#!/bin/bash

set -e

echo "=========================================="
echo "  夸克网盘搜索服务 - 重启脚本"
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
    echo "使用: sudo ./restart.sh"
    exit 1
fi

# 配置变量
APP_NAME="quark-search"
APP_DIR="/opt/$APP_NAME"
PORT=8000

echo -e "${GREEN}[1/2] 重启容器...${NC}"

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

# 重启容器
cd $APP_DIR
docker-compose restart

# 等待容器启动
sleep 3

# 检查容器状态
if docker ps | grep -q "$APP_NAME"; then
    echo -e "${GREEN}容器重启成功！${NC}"
    
    # 获取服务器IP
    SERVER_IP=$(hostname -I | awk '{print $2}')
    
    echo ""
    echo "=========================================="
    echo -e "${GREEN}服务信息${NC}"
    echo "=========================================="
    echo "容器名称: $APP_NAME"
    echo "容器状态: 运行中"
    echo "访问地址: http://$SERVER_IP:$PORT"
    echo ""
    echo "管理命令:"
    echo "  查看状态: cd $APP_DIR && docker-compose ps"
    echo "  查看日志: cd $APP_DIR && docker-compose logs -f"
    echo "  停止服务: sudo ./stop.sh"
    echo ""
else
    echo -e "${RED}容器重启失败！${NC}"
    echo ""
    echo "查看容器日志:"
    echo "  cd $APP_DIR && docker-compose logs"
    echo ""
    exit 1
fi
