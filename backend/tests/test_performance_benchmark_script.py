import asyncio
import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = ROOT / "tests" / "performance" / "benchmark.py"


def load_benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "qsm_performance_benchmark",
        BENCHMARK_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_benchmark_concurrent_transfers_respects_limit(monkeypatch: pytest.MonkeyPatch):
    module = load_benchmark_module()
    original_sleep = asyncio.sleep
    active = 0
    max_active = 0

    async def fake_sleep(_delay: float) -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await original_sleep(0)
        active -= 1

    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    result = await module.benchmark_concurrent_transfers(3)

    assert result["concurrency"] == 3
    assert result["total_tasks"] == module.MIN_TRANSFER_TASKS
    assert result["expected_throughput_tasks_per_sec"] == 30.0
    assert result["excellent_threshold_tasks_per_sec"] == 27.0
    assert result["good_threshold_tasks_per_sec"] == 22.5
    assert result["evaluation"] == "优秀"
    assert max_active == 3


def test_parse_args_rejects_non_positive_transfer_concurrency(
    monkeypatch: pytest.MonkeyPatch,
):
    module = load_benchmark_module()
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark.py", "--transfer-concurrency", "0"],
    )

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 2


@pytest.mark.asyncio
async def test_run_all_benchmarks_uses_cli_transfer_concurrency(
    monkeypatch: pytest.MonkeyPatch,
):
    module = load_benchmark_module()
    seen_concurrency: list[int] = []

    async def fake_cache(iterations: int) -> dict[str, object]:
        return {
            "iterations": iterations,
            "write_time_seconds": 0.01,
            "read_time_seconds": 0.01,
            "write_ops_per_sec": 200000.0,
            "read_ops_per_sec": 300000.0,
            "hit_rate": 1.0,
            "write_evaluation": "优秀",
            "read_evaluation": "优秀",
        }

    async def fake_transfer(concurrency: int) -> dict[str, object]:
        seen_concurrency.append(concurrency)
        return {
            "concurrency": concurrency,
            "total_tasks": module.MIN_TRANSFER_TASKS,
            "elapsed_time_seconds": 0.1,
            "throughput_tasks_per_sec": 200.0,
            "evaluation": "优秀",
        }

    def fake_db(query_count: int) -> dict[str, object]:
        return {
            "queries": query_count,
            "elapsed_time_seconds": 0.01,
            "avg_query_time_seconds": 0.001,
            "queries_per_sec": 10000.0,
            "evaluation": "优秀",
        }

    async def fake_memory_rate_limit(
        total_requests: int,
        unique_keys: int,
    ) -> dict[str, object]:
        return {
            "total_requests": total_requests,
            "unique_keys": unique_keys,
            "allowed_count": total_requests,
            "rejected_count": 0,
            "elapsed_time_seconds": 0.01,
            "ops_per_sec": 100000.0,
            "evaluation": "优秀",
        }

    monkeypatch.setattr(module, "benchmark_cache_operations", fake_cache)
    monkeypatch.setattr(module, "benchmark_concurrent_transfers", fake_transfer)
    monkeypatch.setattr(module, "benchmark_db_queries", fake_db)
    monkeypatch.setattr(module, "benchmark_memory_rate_limiter", fake_memory_rate_limit)

    results = await module.run_all_benchmarks(
        Namespace(
            cache_iterations=10,
            db_queries=5,
            rate_limit_requests=20,
            rate_limit_keys=4,
            transfer_concurrency=7,
            include_redis_rate_limit=False,
            redis_url="redis://127.0.0.1:6379/0",
            output_json=False,
            output_path="ignored.json",
            fail_on_threshold_breach=False,
            require_redis=False,
        )
    )

    assert seen_concurrency == [7]
    assert results["transfer"]["concurrency"] == 7
    assert results["threshold_breaches"] == []


@pytest.mark.asyncio
async def test_run_all_benchmarks_persists_threshold_breaches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    module = load_benchmark_module()

    async def fake_cache(_iterations: int) -> dict[str, object]:
        return {
            "iterations": 10,
            "write_time_seconds": 0.01,
            "read_time_seconds": 0.01,
            "write_ops_per_sec": 200000.0,
            "read_ops_per_sec": 300000.0,
            "hit_rate": 1.0,
            "write_evaluation": "优秀",
            "read_evaluation": "优秀",
        }

    async def fake_transfer(concurrency: int) -> dict[str, object]:
        return {
            "concurrency": concurrency,
            "total_tasks": module.MIN_TRANSFER_TASKS,
            "elapsed_time_seconds": 0.1,
            "throughput_tasks_per_sec": 50.0,
            "evaluation": "需关注",
        }

    def fake_db(_query_count: int) -> dict[str, object]:
        return {
            "queries": 5,
            "elapsed_time_seconds": 0.01,
            "avg_query_time_seconds": 0.001,
            "queries_per_sec": 10000.0,
            "evaluation": "优秀",
        }

    async def fake_memory_rate_limit(
        total_requests: int,
        unique_keys: int,
    ) -> dict[str, object]:
        return {
            "total_requests": total_requests,
            "unique_keys": unique_keys,
            "allowed_count": total_requests,
            "rejected_count": 0,
            "elapsed_time_seconds": 0.01,
            "ops_per_sec": 100000.0,
            "evaluation": "优秀",
        }

    monkeypatch.setattr(module, "benchmark_cache_operations", fake_cache)
    monkeypatch.setattr(module, "benchmark_concurrent_transfers", fake_transfer)
    monkeypatch.setattr(module, "benchmark_db_queries", fake_db)
    monkeypatch.setattr(module, "benchmark_memory_rate_limiter", fake_memory_rate_limit)

    output_path = tmp_path / "performance.json"
    results = await module.run_all_benchmarks(
        Namespace(
            cache_iterations=10,
            db_queries=5,
            rate_limit_requests=20,
            rate_limit_keys=4,
            transfer_concurrency=5,
            include_redis_rate_limit=False,
            redis_url="redis://127.0.0.1:6379/0",
            output_json=True,
            output_path=str(output_path),
            fail_on_threshold_breach=False,
            require_redis=False,
        )
    )

    persisted = json.loads(output_path.read_text(encoding="utf-8"))

    assert results["threshold_breaches"] == ["transfer.throughput_tasks_per_sec"]
    assert persisted["threshold_breaches"] == ["transfer.throughput_tasks_per_sec"]
