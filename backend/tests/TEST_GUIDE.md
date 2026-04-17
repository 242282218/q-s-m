# 测试运行指南

## 后端测试

### 安装依赖
```bash
cd backend
pip install pytest pytest-asyncio httpx
```

### 运行所有测试
```bash
python -m pytest -q tests -m "not performance"
```

### 运行特定测试
```bash
# Collections API测试
python -m pytest tests/test_api_collections.py

# Transfers API测试
python -m pytest tests/test_api_transfers.py

# SSE流测试
python -m pytest tests/test_sse_streams.py

# 并发测试
python -m pytest tests/test_concurrent_operations.py

# 首页 Hero 缓存并发回归
python -m pytest tests/test_home_hero_cache.py

# TMDB 缓存并发/键稳定性回归
python -m pytest tests/test_tmdb_cache_behaviors.py

# 显式运行重型性能 pytest 套件（默认门禁不会包含）
python -m pytest tests/test_performance_benchmark.py -m performance

# RateLimiter 自动清理 + Redis 降级回归
python -m pytest tests/test_rate_limiter_cleanup.py

# Metrics 重置统计结构回归
python -m pytest tests/test_metrics_reset.py

# 备份/恢复脚本完整性回归
python -m pytest tests/test_backup_scripts.py
```

### 生成覆盖率报告
```bash
pip install pytest-cov
python -m pytest --cov=app --cov-report=html
```

## 前端测试

### 运行测试
```bash
cd frontend
pnpm test -- --run
```

### 运行HTTP层测试
```bash
pnpm test -- src/__tests__/http.test.ts
```

### 生成覆盖率
```bash
pnpm test -- --coverage
```

## 性能压测

在 `backend` 目录执行：

```bash
# 默认性能基线（缓存 + 并发调度 + DB + 内存限流），输出 JSON
python ../tests/performance/benchmark.py --output-json --transfer-concurrency 5

# 包含 Redis 限流吞吐压测（Redis 不可用时会标记 skipped）
python ../tests/performance/benchmark.py --output-json --transfer-concurrency 5 --include-redis-rate-limit

# 作为门禁使用：任一指标落入“需关注”时返回非零退出码
python ../tests/performance/benchmark.py --output-json --transfer-concurrency 5 --fail-on-threshold-breach

# 作为部署前强校验：Redis 不可用或跳过时直接失败
python ../tests/performance/benchmark.py --output-json --transfer-concurrency 5 --include-redis-rate-limit --fail-on-threshold-breach --require-redis
```

阈值说明：

1. 并发调度：吞吐阈值按 `--transfer-concurrency` 线性缩放，目标值约为 `concurrency / 0.1s`，优秀/良好阈值分别取该目标的 90% / 75%。
2. 内存限流：`>=100000 ops/s` 优秀，`>=40000 ops/s` 良好。
3. Redis 限流：`>=2000 ops/s` 优秀，`>=800 ops/s` 良好。

Redis 限流故障冷却：

1. 默认 `RATE_LIMIT_REDIS_FAILURE_COOLDOWN_SECONDS=30`，Redis 限流异常后 30 秒内短路到内存限流，避免每请求重试。
2. 设为 `0` 时关闭冷却策略，每次请求都会尝试 Redis 并在异常时回退内存。

反向代理限流 IP 解析：

1. 默认 `TRUST_PROXY_HEADERS=false`，限流键使用直连客户端地址。
2. 仅当部署在可信反向代理后启用 `TRUST_PROXY_HEADERS=true`，并配置精确 `TRUSTED_PROXY_IPS`。
3. `TRUSTED_PROXY_IPS` 推荐 JSON 数组（如 `["127.0.0.1","::1"]`），也兼容逗号分隔（如 `127.0.0.1,::1`）。
4. 启用后按 `X-Forwarded-For` 从右向左剥离可信代理，取首个非代理 IP；缺失时回退 `X-Real-IP`。
5. 头部中的非法 IP 或带异常格式值会被忽略并回退到连接源地址。
