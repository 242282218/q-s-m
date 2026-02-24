@echo off
REM QSM Media Center - 上传到服务器脚本
REM 用途：将打包的文件上传到服务器

echo ==========================================
echo   QSM Media Center - 上传到服务器
echo ==========================================
echo.

REM 配置变量
set SERVER_HOST=103.149.91.156
set SERVER_USER=root
set DEPLOY_FILE=qsm-deploy.tar.gz
set REMOTE_DIR=~

echo 服务器信息：
echo   主机: %SERVER_HOST%
echo   用户: %SERVER_USER%
echo   文件: %DEPLOY_FILE%
echo   目录: %REMOTE_DIR%
echo.

REM 检查文件是否存在
if not exist "%DEPLOY_FILE%" (
    echo 错误: %DEPLOY_FILE% 不存在
    echo 请先运行 PACKAGE_DEPLOY.bat 打包文件
    pause
    exit /b 1
)

echo [1/3] 检查 SSH 连接...

REM 测试 SSH 连接
ssh -o ConnectTimeout=5 %SERVER_USER%@%SERVER_HOST% "echo SSH 连接成功" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 无法连接到服务器
    echo 请检查：
    echo   1. 服务器地址是否正确
    echo   2. SSH 服务是否运行
    echo   3. 网络连接是否正常
    pause
    exit /b 1
)

echo SSH 连接成功

echo.
echo [2/3] 上传文件...

REM 上传文件
scp "%DEPLOY_FILE%" %SERVER_USER%@%SERVER_HOST%:%REMOTE_DIR%/

if %ERRORLEVEL% NEQ 0 (
    echo 错误: 上传失败
    pause
    exit /b 1
)

echo 上传成功

echo.
echo [3/3] 验证文件...

REM 验证文件
ssh %SERVER_USER%@%SERVER_HOST% "ls -lh %REMOTE_DIR%/%DEPLOY_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo 警告: 无法验证文件
) else (
    echo 文件验证成功
)

echo.
echo ==========================================
echo 上传完成！
echo ==========================================
echo.
echo 下一步操作：
echo 1. SSH 登录到服务器：
echo    ssh %SERVER_USER%@%SERVER_HOST%
echo.
echo 2. 解压并部署：
echo    cd ~
echo    tar -xzf %DEPLOY_FILE%
echo    chmod +x SERVER_DEPLOY.sh
echo    ./SERVER_DEPLOY.sh
echo.
echo 或者直接执行一键部署命令：
echo    ssh %SERVER_USER%@%SERVER_HOST% "cd ~ && tar -xzf %DEPLOY_FILE% && chmod +x SERVER_DEPLOY.sh && ./SERVER_DEPLOY.sh"
echo.
echo ==========================================

pause
