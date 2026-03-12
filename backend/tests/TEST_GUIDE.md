# 测试运行指南

## 后端测试

### 安装依赖
```bash
cd backend
pip install pytest pytest-asyncio httpx
```

### 运行所有测试
```bash
pytest
```

### 运行特定测试
```bash
# Collections API测试
pytest tests/test_api_collections.py

# Transfers API测试
pytest tests/test_api_transfers.py

# SSE流测试
pytest tests/test_sse_streams.py

# 并发测试
pytest tests/test_concurrent_operations.py
```

### 生成覆盖率报告
```bash
pip install pytest-cov
pytest --cov=app --cov-report=html
```

## 前端测试

### 运行测试
```bash
cd frontend
npm test
```

### 运行HTTP层测试
```bash
npm test http.test.ts
```

### 生成覆盖率
```bash
npm test -- --coverage
```
