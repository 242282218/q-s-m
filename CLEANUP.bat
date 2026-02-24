@echo off
REM QSM Media Center - 清理垃圾文件脚本（Windows）

echo ==========================================
echo   QSM Media Center - 清理垃圾文件
echo ==========================================
echo.

set /p confirm="确定要清理所有垃圾文件吗？(y/n): "
if /i not "%confirm%"=="y" (
    echo 已取消清理
    pause
    exit /b 0
)

echo.
echo [1/8] 清理 Python 缓存文件...

REM 清理 __pycache__ 目录
for /d /r . %%d in (__pycache__) do @(
    if exist "%%d" (
        echo 删除: %%d
        rd /s /q "%%d"
    )
)

REM 清理 *.pyc 文件
for /r . %%f in (*.pyc) do @(
    if exist "%%f" (
        echo 删除: %%f
        del /f /q "%%f"
    )
)

REM 清理 *.pyo 文件
for /r . %%f in (*.pyo) do @(
    if exist "%%f" (
        echo 删除: %%f
        del /f /q "%%f"
    )
)

echo.
echo [2/8] 清理虚拟环境...

if exist "venv" (
    echo 删除: venv\
    rd /s /q venv
)

if exist "env" (
    echo 删除: env\
    rd /s /q env
)

if exist ".venv" (
    echo 删除: .venv\
    rd /s /q .venv
)

echo.
echo [3/8] 清理数据库文件...

if exist "backend\data\qsm.db" (
    echo 删除: backend\data\qsm.db
    del /f /q backend\data\qsm.db
)

for /r backend\data %%f in (*.db *.sqlite *.sqlite3) do @(
    if exist "%%f" (
        echo 删除: %%f
        del /f /q "%%f"
    )
)

echo.
echo [4/8] 清理日志文件...

if exist "logs" (
    echo 删除: logs\
    rd /s /q logs
)

for /r . %%f in (*.log *.err *.out) do @(
    if exist "%%f" (
        echo 删除: %%f
        del /f /q "%%f"
    )
)

echo.
echo [5/8] 清理临时文件...

for /r . %%f in (*.tmp *.temp *.cache) do @(
    if exist "%%f" (
        echo 删除: %%f
        del /f /q "%%f"
    )
)

echo.
echo [6/8] 清理 IDE 配置...

if exist ".vscode" (
    echo 删除: .vscode\
    rd /s /q .vscode
)

if exist ".idea" (
    echo 删除: .idea\
    rd /s /q .idea
)

for /r . %%f in (*.swp *.swo *~) do @(
    if exist "%%f" (
        echo 删除: %%f
        del /f /q "%%f"
    )
)

echo.
echo [7/8] 清理 AI 工具配置...

if exist ".ai" (
    echo 删除: .ai\
    rd /s /q .ai
)

if exist ".trae" (
    echo 删除: .trae\
    rd /s /q .trae
)

echo.
echo [8/8] 清理其他垃圾...

if exist ".DS_Store" (
    echo 删除: .DS_Store
    del /f /q .DS_Store
)

if exist "Thumbs.db" (
    echo 删除: Thumbs.db
    del /f /q Thumbs.db
)

echo.
echo ==========================================
echo 清理完成！
echo ==========================================
echo.
echo 已清理的文件类型：
echo   - Python 缓存文件（__pycache__、*.pyc、*.pyo）
echo   - 虚拟环境（venv/、env/、.venv/）
echo   - 数据库文件（*.db、*.sqlite）
echo   - 日志文件（*.log、*.err、*.out）
echo   - 临时文件（*.tmp、*.temp、*.cache）
echo   - IDE 配置（.vscode/、.idea/）
echo   - AI 工具配置（.ai/、.trae/）
echo   - 其他垃圾（.DS_Store、Thumbs.db）
echo.
echo 注意：.env 文件已保留（包含敏感信息）
echo.

pause
