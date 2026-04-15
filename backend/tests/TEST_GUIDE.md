# 测试运行指南

## 后端测试

### 安装依赖
```bash
cd backend
pip install pytest pytest-asyncio httpx
```

### 运行所有测试
```bash
python -m pytest -q tests
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

# RateLimiter 自动清理 + Redis 降级回归
python -m pytest tests/test_rate_limiter_cleanup.py

# Metrics 重置统计结构回归
python -m pytest tests/test_metrics_reset.py
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
