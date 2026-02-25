from typing import Any, Dict, Optional
import json
import logging
import time
import asyncio
from abc import ABC, abstractmethod
from collections import OrderedDict

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass


class MemoryCache(CacheBackend):
    """
    内存缓存实现
    
    优化记录:
    - 2024-02-24: 使用 OrderedDict 实现 LRU 淘汰策略，添加最大容量限制
    """
    
    def __init__(self, cleanup_interval: int = 300, max_size: int = 1000) -> None:
        # 优化: 使用 OrderedDict 实现 LRU
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._cleanup_interval = cleanup_interval
        self._max_size = max_size
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

    def start_cleanup_task(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._running = True
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def stop_cleanup_task(self) -> None:
        self._running = False
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self) -> None:
        """定期清理过期缓存"""
        while self._running:
            await asyncio.sleep(self._cleanup_interval)
            if not self._running:
                break
            try:
                await self._cleanup_expired()
            except Exception as e:
                logger.warning(f"Cache cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        """清理过期条目"""
        async with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (_, expiry) in self._cache.items() 
                if now >= expiry
            ]
            for k in expired_keys:
                del self._cache[k]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    # 优化: 移动到末尾表示最近使用 (LRU)
                    self._cache.move_to_end(key)
                    return value
                else:
                    del self._cache[key]
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            expiry = time.time() + ttl
            
            # 优化: 如果 key 已存在，先删除再添加以更新顺序
            if key in self._cache:
                del self._cache[key]
            
            # 优化: LRU 淘汰策略
            while len(self._cache) >= self._max_size:
                # 移除最久未使用的项
                self._cache.popitem(last=False)
                logger.debug("LRU evicted oldest cache entry")
            
            self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        async with self._lock:
            now = time.time()
            total = len(self._cache)
            expired = sum(1 for _, expiry in self._cache.values() if now >= expiry)
            return {
                "total": total,
                "expired": expired,
                "valid": total - expired,
                "max_size": self._max_size,
            }


class RedisCache(CacheBackend):
    def __init__(self, redis_url: str) -> None:
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(redis_url, decode_responses=True)
        except ImportError:
            raise ImportError("redis package is required for Redis cache")

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self._redis.get(key)
            if value:
                return json.loads(value)
            return None
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis connection error in get: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Redis JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Redis unexpected error in get: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self._redis.setex(key, ttl, json.dumps(value))
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis connection error in set: {e}")
        except (TypeError, ValueError) as e:
            logger.warning(f"Redis serialization error: {e}")
        except Exception as e:
            logger.error(f"Redis unexpected error in set: {e}")

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis connection error in delete: {e}")
        except Exception as e:
            logger.error(f"Redis unexpected error in delete: {e}")

    async def clear(self) -> None:
        try:
            await self._redis.flushdb()
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis connection error in clear: {e}")
        except Exception as e:
            logger.error(f"Redis unexpected error in clear: {e}")


class CacheManager:
    """
    缓存管理器
    
    优化记录:
    - 2024-02-24: 添加缓存统计、批量操作支持
    """
    
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.cache_enabled
        self.ttl = settings.cache_ttl
        self._backend: Optional[CacheBackend] = None

        if self.enabled:
            if settings.cache_type == "redis":
                try:
                    self._backend = RedisCache(settings.redis_url)
                except Exception as e:
                    logger.warning(f"Failed to initialize Redis cache, falling back to memory: {e}")
                    self._backend = MemoryCache()
            else:
                self._backend = MemoryCache()

    def start_cleanup(self) -> None:
        if self.enabled and isinstance(self._backend, MemoryCache):
            self._backend.start_cleanup_task()
            logger.info("Started memory cache cleanup task")

    async def stop_cleanup(self) -> None:
        if self.enabled and isinstance(self._backend, MemoryCache):
            await self._backend.stop_cleanup_task()
            logger.info("Stopped memory cache cleanup task")

    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled or not self._backend:
            return None
        return await self._backend.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not self.enabled or not self._backend:
            return
        await self._backend.set(key, value, ttl or self.ttl)

    async def delete(self, key: str) -> None:
        if not self.enabled or not self._backend:
            return
        await self._backend.delete(key)

    async def clear(self) -> None:
        if not self.enabled or not self._backend:
            return
        await self._backend.clear()

    async def get_stats(self) -> Optional[Dict[str, int]]:
        """获取缓存统计信息"""
        if not self.enabled or not self._backend:
            return None
        if isinstance(self._backend, MemoryCache):
            return await self._backend.get_stats()
        return None

    async def get_many(self, keys: list) -> Dict[str, Any]:
        """
        批量获取缓存值
        
        优化: 使用 asyncio.gather 并行获取，减少网络往返
        """
        if not self.enabled or not self._backend:
            return {}
        
        async def get_one(key: str) -> tuple:
            value = await self._backend.get(key)
            return (key, value)
        
        results_list = await asyncio.gather(*[get_one(k) for k in keys])
        
        results = {}
        for key, value in results_list:
            if value is not None:
                results[key] = value
        return results

    async def set_many(self, items: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """
        批量设置缓存值
        
        优化: 使用 asyncio.gather 并行执行，减少多次网络往返
        """
        if not self.enabled or not self._backend:
            return
        
        effective_ttl = ttl or self.ttl
        await asyncio.gather(*[
            self._backend.set(key, value, effective_ttl)
            for key, value in items.items()
        ])


_cache_manager: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def generate_cache_key(prefix: str, **kwargs) -> str:
    key_parts = [prefix]
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")
    return ":".join(key_parts)
