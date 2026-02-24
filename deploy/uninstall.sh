#!/bin/bash

set -e

echo "=========================================="
echo "  夸克网盘搜索服务 - 卸载脚本"
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
    echo "使用: sudo ./uninstall.sh"
    exit 1
fi

# 配置变量
APP_NAME="quark-search"
APP_DIR="/opt/$APP_NAME"

echo -e "${YELLOW}警告: 此操作将完全移除服务及其所有数据！${NC}"
echo ""
read -p "确认卸载? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "卸载已取消"
    exit 0
fi

echo ""
echo -e "${GREEN}[1/4] 停止并删除容器...${NC}"

# 检查Docker是否安装
if command -v docker &> /dev/null; then
    # 检查应用目录是否存在
    if [ -d "$APP_DIR" ]; then
        cd $APP_DIR
        
        # 停止并删除容器
        if [ -f "docker-compose.yml" ]; then
            docker-compose down -v
            echo "容器已停止并删除"
        else
            # 手动删除容器
            if docker ps -a | grep -q "$APP_NAME"; then
                docker stop $APP_NAME 2>/dev/null || true
                docker rm $APP_NAME 2>/dev/null || true
                echo "容器已停止并删除"
            fi
        fi
    else
        echo "应用目录不存在"
    fi
else
    echo "Docker未安装，跳过容器删除"
fi

echo ""
echo -e "${GREEN}[2/4] 删除Docker镜像...${NC}"

# 删除Docker镜像
if command -v docker &> /dev/null; then
    if docker images | grep -q "$APP_NAME"; then
        docker rmi $(docker images | grep $APP_NAME | awk '{print $3}') 2>/dev/null || true
        echo "Docker镜像已删除"
    else
        echo "Docker镜像不存在"
    fi
else
    echo "Docker未安装，跳过镜像删除"
fi

echo ""
echo -e "${GREEN}[3/4] 删除应用目录...${NC}"

# 删除应用目录
if [ -d "$APP_DIR" ]; then
    echo "删除目录: $APP_DIR"
    rm -rf $APP_DIR
    echo "应用目录已删除"
else
    echo "应用目录不存在"
fi

echo ""
echo -e "${GREEN}[4/4] 清理Docker资源...${NC}"

# 询问是否清理Docker
read -p "是否清理Docker系统? (yes/no): " clean_docker

if [ "$clean_docker" = "yes" ]; then
    if command -v docker &> /dev/null; then
        docker system prune -f
        echo "Docker系统已清理"
    else
        echo "Docker未安装，跳过清理"
    fi
else
    echo "跳过Docker清理"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}卸载完成！${NC}"
echo "=========================================="
echo ""
echo "已移除:"
echo "  - 容器: $APP_NAME"
echo "  - 应用目录: $APP_DIR"
if [ "$clean_docker" = "yes" ]; then
    echo "  - Docker系统资源"
fi
echo ""
echo "如需重新安装，请运行:"
echo "  sudo ./install.sh"
echo ""
