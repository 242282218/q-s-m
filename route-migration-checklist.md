# 旧页面下线与路由迁移回归验收表

> 目标：在 Vue SPA 接管入口后，逐路由确认“视觉 + 交互 + 数据契约”与旧 Jinja 页面一致，避免切换回归。  
> 范围：`/`、`/collection(s)`、`/search`、`/movie/:id`、`/tv/:id`、`/person/:id`、`/settings`。

## 1. 路由迁移对照

| 旧路由 | 旧页面实现 | 新路由实现 | 关键接口 | 验收状态 |
|---|---|---|---|---|
| `/` | `templates/home.html` | `frontend/src/pages/HomePage.vue` | `GET /api/home` | 待验收 |
| `/collection` | `templates/collection.html` + `static/js/collection.js` | `frontend/src/pages/CollectionPage.vue` | `GET /api/collection/list` 等 | 待验收 |
| `/collections` | 无（兼容入口） | `frontend/src/pages/CollectionPage.vue` | 同上 | 待验收 |
| `/search` | `templates/search.html` | `frontend/src/pages/SearchPage.vue` | `GET /api/quark/search/*` | 待验收 |
| `/movie/:item_id` | `templates/detail.html` + `static/js/detail.js` | `frontend/src/pages/DetailPage.vue` | `GET /api/tmdb/detail/{media_type}/{item_id}` | 待验收 |
| `/tv/:item_id` | `templates/detail.html` + `static/js/detail.js` | `frontend/src/pages/DetailPage.vue` | `GET /api/tmdb/detail/{media_type}/{item_id}` | 待验收 |
| `/person/:person_id` | `templates/person.html` | `frontend/src/pages/PersonPage.vue` | `GET /api/tmdb/person/{person_id}` | 待验收 |
| `/settings` | `templates/settings.html` | `frontend/src/pages/SettingsPage.vue` | `POST /api/settings/update` | 待验收 |

## 2. 逐路由回归项（可直接打勾）

### `/` 首页
- [ ] Hero 轮播可显示海报/背景图，左右切换与指示器可用。
- [ ] 分区标题、标签、海报横滑布局与旧页面一致（`content-row/posters-row/poster-card`）。
- [ ] 海报点击可进入详情页（`/movie/:id` 或 `/tv/:id`）。

### `/collection(s)` 收藏页
- [ ] 列表分页、刷新、总数显示正常。
- [ ] 卡片操作（删除/转存/重命名/验证）可用。
- [ ] 缺失海报自动回填（调用 `/api/tmdb/details`）。
- [ ] 静默校验可刷新状态徽标（已转存/已失效/网盘已删除/未转存）。

### `/search` 搜索页
- [ ] 支持 TMDB ID 与标题两种模式。
- [ ] URL 查询参数变化时自动触发查询（可回退/前进）。
- [ ] 资源卡“打开链接/收藏/保存到网盘”均可用。

### `/movie/:id` 与 `/tv/:id` 详情页
- [ ] 详情头图、标题、副标题、标签、简介显示正常。
- [ ] 演员区跳转人物页可用。
- [ ] 推荐区海报可跳转新详情页。
- [ ] 视频区点击后可内嵌播放 YouTube。
- [ ] 夸克资源区：TMDB 搜索 + 标题兜底、收藏、保存流程正常。

### `/person/:id` 人物页
- [ ] 人物头图、简介、基础信息显示正常。
- [ ] 代表作海报区可跳转详情页。
- [ ] 全部作品默认显示 10 条，`details` 折叠可展开剩余作品。

### `/settings` 设置页
- [ ] 基础配置和转存策略字段可编辑并提交。
- [ ] 保存成功/失败状态提示正常。

## 3. 旧页面下线清单（建议分两阶段）

### 阶段 A（当前）：保留旧文件，仅停止入口引用
- `backend/app/templates/home.html`
- `backend/app/templates/detail.html`
- `backend/app/templates/person.html`
- `backend/app/templates/search.html`
- `backend/app/templates/collection.html`
- `backend/app/templates/settings.html`
- `backend/app/static/js/detail.js`
- `backend/app/static/js/collection.js`

### 阶段 B（回归全通过后）：正式下线
- [ ] 从代码与文档中移除不再使用的 Jinja 页面入口说明。
- [ ] 删除未再使用的旧模板与旧页面脚本。
- [ ] 再执行一次全路由冒烟回归并记录结果。

## 4. 回归执行记录

| 日期 | 执行人 | 范围 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-02-26 |  | 全路由 |  |  |

