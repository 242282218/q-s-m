from typing import Any, Dict, Optional, Callable, Set, List
import json
import logging
import time
import asyncio
import hashlib
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """缓存级别"""
    L1_MEMORY = "l1_memory"      # 一级缓存：内存
    L2_REDIS = "l2_redis"        # 二级缓存：Redis
    L3_DISK = "l3_disk"          # 三级缓存：磁盘（预留）


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    expiry: float
    level: CacheLevel
    access_count: int = 0
    last_access: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return time.time() >= self.expiry

    def touch(self):
        """更新访问统计"""
        self.access_count += 1
        self.last_access = time.time()


class CacheBackend(ABC):
    """缓存后端抽象基类"""

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

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    async def ttl(self, key: str) -> int:
        """获取剩余 TTL（秒），-1 表示永不过期，-2 表示不存在"""
        pass


class MemoryCache(CacheBackend):
    """
    内存缓存实现（L1 缓存）

    优化记录:
    - 2024-02-24: 使用 OrderedDict 实现 LRU 淘汰策略，添加最大容量限制
    - 2024-02-28: 添加缓存空值机制防止缓存穿透，恶意查询缓存 5 分钟
    - 2026-02-28: 添加访问统计、多级缓存支持
    """

    # 空值标记对象
    _NULL_VALUE = object()
    # 恶意查询缓存 TTL（5 分钟）
    _MALICIOUS_QUERY_TTL = 300

    def __init__(
        self,
        cleanup_interval: int = 300,
        max_size: int = 1000,
        default_ttl: int = 300  # L1 默认 TTL 5 分钟
    ) -> None:
        # 优化：使用 OrderedDict 实现 LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._cleanup_interval = cleanup_interval
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        # 记录恶意查询模式
        self._suspicious_patterns: Dict[str, int] = {}
        # 统计信息
        self._hits = 0
        self._misses = 0

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
                k for k, entry in self._cache.items()
                if entry.is_expired()
            ]
            for k in expired_keys:
                del self._cache[k]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def _is_suspicious_query(self, key: str) -> bool:
        """
        检测是否为可疑查询
        规则：频繁查询但缓存未命中的 key 可能是恶意查询
        """
        # 简单策略：检查 key 是否包含常见的攻击模式
        suspicious_keywords = ['..', '<script', 'SELECT', 'UNION', 'DROP', '--', ';']
        return any(keyword.lower() in key.lower() for keyword in suspicious_keywords)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not entry.is_expired():
                    # 优化：移动到末尾表示最近使用 (LRU)
                    self._cache.move_to_end(key)
                    entry.touch()
                    self._hits += 1
                    # 如果是空值标记，返回 None（缓存穿透保护）
                    if entry.value is self._NULL_VALUE:
                        logger.debug(f"Cache hit for null value: {key}")
                        return None
                    return entry.value
                else:
                    del self._cache[key]
            self._misses += 1
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl or self._default_ttl
        async with self._lock:
            expiry = time.time() + effective_ttl

            # 优化：如果 key 已存在，先删除再添加以更新顺序
            if key in self._cache:
                del self._cache[key]

            # 优化：LRU 淘汰策略
            while len(self._cache) >= self._max_size:
                # 移除最久未使用的项
                self._cache.popitem(last=False)
                logger.debug("LRU evicted oldest cache entry")

            # 如果值为 None，使用特殊标记存储，防止缓存穿透
            if value is None:
                # 检查是否为恶意查询，如果是则使用较短的 TTL
                if self._is_suspicious_query(key):
                    expiry = time.time() + self._MALICIOUS_QUERY_TTL
                    logger.debug(f"Caching null value for suspicious key: {key}")
                else:
                    logger.debug(f"Caching null value: {key}")
                entry = CacheEntry(
                    value=self._NULL_VALUE,
                    expiry=expiry,
                    level=CacheLevel.L1_MEMORY
                )
            else:
                entry = CacheEntry(
                    value=value,
                    expiry=expiry,
                    level=CacheLevel.L1_MEMORY
                )

            self._cache[key] = entry

    async def delete(self, key: str) -> None:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    async def exists(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not entry.is_expired():
                    return True
                del self._cache[key]
            return False

    async def ttl(self, key: str) -> int:
        async with self._lock:
            if key not in self._cache:
                return -2
            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                return -2
            remaining = int(entry.expiry - time.time())
            return max(0, remaining)

    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        async with self._lock:
            now = time.time()
            total = len(self._cache)
            expired = sum(1 for entry in self._cache.values() if entry.is_expired())
            hit_rate = self._hits / max(self._hits + self._misses, 1)
            return {
                "level": "L1_MEMORY",
                "total": total,
                "expired": expired,
                "valid": total - expired,
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
            }


class RedisCache(CacheBackend):
    """
    Redis 缓存实现（L2 缓存）

    优化记录:
    - 2026-02-28: 添加连接池、重试机制、统计信息
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl: int = 3600,  # L2 默认 TTL 1 小时
        max_connections: int = 10
    ) -> None:
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._errors = 0

        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(
                redis_url,
                decode_responses=True,
                max_connections=max_connections
            )
            logger.info("Redis cache initialized")
        except ImportError:
            raise ImportError("redis package is required for Redis cache")
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            raise

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self._redis.get(key)
            if value:
                self._hits += 1
                return json.loads(value)
            self._misses += 1
            return None
        except (ConnectionError, TimeoutError) as e:
            self._errors += 1
            logger.warning(f"Redis connection error in get: {e}")
            return None
        except json.JSONDecodeError as e:
            self._errors += 1
            logger.warning(f"Redis JSON decode error: {e}")
            return None
        except Exception as e:
            self._errors += 1
            logger.error(f"Redis unexpected error in get: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl or self._default_ttl
        try:
            await self._redis.setex(key, effective_ttl, json.dumps(value))
        except (ConnectionError, TimeoutError) as e:
            self._errors += 1
            logger.warning(f"Redis connection error in set: {e}")
        except (TypeError, ValueError) as e:
            self._errors += 1
            logger.warning(f"Redis serialization error: {e}")
        except Exception as e:
            self._errors += 1
            logger.error(f"Redis unexpected error in set: {e}")

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except (ConnectionError, TimeoutError) as e:
            self._errors += 1
            logger.warning(f"Redis connection error in delete: {e}")
        except Exception as e:
            self._errors += 1
            logger.error(f"Redis unexpected error in delete: {e}")

    async def clear(self) -> None:
        try:
            await self._redis.flushdb()
            self._hits = 0
            self._misses = 0
            self._errors = 0
        except (ConnectionError, TimeoutError) as e:
            self._errors += 1
            logger.warning(f"Redis connection error in clear: {e}")
        except Exception as e:
            self._errors += 1
            logger.error(f"Redis unexpected error in clear: {e}")

    async def exists(self, key: str) -> bool:
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.warning(f"Redis exists error: {e}")
            return False

    async def ttl(self, key: str) -> int:
        try:
            return await self._redis.ttl(key)
        except Exception as e:
            logger.warning(f"Redis ttl error: {e}")
            return -2

    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        hit_rate = self._hits / max(self._hits + self._misses, 1)
        return {
            "level": "L2_REDIS",
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "hit_rate": round(hit_rate, 4),
        }


class MultiLevelCache:
    """
    多级缓存管理器（L1 内存 + L2 Redis）

    优化记录:
    - 2026-02-28: 实现多级缓存架构，支持缓存预热、批量操作
    """

    def __init__(
        self,
        l1_cache: Optional[MemoryCache] = None,
        l2_cache: Optional[RedisCache] = None,
        l1_ttl: int = 300,      # L1 默认 5 分钟
        l2_ttl: int = 3600,     # L2 默认 1 小时
    ):
        self.l1 = l1_cache
        self.l2 = l2_cache
        self.l1_ttl = l1_ttl
        self.l2_ttl = l2_ttl
        self._warmup_keys: Set[str] = set()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值，按 L1 -> L2 顺序查找

        如果 L2 有值但 L1 没有，会自动回填到 L1
        """
        # 1. 先查 L1
        if self.l1:
            value = await self.l1.get(key)
            if value is not None:
                logger.debug(f"L1 cache hit: {key}")
                return value

        # 2. 再查 L2
        if self.l2:
            value = await self.l2.get(key)
            if value is not None:
                logger.debug(f"L2 cache hit: {key}")
                # 回填到 L1
                if self.l1:
                    await self.l1.set(key, value, self.l1_ttl)
                return value

        return None

    async def set(
        self,
        key: str,
        value: Any,
        l1_ttl: Optional[int] = None,
        l2_ttl: Optional[int] = None
    ) -> None:
        """
        设置缓存值，同时写入 L1 和 L2
        """
        effective_l1_ttl = l1_ttl or self.l1_ttl
        effective_l2_ttl = l2_ttl or self.l2_ttl

        # 写入 L1
        if self.l1:
            await self.l1.set(key, value, effective_l1_ttl)

        # 写入 L2
        if self.l2:
            await self.l2.set(key, value, effective_l2_ttl)

    async def delete(self, key: str) -> None:
        """删除缓存值，同时从 L1 和 L2 删除"""
        if self.l1:
            await self.l1.delete(key)
        if self.l2:
            await self.l2.delete(key)

    async def clear(self) -> None:
        """清空所有缓存"""
        if self.l1:
            await self.l1.clear()
        if self.l2:
            await self.l2.clear()
        self._warmup_keys.clear()

    async def exists(self, key: str) -> bool:
        """检查 key 是否存在"""
        if self.l1 and await self.l1.exists(key):
            return True
        if self.l2 and await self.l2.exists(key):
            return True
        return False

    async def ttl(self, key: str) -> int:
        """获取剩余 TTL"""
        # 优先返回 L1 的 TTL
        if self.l1:
            ttl = await self.l1.ttl(key)
            if ttl > 0:
                return ttl
        # 再查 L2
        if self.l2:
            return await self.l2.ttl(key)
        return -2

    async def get_many(self, keys: list) -> Dict[str, Any]:
        """
        批量获取缓存值

        优化：使用 asyncio.gather 并行获取
        """
        async def get_one(key: str) -> tuple:
            value = await self.get(key)
            return (key, value)

        results_list = await asyncio.gather(*[get_one(k) for k in keys])

        results = {}
        for key, value in results_list:
            if value is not None:
                results[key] = value
        return results

    async def set_many(
        self,
        items: Dict[str, Any],
        l1_ttl: Optional[int] = None,
        l2_ttl: Optional[int] = None
    ) -> None:
        """
        批量设置缓存值

        优化：使用 asyncio.gather 并行执行
        """
        await asyncio.gather(*[
            self.set(key, value, l1_ttl, l2_ttl)
            for key, value in items.items()
        ])

    async def warmup(self, keys: List[str], fetch_func: Callable[[List[str]], Dict[str, Any]]) -> None:
        """
        缓存预热

        Args:
            keys: 需要预热的 key 列表
            fetch_func: 获取数据的函数，接收 key 列表，返回 {key: value} 字典
        """
        if not keys:
            return

        async with self._lock:
            # 过滤掉已在预热列表中的 key
            new_keys = [k for k in keys if k not in self._warmup_keys]
            if not new_keys:
                return

            # 添加到预热列表
            self._warmup_keys.update(new_keys)

        try:
            # 获取数据
            data = await fetch_func(new_keys)

            # 写入缓存
            await self.set_many(data)

            logger.info(f"Cache warmup completed: {len(data)} items")
        except Exception as e:
            logger.error(f"Cache warmup failed: {e}")
        finally:
            async with self._lock:
                self._warmup_keys.difference_update(new_keys)

    async def get_stats(self) -> Dict[str, Any]:
        """获取多级缓存统计信息"""
        stats = {
            "multi_level": True,
            "l1_ttl": self.l1_ttl,
            "l2_ttl": self.l2_ttl,
        }

        if self.l1:
            stats["l1"] = await self.l1.get_stats()
        if self.l2:
            stats["l2"] = await self.l2.get_stats()

        # 计算总体命中率
        total_hits = 0
        total_misses = 0
        if self.l1:
            l1_stats = await self.l1.get_stats()
            total_hits += l1_stats.get("hits", 0)
            total_misses += l1_stats.get("misses", 0)
        if self.l2:
            l2_stats = await self.l2.get_stats()
            total_hits += l2_stats.get("hits", 0)
            total_misses += l2_stats.get("misses", 0)

        stats["total_hits"] = total_hits
        stats["total_misses"] = total_misses
        stats["overall_hit_rate"] = round(total_hits / max(total_hits + total_misses, 1), 4)

        return stats


class CacheManager:
    """
    缓存管理器（兼容旧版本接口）

    优化记录:
    - 2024-02-24: 添加缓存统计、批量操作支持
    - 2026-02-28: 升级为多级缓存架构
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.cache_enabled
        self.ttl = settings.cache_ttl
        self._backend: Optional[MultiLevelCache] = None

        if self.enabled:
            # 初始化 L1 内存缓存
            l1_cache = MemoryCache(
                max_size=1000,
                default_ttl=300,  # L1: 5 分钟
            )

            # 初始化 L2 Redis 缓存（如果配置）
            l2_cache = None
            if settings.cache_type == "redis":
                try:
                    l2_cache = RedisCache(
                        settings.redis_url,
                        default_ttl=3600,  # L2: 1 小时
                    )
                    logger.info("Redis L2 cache enabled")
                except Exception as e:
                    logger.warning(f"Failed to initialize Redis cache: {e}")

            # 创建多级缓存
            self._backend = MultiLevelCache(
                l1_cache=l1_cache,
                l2_cache=l2_cache,
                l1_ttl=300,
                l2_ttl=settings.cache_ttl,
            )

    def start_cleanup(self) -> None:
        if self.enabled and self._backend and self._backend.l1:
            self._backend.l1.start_cleanup_task()
            logger.info("Started memory cache cleanup task")

    async def stop_cleanup(self) -> None:
        if self.enabled and self._backend and self._backend.l1:
            await self._backend.l1.stop_cleanup_task()
            logger.info("Stopped memory cache cleanup task")

    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled or not self._backend:
            return None
        return await self._backend.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not self.enabled or not self._backend:
            return
        # 兼容旧接口：ttl 作为 L2 的 TTL，L1 使用默认 5 分钟
        await self._backend.set(key, value, l2_ttl=ttl or self.ttl)

    async def delete(self, key: str) -> None:
        if not self.enabled or not self._backend:
            return
        await self._backend.delete(key)

    async def clear(self) -> None:
        if not self.enabled or not self._backend:
            return
        await self._backend.clear()

    async def get_stats(self) -> Optional[Dict[str, Any]]:
        """获取缓存统计信息"""
        if not self.enabled or not self._backend:
            return None
        return await self._backend.get_stats()

    async def get_many(self, keys: list) -> Dict[str, Any]:
        """
        批量获取缓存值

        优化：使用 asyncio.gather 并行获取，减少网络往返
        """
        if not self.enabled or not self._backend:
            return {}
        return await self._backend.get_many(keys)

    async def set_many(self, items: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """
        批量设置缓存值

        优化：使用 asyncio.gather 并行执行，减少多次网络往返
        """
        if not self.enabled or not self._backend:
            return
        await self._backend.set_many(items, l2_ttl=ttl or self.ttl)

    async def warmup(self, keys: List[str], fetch_func: Callable[[List[str]], Dict[str, Any]]) -> None:
        """缓存预热"""
        if not self.enabled or not self._backend:
            return
        await self._backend.warmup(keys, fetch_func)


_cache_manager: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def generate_cache_key(prefix: str, **kwargs) -> str:
    """生成缓存 key（确保一致性）"""
    key_parts = [prefix]
    for k, v in sorted(kwargs.items()):
        # 标准化值：None -> "null", bool -> "true"/"false"
        if v is None:
            normalized = "null"
        elif isinstance(v, bool):
            normalized = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            normalized = ",".join(str(x) for x in v)
        elif isinstance(v, dict):
            normalized = generate_hash_key("", v).split(":")[-1]
        else:
            normalized = str(v)
        key_parts.append(f"{k}:{normalized}")
    return ":".join(key_parts)


def generate_hash_key(prefix: str, data: Any) -> str:
    """使用哈希生成缓存 key（用于大数据）"""
    data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    hash_value = hashlib.md5(data_str.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_value}"
