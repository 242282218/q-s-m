"""
性能基准测试
"""
import asyncio
import time
from typing import List

from app.quark.core.cache import MemoryCache, generate_cache_key
from app.db.session import SessionLocal, get_query_stats, reset_query_stats


async def benchmark_cache_operations(iterations: int = 1000):
    """缓存操作基准测试"""
    cache = MemoryCache(max_size=1000)

    # 写入测试
    start = time.time()
    for i in range(iterations):
        await cache.set(f"key_{i}", f"value_{i}", ttl=300)
    write_time = time.time() - start

    # 读取测试
    start = time.time()
    for i in range(iterations):
        await cache.get(f"key_{i}")
    read_time = time.time() - start

    stats = await cache.get_stats()

    return {
        "iterations": iterations,
        "write_time": round(write_time, 3),
        "read_time": round(read_time, 3),
        "write_ops_per_sec": round(iterations / write_time, 2),
        "read_ops_per_sec": round(iterations / read_time, 2),
        "hit_rate": stats["hit_rate"]
    }


async def benchmark_concurrent_transfers(concurrency: int = 5):
    """并发转存基准测试"""
    from app.quark.services.transfer_service import TransferService

    service = TransferService(max_concurrent=concurrency)

    async def mock_transfer():
        await asyncio.sleep(0.1)  # 模拟转存操作
        return True

    start = time.time()
    tasks = [mock_transfer() for _ in range(20)]
    await asyncio.gather(*tasks)
    elapsed = time.time() - start

    return {
        "concurrency": concurrency,
        "total_tasks": 20,
        "elapsed_time": round(elapsed, 3),
        "throughput": round(20 / elapsed, 2)
    }


def benchmark_db_queries():
    """数据库查询基准测试"""
    reset_query_stats()

    db = SessionLocal()
    start = time.time()

    # 执行测试查询
    for _ in range(100):
        db.execute("SELECT 1")

    elapsed = time.time() - start
    stats = get_query_stats()

    db.close()

    return {
        "queries": stats["total_queries"],
        "elapsed_time": round(elapsed, 3),
        "avg_query_time": stats["avg_time"],
        "queries_per_sec": round(stats["total_queries"] / elapsed, 2)
    }


async def run_all_benchmarks():
    """运行所有基准测试"""
    print("=== 性能基准测试 ===\n")

    print("1. 缓存操作测试")
    cache_result = await benchmark_cache_operations(1000)
    print(f"   写入: {cache_result['write_ops_per_sec']} ops/s")
    print(f"   读取: {cache_result['read_ops_per_sec']} ops/s\n")

    print("2. 并发转存测试")
    transfer_result = await benchmark_concurrent_transfers(5)
    print(f"   吞吐量: {transfer_result['throughput']} tasks/s\n")

    print("3. 数据库查询测试")
    db_result = benchmark_db_queries()
    print(f"   查询速度: {db_result['queries_per_sec']} queries/s")
    print(f"   平均耗时: {db_result['avg_query_time']}s\n")

    return {
        "cache": cache_result,
        "transfer": transfer_result,
        "database": db_result
    }


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
