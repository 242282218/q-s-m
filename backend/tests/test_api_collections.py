"""Collections API 集成测试"""
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session


@pytest.fixture
def test_collection_data():
    return {
        "tmdb_id": 12345,
        "media_type": "movie",
        "title": "测试电影",
        "share_url": "https://pan.quark.cn/s/test123",
        "year": 2024,
    }


@pytest.mark.asyncio
async def test_add_collection(async_client: AsyncClient, test_collection_data):
    """测试添加收藏"""
    response = await async_client.post("/api/v1/collections", json=test_collection_data)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "data" in data
    assert data["data"]["created"] is True


@pytest.mark.asyncio
async def test_list_collections(async_client: AsyncClient):
    """测试获取收藏列表"""
    response = await async_client.get("/api/v1/collections?page=1&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "data" in data
    assert "items" in data["data"]
    assert "pagination" in data["data"]


@pytest.mark.asyncio
async def test_get_collection(async_client: AsyncClient, test_collection_data):
    """测试获取单个收藏"""
    add_resp = await async_client.post("/api/v1/collections", json=test_collection_data)
    collection_id = add_resp.json()["data"]["id"]

    response = await async_client.get(f"/api/v1/collections/{collection_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["id"] == collection_id


@pytest.mark.asyncio
async def test_delete_collection(async_client: AsyncClient, test_collection_data):
    """测试删除收藏"""
    add_resp = await async_client.post("/api/v1/collections", json=test_collection_data)
    collection_id = add_resp.json()["data"]["id"]

    response = await async_client.delete(f"/api/v1/collections/{collection_id}")
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_batch_add_collections(async_client: AsyncClient):
    """测试批量添加收藏"""
    items = [
        {"tmdb_id": i, "media_type": "movie", "title": f"电影{i}", "share_url": f"https://pan.quark.cn/s/test{i}"}
        for i in range(1, 4)
    ]
    response = await async_client.post("/api/v1/collections/batch", json={"items": items})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 3
