"""并发场景测试"""
import pytest
import asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_concurrent_list_requests(async_client: AsyncClient):
    """测试并发列表请求"""
    tasks = [async_client.get("/api/v1/collections?page=1&limit=10") for _ in range(5)]
    responses = await asyncio.gather(*tasks)
    assert all(r.status_code == 200 for r in responses)


@pytest.mark.asyncio
async def test_concurrent_add_collections(async_client: AsyncClient):
    """测试并发添加收藏"""
    tasks = [
        async_client.post("/api/v1/collections", json={
            "tmdb_id": 10000 + i,
            "media_type": "movie",
            "title": f"并发测试{i}",
            "share_url": f"https://pan.quark.cn/s/concurrent{i}"
        })
        for i in range(3)
    ]
    responses = await asyncio.gather(*tasks)
    assert all(r.status_code == 200 for r in responses)
