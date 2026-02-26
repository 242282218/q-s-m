# 旧页面下线与路由迁移清单（Jinja -> Vue SPA）

## 1. 迁移目标
- 后端页面入口从 Jinja 模板切换为 `frontend/dist/index.html`。
- `/api/*` REST 与 SSE 接口保持不变。
- 老链接访问不返回 404，统一回落到 Vue 路由。

## 2. 路由映射
1. `/` -> Vue SPA 入口（默认重定向到 `/collections`）
2. `/collection` -> `/collections`（兼容旧收藏页路径）
3. `/collections` -> Vue 收藏页
4. `/search` -> Vue 搜索页
5. `/settings` -> Vue 设置页
6. `/movie/{item_id}` -> `/search?mode=tmdb&tmdb_id={item_id}&media_type=movie`
7. `/tv/{item_id}` -> `/search?mode=tmdb&tmdb_id={item_id}&media_type=tv`
8. `/person/{person_id}` -> `/search`（保底兼容）

## 3. 已下线项
- 后端不再注册 Jinja 页面路由：
  - `home_router`
  - `settings_router`（HTML 页面）
- `settings.py` 仅保留 API 路由：`POST /api/settings/update`

## 4. 前端资源服务策略
1. 静态资源优先从 `frontend/dist/assets` 挂载到 `/assets`
2. 前端入口文件：`frontend/dist/index.html`
3. 如果 dist 不存在：
   - 页面请求返回 `503`
   - 错误信息包含预期路径，便于定位构建缺失

## 5. 回归测试清单
1. 构建前端
   - `cd frontend && npm run build`
2. 启动后端后验证页面入口
   - `GET /` 返回 HTML
   - `GET /collections` 返回 HTML
   - `GET /collection` 返回 HTML
   - `GET /search` 返回 HTML
   - `GET /settings` 返回 HTML
3. 验证 legacy 深链
   - `GET /movie/27205` 返回 HTML（由前端重定向到搜索页）
   - `GET /tv/1399` 返回 HTML（由前端重定向到搜索页）
4. 验证 API 不回归
   - `GET /api/health` 响应结构为 `code/message/data`
   - `GET /api/collection/list?page=1&limit=20` 含 `data.items + data.pagination`
   - `POST /api/transfer/rename` SSE event data 为 `code/message/data`
5. 验证前端关键交互
   - 收藏页分页/删除/转存/验证/重命名日志
   - 搜索页按 TMDB 和标题检索、收藏、保存
   - 设置页保存配置成功

## 6. 发布注意事项
1. 部署时必须包含 `frontend/dist`。
2. 容器部署建议设置（可选）：
   - `FRONTEND_DIST_DIR=/app/frontend/dist`
3. 上线后第一轮观察项：
   - `/assets/*` 访问命中率
   - `/api/*` 错误率是否异常上升
   - 页面 404/503 日志

