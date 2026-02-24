# 简易部署指南 (Simple Deployment)

本指南适用于 Ubuntu 20.04+ 环境，通过 Docker 一键部署。

## 1. 准备工作

将整个项目文件夹（包含 `backend`, `Dockerfile`, `docker-compose.yml`, `deploy.sh`）上传到您的服务器。

例如：
```bash
# 在本地执行 (假设服务器 IP 为 1.2.3.4)
scp -r qsm/ root@1.2.3.4:/opt/qsm
```

## 2. 一键部署

登录服务器并运行部署脚本：

```bash
# 登录服务器
ssh root@1.2.3.4

# 进入项目目录
cd /opt/qsm

# 添加执行权限
chmod +x deploy.sh

# 运行部署脚本
./deploy.sh
```

脚本会自动：
1. 检查并安装 Docker 和 Docker Compose（如果未安装）。
2. 准备 `.env` 配置文件。
3. 构建 Docker 镜像。
4. 启动服务。

## 3. 访问与配置

部署完成后，服务将在 **8000** 端口运行。

*   **访问地址**: `http://您的服务器IP:8000`
*   **初始配置**:
    1.  访问 `http://您的服务器IP:8000/settings`。
    2.  配置 **TMDB API Key** 和 **夸克网盘 Cookie**。
    3.  保存配置。

## 4. 常用维护命令

*   **查看日志**:
    ```bash
    docker-compose logs -f
    ```

*   **重启服务**:
    ```bash
    docker-compose restart
    ```

*   **停止服务**:
    ```bash
    docker-compose down
    ```

*   **更新代码**:
    1. 上传新代码覆盖旧文件。
    2. 重新运行 `./deploy.sh`。

## 5. 常见问题

*   **端口冲突**: 如果 8000 端口被占用，请编辑 `docker-compose.yml`，修改 `ports` 部分，例如 `"8080:8000"` 将服务映射到 8080 端口。
*   **权限问题**: 如果遇到权限错误，请确保使用 `root` 用户或使用 `sudo` 运行命令。
