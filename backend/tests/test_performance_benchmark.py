"""
性能基准测试套件
测试优化后系统的各项性能指标
"""
import asyncio
import time
import json
import statistics
import tracemalloc
import psutil
import aiohttp
import pytest
from typing import Dict, List, Any, Tuple
from app.middleware.rate_limit import RateLimiter
from app.quark.core.cache import MemoryCache, CacheManager
from app.db.session import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
pytestmark = pytest.mark.performance


class PerformanceTester:
    """性能测试器"""
    
    def __init__(self, base_url: str = "http://localhost:7799"):
        self.base_url = base_url
        self.results: Dict[str, Any] = {}
    
    def record_result(self, test_name: str, result: Dict[str, Any]):
        """记录测试结果"""
        self.results[test_name] = result
        logger.info(f"✓ {test_name}: {result}")
    
    async def test_rate_limiter_performance(self):
        """测试限流中间件性能"""
        logger.info("\n=== 测试限流中间件性能 ===")
        
        limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)
        
        # 测试 1: 正常请求性能
        start = time.perf_counter()
        allowed_count = 0
        
        for i in range(1000):
            allowed, _ = limiter.is_allowed(f"test_ip_{i % 100}")
            if allowed:
                allowed_count += 1
        
        duration = time.perf_counter() - start
        ops_per_second = 1000 / duration
        
        self.record_result("rate_limiter_throughput", {
            "total_requests": 1000,
            "allowed_count": allowed_count,
            "duration_seconds": round(duration, 3),
            "ops_per_second": round(ops_per_second, 2),
            "evaluation": "优秀" if ops_per_second > 10000 else "良好" if ops_per_second > 5000 else "一般"
        })
        
        # 测试 2: 内存使用
        tracemalloc.start()
        for i in range(10000):
            limiter.is_allowed(f"memory_test_ip_{i}")
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        self.record_result("rate_limiter_memory", {
            "current_memory_kb": round(current / 1024, 2),
            "peak_memory_kb": round(peak / 1024, 2),
            "evaluation": "优秀" if peak < 1024 * 1024 else "良好" if peak < 5 * 1024 * 1024 else "需优化"
        })
        
        # 测试 3: 清理功能
        start = time.perf_counter()
        limiter.cleanup_inactive_keys(inactive_seconds=0)
        cleanup_duration = time.perf_counter() - start
        
        self.record_result("rate_limiter_cleanup", {
            "cleanup_duration_ms": round(cleanup_duration * 1000, 2),
            "evaluation": "优秀" if cleanup_duration < 0.01 else "良好"
        })
    
    async def test_cache_performance(self):
        """测试缓存性能"""
        logger.info("\n=== 测试缓存性能 ===")
        
        cache = MemoryCache(cleanup_interval=300, max_size=1000)
        
        # 测试 1: 写入性能
        start = time.perf_counter()
        for i in range(1000):
            await cache.set(f"key_{i}", {"data": f"value_{i}" * 100}, ttl=300)
        
        duration = time.perf_counter() - start
        writes_per_second = 1000 / duration
        
        self.record_result("cache_write_throughput", {
            "total_writes": 1000,
            "duration_seconds": round(duration, 3),
            "writes_per_second": round(writes_per_second, 2),
            "evaluation": "优秀" if writes_per_second > 5000 else "良好" if writes_per_second > 2000 else "一般"
        })
        
        # 测试 2: 读取性能
        start = time.perf_counter()
        hits = 0
        for i in range(1000):
            result = await cache.get(f"key_{i}")
            if result:
                hits += 1
        
        duration = time.perf_counter() - start
        reads_per_second = 1000 / duration
        hit_rate = hits / 1000 * 100
        
        self.record_result("cache_read_throughput", {
            "total_reads": 1000,
            "hits": hits,
            "hit_rate_percent": round(hit_rate, 2),
            "duration_seconds": round(duration, 3),
            "reads_per_second": round(reads_per_second, 2),
            "evaluation": "优秀" if reads_per_second > 10000 else "良好" if reads_per_second > 5000 else "一般"
        })
        
        # 测试 3: LRU 淘汰
        start = time.perf_counter()
        for i in range(1000, 2000):
            await cache.set(f"key_{i}", {"data": f"value_{i}"}, ttl=300)
        
        duration = time.perf_counter() - start
        stats = await cache.get_stats()
        
        self.record_result("cache_lru_eviction", {
            "total_items_after": stats["total"],
            "max_size": stats["max_size"],
            "eviction_occurred": stats["total"] == stats["max_size"],
            "duration_seconds": round(duration, 3),
            "evaluation": "优秀" if stats["total"] == stats["max_size"] else "失败"
        })
        
        # 测试 4: 内存使用
        tracemalloc.start()
        for i in range(5000):
            await cache.set(f"memory_key_{i}", {"data": "x" * 1000}, ttl=300)
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        self.record_result("cache_memory_usage", {
            "current_memory_kb": round(current / 1024, 2),
            "peak_memory_kb": round(peak / 1024, 2),
            "peak_memory_mb": round(peak / 1024 / 1024, 2),
            "evaluation": "优秀" if peak < 10 * 1024 * 1024 else "良好" if peak < 50 * 1024 * 1024 else "需优化"
        })
    
    async def test_database_query_performance(self):
        """测试数据库查询性能"""
        logger.info("\n=== 测试数据库查询性能 ===")
        
        db = SessionLocal()
        
        try:
            # 测试 1: 简单查询
            start = time.perf_counter()
            for i in range(100):
                db.execute(text("SELECT 1")).fetchone()
            
            duration = time.perf_counter() - start
            avg_query_time = (duration / 100) * 1000
            
            self.record_result("db_simple_query", {
                "total_queries": 100,
                "duration_seconds": round(duration, 3),
                "avg_query_time_ms": round(avg_query_time, 3),
                "evaluation": "优秀" if avg_query_time < 1 else "良好" if avg_query_time < 5 else "一般"
            })
            
            # 测试 2: 复杂查询（如果有数据）
            start = time.perf_counter()
            result = db.execute(
                text("SELECT COUNT(*) FROM collections")
            ).fetchone()
            
            duration = time.perf_counter() - start
            collection_count = result[0] if result else 0
            
            self.record_result("db_collection_count_query", {
                "collection_count": collection_count,
                "query_time_ms": round(duration * 1000, 3),
                "evaluation": "优秀" if duration < 0.01 else "良好" if duration < 0.1 else "一般"
            })
            
        finally:
            db.close()
    
    async def test_api_endpoints(self):
        """测试 API 端点性能"""
        logger.info("\n=== 测试 API 端点性能 ===")
        
        async with aiohttp.ClientSession() as session:
            try:
                # 测试 1: 健康检查
                start = time.perf_counter()
                async with session.get(f"{self.base_url}/api/v1/health") as resp:
                    duration = time.perf_counter() - start
                    status = resp.status
                    
                    self.record_result("api_health_check", {
                        "status_code": status,
                        "response_time_ms": round(duration * 1000, 2),
                        "evaluation": "优秀" if duration < 0.1 else "良好" if duration < 0.5 else "一般"
                    })
            except aiohttp.ClientConnectorError:
                self.record_result("api_health_check", {
                    "status_code": None,
                    "response_time_ms": None,
                    "evaluation": "skipped",
                    "reason": f"benchmark server unavailable at {self.base_url}",
                })
                self.record_result("api_concurrent_requests", {
                    "concurrent_count": 10,
                    "total_duration_seconds": None,
                    "avg_response_time_ms": None,
                    "min_response_time_ms": None,
                    "max_response_time_ms": None,
                    "success_rate_percent": 0,
                    "evaluation": "skipped",
                    "reason": f"benchmark server unavailable at {self.base_url}",
                })
                return
            
            # 测试 2: 并发请求测试
            async def make_request(endpoint: str) -> Tuple[float, int]:
                start = time.perf_counter()
                try:
                    async with session.get(f"{self.base_url}{endpoint}") as resp:
                        duration = time.perf_counter() - start
                        return duration, resp.status
                except Exception as e:
                    duration = time.perf_counter() - start
                    return duration, 0
            
            # 10 个并发请求
            endpoints = ["/api/v1/health"] * 10
            tasks = [make_request(ep) for ep in endpoints]
            
            start = time.perf_counter()
            results = await asyncio.gather(*tasks)
            total_duration = time.perf_counter() - start
            
            response_times = [r[0] for r in results]
            success_count = sum(1 for r in results if r[1] == 200)
            
            self.record_result("api_concurrent_requests", {
                "concurrent_count": 10,
                "total_duration_seconds": round(total_duration, 3),
                "avg_response_time_ms": round(statistics.mean(response_times) * 1000, 2),
                "min_response_time_ms": round(min(response_times) * 1000, 2),
                "max_response_time_ms": round(max(response_times) * 1000, 2),
                "success_rate_percent": round(success_count / len(results) * 100, 2),
                "evaluation": "优秀" if success_count == 10 else "良好" if success_count >= 8 else "需优化"
            })
    
    async def test_memory_leak(self):
        """测试内存泄漏（长时间运行）"""
        logger.info("\n=== 测试内存泄漏 ===")
        
        process = psutil.Process()
        
        # 初始内存
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        # 模拟长时间运行（100 次迭代）
        cache = MemoryCache()
        limiter = RateLimiter()
        
        for i in range(100):
            await cache.set(f"test_{i}", {"data": "x" * 1000}, ttl=60)
            await cache.get(f"test_{i}")
            limiter.is_allowed(f"ip_{i}")
            
            if i % 20 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                logger.info(f"  迭代 {i}: 内存使用 {current_memory:.2f} MB")
        
        # 最终内存
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory
        
        self.record_result("memory_leak_test", {
            "initial_memory_mb": round(initial_memory, 2),
            "final_memory_mb": round(final_memory, 2),
            "memory_increase_mb": round(memory_increase, 2),
            "memory_increase_percent": round(memory_increase / initial_memory * 100, 2),
            "evaluation": "优秀" if memory_increase < 10 else "良好" if memory_increase < 50 else "可能存在泄漏"
        })
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("\n" + "="*60)
        logger.info("开始性能基准测试")
        logger.info("="*60)
        
        await self.test_rate_limiter_performance()
        await self.test_cache_performance()
        await self.test_database_query_performance()
        await self.test_api_endpoints()
        await self.test_memory_leak()
        
        logger.info("\n" + "="*60)
        logger.info("性能测试完成")
        logger.info("="*60)
        
        return self.results


async def run_performance_tests():
    """运行性能测试"""
    tester = PerformanceTester()
    results = await tester.run_all_tests()
    return results


def test_performance_benchmark():
    """性能基准测试主测试"""
    results = asyncio.run(run_performance_tests())
    
    # 打印汇总
    print("\n\n" + "="*60)
    print("性能测试汇总")
    print("="*60)
    
    for test_name, result in results.items():
        print(f"\n{test_name}:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    
    # 保存结果
    with open("performance_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到 performance_results.json")
    
    # 验证关键指标
    assert results["rate_limiter_throughput"]["ops_per_second"] > 1000, "限流器性能不达标"
    assert results["cache_write_throughput"]["writes_per_second"] > 1000, "缓存写入性能不达标"
    assert results["cache_read_throughput"]["reads_per_second"] > 1000, "缓存读取性能不达标"


if __name__ == "__main__":
    test_performance_benchmark()
