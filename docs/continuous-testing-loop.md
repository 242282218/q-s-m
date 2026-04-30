# 持续测试与优化循环（多模块）

## 1. 模块清单

1. `backend`：FastAPI API、SSE、收藏/转存/重命名、Quark/TMDB 集成、DB 与中间件。
2. `frontend`：Vue3 页面与组件、HTTP/SSE 客户端、缓存与设置交互。
3. `tests/performance`：仓库级性能基准脚本。
4. `ops/backup`：SQLite 备份与恢复脚本。
5. `storage`：运行期数据与日志目录。
6. `movie-wall`：子项目样例（独立 backend/frontend 测试）。

## 2. 默认任务矩阵

默认定义在 `ops/continuous/tasks.default.json`：

1. `backend_pytest`：`backend-agent` 下执行 `python -m pytest -m "not performance"`。
2. `frontend_lint_check`：`frontend-agent` 下执行只读 `pnpm run lint:check`。
3. `frontend_format_check`：`frontend-agent` 下执行只读 `pnpm run format:check`。
4. `frontend_vitest`：`frontend-agent` 下执行 `pnpm run test:coverage`，默认同时锁 coverage 阈值。
5. `frontend_build`：`frontend-agent` 下执行 `pnpm build`。
6. `performance_benchmark`：`performance-agent` 下执行 `python ../tests/performance/benchmark.py --transfer-concurrency 5 --output-json --output-path storage/logs/continuous/performance/latest.json --fail-on-threshold-breach`。

## 3. 运行方式

单轮验证：

```bash
python ops/continuous/continuous_runner.py --max-iterations 1
```

持续循环（默认不停止）：

```bash
python ops/continuous/continuous_runner.py --interval 60
```

并行执行（示例：3 个 worker）：

```bash
python ops/continuous/continuous_runner.py --interval 60 --max-workers 3
```

失败即停：

```bash
python ops/continuous/continuous_runner.py --stop-on-failure
```

说明：

1. `--max-workers` 默认 `1`（串行）；当前默认任务已按 `backend-agent` / `frontend-agent` / `performance-agent` 分 lane，同一 agent 串行、跨 agent 并发，报告中任务顺序仍按任务定义顺序输出。
2. 当 `--stop-on-failure` 与 `--max-workers > 1` 同时设置时，会自动回退为单 worker，保证 fail-fast 行为可预测。
3. `--stop-on-failure` 触发后，当前失败任务之后的任务会在报告中标记为 `skipped`（`exit_code=125`），便于区分“未执行”与“任务缺失”。
4. `--max-iterations` 表示当前进程最多执行的轮数；即使 `latest.json` 已有更大迭代号，也会按本次设置执行完整轮次。
5. 单任务执行出现未捕获内部异常时，runner 会将该任务标记为失败（`exit_code=70`）并继续写出本轮报告，避免整轮中断丢失上下文。
6. 并行模式下如果某条 agent lane 在执行中途出现未捕获异常，runner 会保留该 lane 已完成任务的真实结果，并把当前任务及后续未执行任务统一回填为失败（`exit_code=70`）。
7. 如果某条 agent lane 在 `future.result()` 聚合阶段直接抛出未捕获异常，runner 仍会把该 lane 中尚未写入结果的任务统一回填为失败（`exit_code=70`），保证 iteration report 不丢任务。
8. 如果聚合阶段拿到的 lane 结果集不完整，runner 会保留已返回的合法任务结果，并把缺失任务回填为失败（`exit_code=70`）；如果结果索引出现重复或落到其他 lane，则按 lane 级错误处理并回填该 lane。
9. 任务文件 schema 要求：`enabled` 必须是布尔值，`name/module/cwd` 必须为非空字符串，`command` 必须是“由非空字符串组成”的数组，且同一文件内任务名不可重复；违反时会直接报错并指出 `tasks[index]` 定位。
10. 运行参数约束：`interval` 必须为非负数；`max-iterations` 必须为非负整数；`tail-lines`、`default-timeout`、`max-workers` 必须为正整数；非法值会在加载任务前直接 fail-fast。
11. 参数校验失败时，runner 会输出 `Invalid runtime arguments: ...` 到标准错误并以退出码 `1` 结束。
12. 多个已更新的 runner 共享同一 `log_dir` 时，会先通过锁保护的 iteration 计数器保留唯一编号，避免只依赖 `latest.json`/历史文件推断而发生并发撞号。
13. 默认前端 lane 使用只读 lint/format gate，不会在持续循环里自动改写工作区。
14. 默认 performance lane 是独立 opt-in benchmark；backend 默认 pytest 不再重复跑重型 benchmark。

