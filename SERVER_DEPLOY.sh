#!/bin/bash

# QSM Media Center - 服务器部署脚本
# 用途：自动化部署 QSM Media Center 到服务器

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  QSM Media Center - 服务器部署脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}请使用 root 用户运行此脚本${NC}"
    echo "使用命令: sudo $0"
    exit 1
fi

# 配置变量
PROJECT_DIR="/root/qsm"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"
SERVICE_PORT=7809
SERVICE_NAME="qsm-media-center"

echo -e "${GREEN}[1/10] 检查系统环境...${NC}"

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 未安装，正在安装...${NC}"
    apt update
    apt install -y python3 python3-pip python3-venv python3-full
else
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    echo -e "${GREEN}Python3 已安装: $PYTHON_VERSION${NC}"
fi

# 检查 pip3
if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}pip3 未安装，正在安装...${NC}"
    apt install -y python3-pip
fi

echo -e "${GREEN}[2/10] 创建项目目录...${NC}"
mkdir -p "$PROJECT_DIR"
mkdir -p "$BACKEND_DIR/data"
mkdir -p "$BACKEND_DIR/logs"

echo -e "${GREEN}[3/10] 检查必要文件...${NC}"

# 检查必要文件是否存在
REQUIRED_FILES=(
    "$BACKEND_DIR/app/main.py"
    "$BACKEND_DIR/app/config.py"
    "$BACKEND_DIR/requirements.txt"
    "$BACKEND_DIR/.env.example"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}错误: 缺少必要文件 $file${NC}"
        echo "请确保已上传所有必需文件"
        exit 1
    fi
done

echo -e "${GREEN}所有必要文件检查通过${NC}"

echo -e "${GREEN}[4/10] 创建虚拟环境...${NC}"

# 删除旧的虚拟环境（如果存在）
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}删除旧的虚拟环境...${NC}"
    rm -rf "$VENV_DIR"
fi

# 创建新的虚拟环境
python3 -m venv "$VENV_DIR"

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

echo -e "${GREEN}虚拟环境创建成功${NC}"

echo -e "${GREEN}[5/10] 升级 pip...${NC}"
pip install --upgrade pip

echo -e "${GREEN}[6/10] 安装 Python 依赖...${NC}"

# 安装依赖
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    pip install -r "$BACKEND_DIR/requirements.txt"
    echo -e "${GREEN}Python 依赖安装完成${NC}"
else
    echo -e "${RED}错误: requirements.txt 不存在${NC}"
    exit 1
fi

echo -e "${GREEN}[7/10] 配置环境变量...${NC}"

# 检查 .env 文件
if [ ! -f "$BACKEND_DIR/.env" ]; then
    if [ -f "$BACKEND_DIR/.env.example" ]; then
        cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
        echo -e "${YELLOW}已创建 .env 文件（从 .env.example 复制）${NC}"
        echo -e "${YELLOW}请编辑 $BACKEND_DIR/.env 文件，填入您的配置${NC}"
        echo ""
        echo "需要配置的变量："
        echo "  - TMDB_API_KEY: TMDB API 密钥"
        echo "  - QUARK_TRANSFER_COOKIE: 夸克网盘 Cookie"
        echo ""
        echo "编辑命令: nano $BACKEND_DIR/.env"
        echo ""
        read -p "按 Enter 继续，或 Ctrl+C 取消..."
    else
        echo -e "${RED}错误: .env.example 不存在${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}.env 文件已存在${NC}"
fi

echo -e "${GREEN}[8/10] 创建 systemd 服务...${NC}"

# 创建 systemd 服务文件
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=QSM Media Center
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port $SERVICE_PORT --reload
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd
systemctl daemon-reload

echo -e "${GREEN}systemd 服务创建完成${NC}"

echo -e "${GREEN}[9/10] 配置防火墙...${NC}"

# 检查 ufw 是否安装
if command -v ufw &> /dev/null; then
    echo -e "${YELLOW}配置防火墙规则...${NC}"
    ufw allow $SERVICE_PORT/tcp 2>/dev/null || true
    echo -e "${GREEN}防火墙规则已添加${NC}"
else
    echo -e "${YELLOW}ufw 未安装，跳过防火墙配置${NC}"
fi

echo -e "${GREEN}[10/10] 启动服务...${NC}"

# 启动服务
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# 等待服务启动
sleep 3

# 检查服务状态
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✓ 服务启动成功！${NC}"
else
    echo -e "${RED}✗ 服务启动失败${NC}"
    echo "查看日志: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "=========================================="
echo ""
echo "服务信息："
echo "  服务名称: $SERVICE_NAME"
echo "  服务端口: $SERVICE_PORT"
echo "  项目目录: $PROJECT_DIR"
echo "  后端目录: $BACKEND_DIR"
echo ""
echo "访问地址："
echo "  本地: http://localhost:$SERVICE_PORT"
echo "  外部: http://$(curl -s ifconfig.me):$SERVICE_PORT"
echo ""
echo "常用命令："
echo "  查看状态: systemctl status $SERVICE_NAME"
echo "  查看日志: journalctl -u $SERVICE_NAME -f"
echo "  重启服务: systemctl restart $SERVICE_NAME"
echo "  停止服务: systemctl stop $SERVICE_NAME"
echo ""
echo "配置文件："
echo "  环境变量: $BACKEND_DIR/.env"
echo "  服务配置: /etc/systemd/system/$SERVICE_NAME.service"
echo ""
echo "=========================================="
