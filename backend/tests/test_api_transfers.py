"""Transfers API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_validate_link(async_client: AsyncClient):
    """测试验证分享链接"""
    response = await async_client.post(
        "/api/v1/transfers/validate",
        json={"share_url": "https://pan.quark.cn/s/test123"}
    )
    assert response.status_code in [200, 401]
    data = response.json()
    assert "code" in data
    if response.status_code == 200:
        assert "data" in data
        assert "valid" in data["data"]


@pytest.mark.asyncio
async def test_transfer_execute(async_client: AsyncClient):
    """测试执行转存"""
    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/test", "auto_rename": False}
    )
    assert response.status_code in [200, 401, 404]


@pytest.mark.asyncio
async def test_batch_transfer(async_client: AsyncClient):
    """测试批量转存"""
    items = [{"collection_id": i, "auto_rename": False} for i in range(1, 3)]
    response = await async_client.post("/api/v1/transfers/batch", json={"items": items})
    assert response.status_code in [200, 401]
    if response.status_code == 200:
        data = response.json()["data"]
        assert "total" in data
        assert "success_count" in data
