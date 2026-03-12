# 开源整理说明

本目录当前保留的是适合公开仓库发布的核心代码与配置。运行时数据、真实密钥和本地工具目录仍应保持在版本控制之外。

## 已整理内容
- 根目录基础文件：`README.md`、`.gitignore`、`.env.example`、`Dockerfile`、`docker-compose.yml`
- 后端运行代码：`backend/app/`
- 后端测试与基础配置：`backend/tests/`、`backend/requirements.txt`、`backend/pytest.ini`
- 前端运行代码：`frontend/src/`
- 前端构建配置：`frontend/package.json`、`frontend/pnpm-lock.yaml`、`frontend/vite.config.ts`、`frontend/tsconfig*.json`
- 运维辅助：`ops/backup/`

## 有意不包含的本地文件
- 私密配置：任意 `.env`
- 运行时数据：`storage/`、`backend/data/`、数据库文件、日志文件
- 构建产物：`frontend/dist/`
- 依赖目录：`frontend/node_modules/`
- 本地工具目录：`.codex/`、`.claude/`、`.trae/`、`.vscode/`
- 缓存目录：`.pytest_cache/`、`__pycache__/`

## 开源前仍建议确认
1. 补充正式 `LICENSE`
2. 复核 `README.md` 是否仍包含仅本地可用的信息
3. 检查文档是否包含敏感链接、账号、路径
4. 如果要对外发布，优先用当前根目录结构，不再回退旧的 `movie-wall/` 布局