## 4. 仓库级 CI 质量门

`.github/workflows/quality-gates.yml` 在 `pull_request`、`push(main)` 和手工触发时执行三条仓库级质量门：

1. `backend` job：安装 `backend/requirements-dev.lock.txt`，执行 `python -m pytest tests -q -m "not performance"`。
2. `docker` job：直接构建仓库根目录 `Dockerfile`（`linux/amd64`），然后实际启动容器并探测 `/api/v1/health/live` 与 `/api/v1/health/ready`，提前暴露 Dockerfile、entrypoint、健康探针和环境变量接线的部署回归。
3. `frontend` job：安装 `frontend/pnpm-lock.yaml` 对应依赖，执行 `lint:check`、`format:check`、`test:coverage`、`build`，并上传 `coverage-summary.json` artifact。

设计原则：

1. 不直接在 CI 里跑 `continuous_runner`，而是拆成后端、Docker、前端三个独立 job，保证失败定位更直接。
2. 对外推荐的 Docker 部署路径必须在 PR 阶段就被验证，而不是等合入 `main` 后才在发布链路暴露镜像构建失败。
3. CI 复用相同的 backend/frontend 默认门禁，并额外补一条 Docker 构建 + 启动 smoke 校验，减少“本地主逻辑过了，但推荐部署路径在远端才爆炸”的漂移。
4. performance benchmark 继续留在本地持续优化闭环或手工触发场景，避免每次 PR 都付出不稳定的重成本。

## 5. 结果产物

每轮生成：

1. `storage/logs/continuous/iteration-*.json`
2. `storage/logs/continuous/latest.json`

报告包含：

1. 任务状态、耗时、退出码
2. 标准输出/错误输出尾部
3. 自动提取的优化建议

## 6. 性能基线（限流）

`tests/performance/benchmark.py` 新增了内存/Redis 限流吞吐测试，支持：

```bash
# 默认（内存限流 + 缓存 + DB + transfer concurrency=5）
python ../tests/performance/benchmark.py --output-json --transfer-concurrency 5

# 包含 Redis 限流（Redis 不可用时标记 skipped，不会假失败）
python ../tests/performance/benchmark.py --output-json --transfer-concurrency 5 --include-redis-rate-limit
```

关键参数：

1. `--rate-limit-requests`：限流吞吐压测总请求数（默认 `3000`）。
2. `--rate-limit-keys`：压测 key 基数（默认 `256`）。
3. `--redis-url`：Redis 地址，默认读取 `REDIS_URL`。
4. `--output-path`：JSON 输出路径，默认仓库根目录 `performance_results.json`。
5. `--transfer-concurrency`：并发调度 benchmark 的并发档位；默认 continuous lane 固定为 `5`。

阈值说明（当前脚本内置）：

1. 并发调度吞吐阈值按 `--transfer-concurrency` 线性缩放，目标值约为 `concurrency / 0.1s`，优秀/良好阈值分别取目标值的 90% / 75%。
2. 内存限流吞吐：`>=100000 ops/s` 为“优秀”，`>=40000 ops/s` 为“良好”。
3. Redis 限流吞吐：`>=2000 ops/s` 为“优秀”，`>=800 ops/s` 为“良好”。

## 7. 下一轮优化重点

1. `backend/app/quark/core/*`：补网络异常、限流、重试与缓存一致性场景，优先真实外部依赖失败边界。
2. `backend/app/middleware/rate_limit.py`：继续补 Redis 故障冷却、恢复与代理头组合场景的回归。
3. `frontend/src/api/index.ts` 与 `frontend/src/shared/lib/http.ts`：继续压低当前剩余低覆盖分支。
4. `docs/*`：持续复审默认门禁文档是否和 `tasks.default.json`、GitHub Actions 现状一致。

## 8. 近期新增回归点

1. `frontend` 默认门禁已覆盖 `lint:check`、`format:check`、`test:coverage`、`build`，并通过真实 bootstrap/router smoke 和核心页面 focused tests 锁住主路径。
2. `backend` 默认 pytest 已排除 opt-in `performance` marker，重型 benchmark 改由独立 lane 执行，避免持续闭环重复跑 5s+ 基准。
3. `ops/backup/*` 新增 `backend/tests/test_backup_scripts.py`，锁住数据库备份、schema 导出、同名 `settings.env` 联合恢复、pre-restore 快照与运行时路径覆盖语义。
