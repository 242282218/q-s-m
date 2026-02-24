#!/bin/bash

# QSM Media Center - Docker 清理脚本

echo "=========================================="
echo "  QSM Media Center - Docker 清理"
echo "=========================================="
echo ""

read -p "确定要清理 Docker 资源吗？(y/n): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消清理"
    exit 0
fi

echo ""
echo "[1/6] 停止并删除容器..."

cd ~/qsm

# 停止容器
docker compose down 2>/dev/null || docker-compose down 2>/dev/null

echo "✓ 容器已停止"

echo ""
echo "[2/6] 删除旧镜像..."

# 删除旧的镜像
docker images qsm-media-center -q | xargs -r docker rmi -f 2>/dev/null

echo "✓ 旧镜像已删除"

echo ""
echo "[3/6] 清理未使用的镜像..."

# 清理悬空镜像
docker image prune -f

echo "✓ 未使用的镜像已清理"

echo ""
echo "[4/6] 清理未使用的容器..."

# 清理停止的容器
docker container prune -f

echo "✓ 未使用的容器已清理"

echo ""
echo "[5/6] 清理未使用的卷..."

# 清理未使用的卷
docker volume prune -f

echo "✓ 未使用的卷已清理"

echo ""
echo "[6/6] 清理构建缓存..."

# 清理构建缓存
docker builder prune -f

echo "✓ 构建缓存已清理"

echo ""
echo "=========================================="
echo "清理完成！"
echo "=========================================="
echo ""
echo "Docker 磁盘使用情况："
docker system df

echo ""
echo "如需彻底清理所有未使用的资源，运行："
echo "  docker system prune -a --volumes"
echo ""
echo "重新构建并启动服务："
echo "  cd ~/qsm"
echo "  docker compose up -d --build"
echo ""
