#!/bin/bash

# 检查是否安装 Docker
if ! command -v docker &> /dev/null; then
    echo "Docker 未安装，正在尝试自动安装..."
    curl -fsSL https://get.docker.com | bash
    if ! command -v docker &> /dev/null; then
        echo "Docker 安装失败，请手动安装后重试。"
        exit 1
    fi
fi

# 检查是否安装 Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose 未安装，正在尝试自动安装..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 确保 .env 文件存在
if [ ! -f .env ]; then
    echo "创建默认 .env 文件..."
    # 尝试从 backend/.env 复制，如果不存在则创建空的
    if [ -f backend/.env ]; then
        cp backend/.env .env
    else
        touch .env
    fi
fi

# 创建日志目录
mkdir -p logs

echo "开始构建并启动服务..."
# 停止旧容器（如果有）
docker-compose down

# 构建并启动
docker-compose up -d --build

echo "========================================"
echo "服务已启动！"
echo "访问地址: http://$(curl -s ifconfig.me):8000"
echo "本地地址: http://localhost:8000"
echo "查看日志: docker-compose logs -f"
echo "========================================"
