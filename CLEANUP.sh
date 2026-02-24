#!/bin/bash

# QSM Media Center - 清理垃圾文件脚本（Linux）

echo "=========================================="
echo "  QSM Media Center - 清理垃圾文件"
echo "=========================================="
echo ""

read -p "确定要清理所有垃圾文件吗？(y/n): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消清理"
    exit 0
fi

echo ""
echo "[1/8] 清理 Python 缓存文件..."

# 清理 __pycache__ 目录
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# 清理 *.pyc 文件
find . -type f -name "*.pyc" -delete 2>/dev/null

# 清理 *.pyo 文件
find . -type f -name "*.pyo" -delete 2>/dev/null

echo "✓ Python 缓存文件清理完成"

echo ""
echo "[2/8] 清理虚拟环境..."

# 清理虚拟环境
[ -d "venv" ] && rm -rf venv && echo "删除: venv/"
[ -d "env" ] && rm -rf env && echo "删除: env/"
[ -d ".venv" ] && rm -rf .venv && echo "删除: .venv/"

echo "✓ 虚拟环境清理完成"

echo ""
echo "[3/8] 清理数据库文件..."

# 清理数据库文件
find backend/data -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) -delete 2>/dev/null

echo "✓ 数据库文件清理完成"

echo ""
echo "[4/8] 清理日志文件..."

# 清理日志目录
[ -d "logs" ] && rm -rf logs && echo "删除: logs/"

# 清理日志文件
find . -type f \( -name "*.log" -o -name "*.err" -o -name "*.out" \) -delete 2>/dev/null

echo "✓ 日志文件清理完成"

echo ""
echo "[5/8] 清理临时文件..."

# 清理临时文件
find . -type f \( -name "*.tmp" -o -name "*.temp" -o -name "*.cache" \) -delete 2>/dev/null

echo "✓ 临时文件清理完成"

echo ""
echo "[6/8] 清理 IDE 配置..."

# 清理 IDE 配置
[ -d ".vscode" ] && rm -rf .vscode && echo "删除: .vscode/"
[ -d ".idea" ] && rm -rf .idea && echo "删除: .idea/"

# 清理编辑器临时文件
find . -type f \( -name "*.swp" -o -name "*.swo" -o -name "*~" \) -delete 2>/dev/null

echo "✓ IDE 配置清理完成"

echo ""
echo "[7/8] 清理 AI 工具配置..."

# 清理 AI 工具配置
[ -d ".ai" ] && rm -rf .ai && echo "删除: .ai/"
[ -d ".trae" ] && rm -rf .trae && echo "删除: .trae/"

echo "✓ AI 工具配置清理完成"

echo ""
echo "[8/8] 清理其他垃圾..."

# 清理系统垃圾
find . -type f -name ".DS_Store" -delete 2>/dev/null
find . -type f -name "Thumbs.db" -delete 2>/dev/null

echo "✓ 其他垃圾清理完成"

echo ""
echo "=========================================="
echo "清理完成！"
echo "=========================================="
echo ""
echo "已清理的文件类型："
echo "  - Python 缓存文件（__pycache__、*.pyc、*.pyo）"
echo "  - 虚拟环境（venv/、env/、.venv/）"
echo "  - 数据库文件（*.db、*.sqlite）"
echo "  - 日志文件（*.log、*.err、*.out）"
echo "  - 临时文件（*.tmp、*.temp、*.cache）"
echo "  - IDE 配置（.vscode/、.idea/）"
echo "  - AI 工具配置（.ai/、.trae/）"
echo "  - 其他垃圾（.DS_Store、Thumbs.db）"
echo ""
echo "注意：.env 文件已保留（包含敏感信息）"
echo ""
