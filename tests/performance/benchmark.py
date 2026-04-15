"""性能基准测试。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal, get_query_stats, reset_query_stats
from app.middleware.rate_limit import RateLimiter, RedisRateLimiter
from app.quark.core.cache import MemoryCache


def _now() -> float:
    return time.perf_counter()


def _safe_ops(total: int, duration: float) -> float:
    if duration <= 0:
        return 0.0
    return total / duration


def _evaluate(value: float, excellent: float, good: float) -> str:
    if value >= excellent:
        return "优秀"
    if value >= good:
        return "良好"
    return "需关注"


def _round(value: float) -> float:
    return round(value, 3)


def _resolve_output_path(path_value: str) -> Path:
    output_path = Path(path_value)
    if output_path.is_absolute():
        return output_path
    return (REPO_ROOT / output_path).resolve()


async def benchmark_cache_operations(iterations: int = 1000) -> dict[str, Any]:
    cache = MemoryCache(max_size=1000)

    started = _now()
    for index in range(iterations):
        await cache.set(f"key_{index}", f"value_{index}", ttl=300)
    write_duration = _now() - started

    started = _now()
    for index in range(iterations):
        await cache.get(f"key_{index}")
    read_duration = _now() - started

    stats = await cache.get_stats()
    write_ops = _safe_ops(iterations, write_duration)
    read_ops = _safe_ops(iterations, read_duration)

    return {
        "iterations": iterations,
        "write_time_seconds": _round(write_duration),
        "read_time_seconds": _round(read_duration),
        "write_ops_per_sec": round(write_ops, 2),
        "read_ops_per_sec": round(read_ops, 2),
        "hit_rate": stats["hit_rate"],
        "write_evaluation": _evaluate(write_ops, excellent=200_000, good=80_000),
        "read_evaluation": _evaluate(read_ops, excellent=300_000, good=120_000),
    }


async def benchmark_concurrent_transfers(concurrency: int = 5) -> dict[str, Any]:
    async def mock_transfer() -> bool:
        await asyncio.sleep(0.1)
        return True

    started = _now()
    tasks = [mock_transfer() for _ in range(20)]
    await asyncio.gather(*tasks)
    elapsed = _now() - started
    throughput = _safe_ops(20, elapsed)

    return {
        "concurrency": concurrency,
        "total_tasks": 20,
        "elapsed_time_seconds": _round(elapsed),
        "throughput_tasks_per_sec": round(throughput, 2),
        "evaluation": _evaluate(throughput, excellent=180, good=120),
    }


def benchmark_db_queries(query_count: int = 100) -> dict[str, Any]:
    reset_query_stats()

    db = SessionLocal()
    started = _now()
    try:
        for _ in range(query_count):
            db.execute(text("SELECT 1"))
    finally:
        db.close()

    elapsed = _now() - started
    stats = get_query_stats()
    throughput = _safe_ops(stats["total_queries"], elapsed)

    return {
        "queries": stats["total_queries"],
        "elapsed_time_seconds": _round(elapsed),
        "avg_query_time_seconds": stats["avg_time"],
        "queries_per_sec": round(throughput, 2),
        "evaluation": _evaluate(throughput, excellent=10_000, good=4_000),
    }


async def benchmark_memory_rate_limiter(
    total_requests: int = 3000,
    unique_keys: int = 256,
) -> dict[str, Any]:
    limiter = RateLimiter(
        requests_per_minute=max(total_requests * 2, 1000),
        requests_per_hour=max(total_requests * 4, 5000),
    )

    allowed_count = 0
    started = _now()
    for index in range(total_requests):
        key = f"bench_mem_{index % max(1, unique_keys)}"
        allowed, _ = limiter.is_allowed(key)
        if allowed:
            allowed_count += 1
    elapsed = _now() - started
    throughput = _safe_ops(total_requests, elapsed)

    return {
        "total_requests": total_requests,
        "unique_keys": unique_keys,
        "allowed_count": allowed_count,
        "rejected_count": total_requests - allowed_count,
        "elapsed_time_seconds": _round(elapsed),
        "ops_per_sec": round(throughput, 2),
        "evaluation": _evaluate(throughput, excellent=100_000, good=40_000),
    }


async def _cleanup_redis_benchmark_keys(redis_client: Any, prefix: str) -> None:
    cursor: int | str = 0
    while True:
        cursor, keys = await redis_client.scan(
            cursor=cursor,
            match=f"{prefix}*",
            count=1000,
        )
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0 or cursor == "0":
            break


async def _close_redis_client(redis_client: Any) -> None:
    if hasattr(redis_client, "aclose"):
        await redis_client.aclose()
        return
    await redis_client.close()


async def benchmark_redis_rate_limiter(
    redis_url: str,
    total_requests: int = 3000,
    unique_keys: int = 256,
) -> dict[str, Any]:
    try:
        import redis.asyncio as redis
    except Exception as exc:
        return {
            "evaluation": "skipped",
            "reason": f"redis package unavailable: {exc}",
            "redis_url": redis_url,
        }

    redis_client = redis.from_url(redis_url, decode_responses=True)
    prefix = f"qsm:bench:rate_limit:{int(time.time())}"

    try:
        await redis_client.ping()
    except Exception as exc:
        await _close_redis_client(redis_client)
        return {
            "evaluation": "skipped",
            "reason": f"redis unavailable: {type(exc).__name__}: {exc}",
            "redis_url": redis_url,
        }

    limiter = RedisRateLimiter(
        redis_url=redis_url,
        requests_per_minute=max(total_requests * 2, 1000),
        requests_per_hour=max(total_requests * 4, 5000),
        key_prefix=prefix,
        redis_client=redis_client,
    )

    try:
        await _cleanup_redis_benchmark_keys(redis_client, prefix)
        allowed_count = 0
        started = _now()
        for index in range(total_requests):
            key = f"bench_redis_{index % max(1, unique_keys)}"
            allowed, _ = await limiter.is_allowed(key)
            if allowed:
                allowed_count += 1
        elapsed = _now() - started
        throughput = _safe_ops(total_requests, elapsed)
        return {
            "total_requests": total_requests,
            "unique_keys": unique_keys,
            "allowed_count": allowed_count,
            "rejected_count": total_requests - allowed_count,
            "elapsed_time_seconds": _round(elapsed),
            "ops_per_sec": round(throughput, 2),
            "evaluation": _evaluate(throughput, excellent=2_000, good=800),
            "redis_url": redis_url,
        }
    finally:
        await _cleanup_redis_benchmark_keys(redis_client, prefix)
        await _close_redis_client(redis_client)


def _persist_results(results: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QSM performance benchmarks")
    parser.add_argument("--cache-iterations", type=int, default=1000)
    parser.add_argument("--db-queries", type=int, default=100)
    parser.add_argument("--rate-limit-requests", type=int, default=3000)
    parser.add_argument("--rate-limit-keys", type=int, default=256)
    parser.add_argument("--include-redis-rate-limit", action="store_true")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
    )
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--output-path", default="performance_results.json")
    return parser.parse_args()


async def run_all_benchmarks(args: argparse.Namespace) -> dict[str, Any]:
    print("=== 性能基准测试 ===\n")

    print("1. 缓存操作测试")
    cache_result = await benchmark_cache_operations(args.cache_iterations)
    print(f"   写入: {cache_result['write_ops_per_sec']} ops/s ({cache_result['write_evaluation']})")
    print(f"   读取: {cache_result['read_ops_per_sec']} ops/s ({cache_result['read_evaluation']})\n")

    print("2. 并发调度测试")
    transfer_result = await benchmark_concurrent_transfers(5)
    print(
        "   吞吐量: "
        f"{transfer_result['throughput_tasks_per_sec']} tasks/s ({transfer_result['evaluation']})\n"
    )

    print("3. 数据库查询测试")
    db_result = benchmark_db_queries(args.db_queries)
    print(f"   查询速度: {db_result['queries_per_sec']} queries/s ({db_result['evaluation']})")
    print(f"   平均耗时: {db_result['avg_query_time_seconds']}s\n")

    print("4. 内存限流吞吐测试")
    mem_rate_limit_result = await benchmark_memory_rate_limiter(
        total_requests=args.rate_limit_requests,
        unique_keys=args.rate_limit_keys,
    )
    print(
        "   吞吐量: "
        f"{mem_rate_limit_result['ops_per_sec']} ops/s ({mem_rate_limit_result['evaluation']})\n"
    )

    redis_rate_limit_result: dict[str, Any]
    if args.include_redis_rate_limit:
        print("5. Redis 限流吞吐测试")
        redis_rate_limit_result = await benchmark_redis_rate_limiter(
            redis_url=args.redis_url,
            total_requests=args.rate_limit_requests,
            unique_keys=args.rate_limit_keys,
        )
        if redis_rate_limit_result.get("evaluation") == "skipped":
            print(f"   跳过: {redis_rate_limit_result['reason']}\n")
        else:
            print(
                "   吞吐量: "
                f"{redis_rate_limit_result['ops_per_sec']} ops/s "
                f"({redis_rate_limit_result['evaluation']})\n"
            )
    else:
        redis_rate_limit_result = {
            "evaluation": "skipped",
            "reason": "set --include-redis-rate-limit to enable",
            "redis_url": args.redis_url,
        }

    results = {
        "cache": cache_result,
        "transfer": transfer_result,
        "database": db_result,
        "rate_limiter_memory": mem_rate_limit_result,
        "rate_limiter_redis": redis_rate_limit_result,
    }

    if args.output_json:
        output_path = _resolve_output_path(args.output_path)
        _persist_results(results, output_path)
        print(f"结果已写入: {output_path}")

    return results


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks(parse_args()))
