# 开源整理说明

该目录用于存放**适合公开仓库发布**的项目必要文件，原项目其他本地文件保持不变。

## 已整理内容
- 根目录基础文件：`README.md`、`.gitignore`、`.env.example`、`Dockerfile`、`docker-compose.yml`
- 后端运行代码：`backend/app/`
- 后端测试与基础配置：`backend/tests/`、`requirements.txt`、`requirements.lock.txt`、`pytest.ini`、`start_server.py`、`backend/.env.example`
- 前端运行代码：`frontend/src/`
- 前端构建配置：`package.json`、`pnpm-lock.yaml`、`vite.config.ts`、`tsconfig*.json`、`eslint.config.js`、`.prettierrc`、`index.html`
- 补充文档：部分 `docs/` 文档

## 有意未包含的本地文件
- 私密配置：任何 `.env`
- 运行态数据：`backend/data/`、数据库文件、日志文件
- 构建产物：`frontend/dist/`
- 依赖目录：`frontend/node_modules/`
- 本地工具目录：`.codex/`、`.claude/`、`.trae/`、`.vscode/`
- 缓存目录：`.pytest_cache/`、`__pycache__/`、`.ruff_cache/`

## 开源前仍建议确认
1. 选择并补充正式 `LICENSE`
2. 检查 README 中是否仍包含仅本地可用的信息
3. 检查文档中是否包含敏感链接、账号、内部路径
4. 如需正式发布，可在该目录内单独初始化公开仓库
