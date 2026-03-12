"""
分布式锁机制（基于 Redis）
"""
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.exceptions import LockException

logger = logging.getLogger(__name__)


class DistributedLock:
    """分布式锁（Redis 实现）"""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._local_locks = {}  # 内存锁降级

    @asynccontextmanager
    async def acquire(
        self,
        key: str,
        timeout: int = 30,
        blocking: bool = True,
        blocking_timeout: Optional[int] = None
    ):
        """
        获取分布式锁

        Args:
            key: 锁键名
            timeout: 锁超时时间（秒）
            blocking: 是否阻塞等待
            blocking_timeout: 阻塞超时时间（秒）
        """
        settings = get_settings()

        # 如果 Redis 不可用，降级到内存锁
        if not settings.cache_enabled or settings.cache_type != "redis" or not self._redis:
            async with self._acquire_local_lock(key, timeout, blocking, blocking_timeout):
                yield
            return

        # Redis 分布式锁
        lock_key = f"lock:{key}"
        acquired = False

        try:
            if blocking:
                # 阻塞等待获取锁
                start_time = asyncio.get_event_loop().time()
                while True:
                    acquired = await self._try_acquire_redis_lock(lock_key, timeout)
                    if acquired:
                        break

                    if blocking_timeout:
                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed >= blocking_timeout:
                            raise LockException(f"获取锁超时: {key}")

                    await asyncio.sleep(0.1)
            else:
                # 非阻塞获取锁
                acquired = await self._try_acquire_redis_lock(lock_key, timeout)
                if not acquired:
                    raise LockException(f"无法获取锁: {key}")

            yield

        finally:
            if acquired:
                await self._release_redis_lock(lock_key)

    async def _try_acquire_redis_lock(self, key: str, timeout: int) -> bool:
        """尝试获取 Redis 锁"""
        try:
            # 使用 SET NX EX 原子操作
            result = await self._redis.set(key, "1", ex=timeout, nx=True)
            return result is True
        except Exception as e:
            logger.warning(f"Redis 锁获取失败，降级到内存锁: {e}")
            return False

    async def _release_redis_lock(self, key: str):
        """释放 Redis 锁"""
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.error(f"释放 Redis 锁失败: {e}")

    @asynccontextmanager
    async def _acquire_local_lock(
        self,
        key: str,
        timeout: int,
        blocking: bool,
        blocking_timeout: Optional[int]
    ):
        """内存锁降级方案"""
        if key not in self._local_locks:
            self._local_locks[key] = asyncio.Lock()

        lock = self._local_locks[key]

        acquired = False
        try:
            if blocking:
                if blocking_timeout:
                    await asyncio.wait_for(lock.acquire(), timeout=blocking_timeout)
                else:
                    await lock.acquire()
                acquired = True
            else:
                acquired = not lock.locked()
                if not acquired:
                    raise LockException(f"无法获取锁: {key}")
                await lock.acquire()

            yield

        finally:
            if acquired and lock.locked():
                lock.release()


# 全局锁实例
_lock_instance: Optional[DistributedLock] = None


def get_distributed_lock() -> DistributedLock:
    """获取分布式锁实例"""
    global _lock_instance
    if _lock_instance is None:
        _lock_instance = DistributedLock()
    return _lock_instance
