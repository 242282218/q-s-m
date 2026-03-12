# 架构重构报告

## 重构概述

本次重构解决了以下关键架构问题：
1. TransferService 职责过重
2. 错误处理不一致
3. 缺少分布式锁机制
4. 模块依赖关系复杂

## 重构内容

### 1. 统一异常处理体系

**文件**: `backend/app/core/exceptions.py`

创建了统一的异常类层次结构：
- `QSMException` - 基础异常类
- `TransferException` - 转存异常
- `RenameException` - 重命名异常
- `CleanupException` - 清理异常
- `QuarkException` - 夸克服务异常
- `LockException` - 分布式锁异常

所有异常都包含错误码、上下文信息和详细信息。

### 2. 分布式锁机制

**文件**: `backend/app/core/distributed_lock.py`

实现了基于 Redis 的分布式锁：
- 支持阻塞/非阻塞模式
- 自动超时释放
- Redis 不可用时降级到内存锁
- 使用上下文管理器确保锁释放

### 3. 服务拆分

#### RenameService
**文件**: `backend/app/quark/services/rename_service.py`

职责：
- 重命名媒体文件
- 重组文件结构
- 收集保留的文件 FID

#### CleanupService
**文件**: `backend/app/quark/services/cleanup_service.py`

职责：
- 清理非视频文件
- 删除空目录
- 保护指定的视频文件

#### TransferService (重构后)
**文件**: `backend/app/transfer/service.py`

职责变更：
- 协调转存流程
- 调用 RenameService 和 CleanupService
- 管理数据库事务
- 使用分布式锁防止并发冲突

## 架构对比

### 重构前
```
TransferService
├── 转存逻辑
├── 重命名逻辑
├── 清理逻辑
├── SSE 事件生成
└── 数据库操作
```

### 重构后
```
TransferService (协调器)
├── RenameService (重命名)
├── CleanupService (清理)
├── DistributedLock (分布式锁)
└── 统一异常处理
```

## API 兼容性

所有 API 接口保持向后兼容，无需修改前端代码：
- `POST /transfers/validate`
- `POST /transfers/{collection_id}/execute`
- `POST /transfers/{collection_id}/rename`
- `POST /transfers/batch`
- `POST /transfers/batch/sse`

## 关键改进

1. **职责分离**: 每个服务单一职责，易于测试和维护
2. **并发安全**: 分布式锁防止多实例部署时的资源冲突
3. **错误处理**: 统一的异常体系，便于错误追踪和处理
4. **可扩展性**: 新增功能只需添加新服务，不影响现有代码

## 使用示例

### 分布式锁
```python
from app.core.distributed_lock import get_distributed_lock

lock = get_distributed_lock()
async with lock.acquire("resource_key", timeout=30):
    # 执行需要互斥的操作
    pass
```

### 异常处理
```python
from app.core.exceptions import TransferException
from app.core.error_codes import ErrorCode

raise TransferException(
    "转存失败",
    code=ErrorCode.TRANSFER_FAILED,
    details={"collection_id": 123}
)
```

## 后续优化建议

1. 为 RenameService 和 CleanupService 添加单元测试
2. 实现 Redis 连接池管理
3. 添加服务间通信的性能监控
4. 考虑使用消息队列处理长时间运行的任务
