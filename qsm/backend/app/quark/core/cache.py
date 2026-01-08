from typing import Any, Dict, Optional
import json
import time
from abc import ABC, abstractmethod

from app.config import get_settings


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
    def __init__(self):
        self._cache: Dict[str, tuple] = {}

    async def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]

    async def clear(self) -> None:
        self._cache.clear()


class RedisCache(CacheBackend):
    def __init__(self, redis_url: str):
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
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self._redis.setex(key, ttl, json.dumps(value))
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception:
            pass

    async def clear(self) -> None:
        try:
            await self._redis.flushdb()
        except Exception:
            pass


class CacheManager:
    def __init__(self):
        settings = get_settings()
        self.enabled = settings.cache_enabled
        self.ttl = settings.cache_ttl
        self._backend: Optional[CacheBackend] = None

        if self.enabled:
            if settings.cache_type == "redis":
                try:
                    self._backend = RedisCache(settings.redis_url)
                except Exception:
                    self._backend = MemoryCache()
            else:
                self._backend = MemoryCache()

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
