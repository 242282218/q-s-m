"""SSE 流式响应测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rename_sse_stream(async_client: AsyncClient):
    """测试重命名SSE流"""
    async with async_client.stream("POST", "/api/v1/transfers/1/rename") as response:
        assert response.status_code in [200, 401, 404]
        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_verify_sse_stream(async_client: AsyncClient):
    """测试验证SSE流"""
    async with async_client.stream("POST", "/api/v1/collections/verify") as response:
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_batch_transfer_sse(async_client: AsyncClient):
    """测试批量转存SSE流"""
    items = [{"collection_id": 1, "auto_rename": False}]
    async with async_client.stream("POST", "/api/v1/transfers/batch/sse", json={"items": items}) as response:
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/event-stream")
