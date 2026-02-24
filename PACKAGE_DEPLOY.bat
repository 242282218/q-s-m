@echo off
REM QSM Media Center - Windows 打包脚本
REM 用途：打包必要文件用于服务器部署

echo ==========================================
echo   QSM Media Center - 文件打包脚本
echo ==========================================
echo.

REM 设置变量
set PROJECT_DIR=%~dp0
set DEPLOY_FILE=qsm-deploy.tar.gz

echo [1/5] 检查必要文件...

REM 检查必要文件
if not exist "%PROJECT_DIR%backend\app\main.py" (
    echo 错误: backend\app\main.py 不存在
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%backend\requirements.txt" (
    echo 错误: backend\requirements.txt 不存在
    pause
    exit /b 1
)

echo 所有必要文件检查通过

echo.
echo [2/5] 清理旧的部署包...

if exist "%DEPLOY_FILE%" (
    echo 删除旧的部署包: %DEPLOY_FILE%
    del /F /Q "%DEPLOY_FILE%"
)

echo.
echo [3/5] 打包必要文件...

REM 使用 tar 命令打包（Windows 10+ 内置）
tar -czf "%DEPLOY_FILE%" ^
    backend\app ^
    backend\requirements.txt ^
    backend\.env.example ^
    backend\start_server.py ^
    Dockerfile ^
    docker-compose.yml ^
    README.md ^
    SERVER_DEPLOY.sh ^
    SERVER_DEPLOY_GUIDE.md

if %ERRORLEVEL% NEQ 0 (
    echo 错误: 打包失败
    pause
    exit /b 1
)

echo 打包完成: %DEPLOY_FILE%

echo.
echo [4/5] 显示文件信息...

for %%I in ("%DEPLOY_FILE%") do (
    echo 文件名: %%~nxI
    echo 文件大小: %%~zI 字节
)

echo.
echo [5/5] 部署说明...

echo ==========================================
echo 打包完成！
echo ==========================================
echo.
echo 部署包位置: %PROJECT_DIR%%DEPLOY_FILE%
echo.
echo 下一步操作：
echo 1. 将 %DEPLOY_FILE% 上传到服务器
echo 2. 在服务器上执行以下命令：
echo    tar -xzf qsm-deploy.tar.gz
echo    chmod +x SERVER_DEPLOY.sh
echo    ./SERVER_DEPLOY.sh
echo.
echo 上传命令示例：
echo    scp qsm-deploy.tar.gz root@103.149.91.156:~/
echo.
echo ==========================================

pause
