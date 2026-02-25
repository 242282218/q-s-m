# Git 防卡住配置脚本
# 解决 Windows 终端执行 git diff 等命令卡住的问题

Write-Host "=== Git 防卡住配置 ===" -ForegroundColor Green

# 永久设置 git 不使用分页器
Write-Host "正在配置 git 禁用分页器..." -ForegroundColor Yellow
git config --global core.pager cat

# 验证配置
Write-Host "`n当前 git 分页器配置：" -ForegroundColor Cyan
$currentPager = git config --global core.pager
Write-Host "core.pager = $currentPager"

# 设置环境变量（当前会话）
$env:GIT_PAGER = ""

Write-Host "`n配置完成！" -ForegroundColor Green
Write-Host "现在可以正常使用 git diff、git log 等命令而不会卡住。" -ForegroundColor Green
Write-Host "`n使用方法：" -ForegroundColor Cyan
Write-Host "  git diff      # 不会卡住" -ForegroundColor White
Write-Host "  git log       # 不会卡住" -ForegroundColor White
