"""Transfers API 集成测试"""
import pytest
from httpx import AsyncClient

from app.core.error_codes import ErrorCode


def patch_transfer_collection(monkeypatch: pytest.MonkeyPatch, message: str):
    async def fake_transfer_collection(self, collection_id: int, target_folder=None, auto_rename=False):
        _ = (self, collection_id, target_folder, auto_rename)
        return False, message, []

    monkeypatch.setattr(
        "app.transfer.routes.TransferService.transfer_collection",
        fake_transfer_collection,
    )


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
async def test_transfer_execute_returns_collection_not_found_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """测试转存接口会把不存在收藏映射为明确错误码"""
    patch_transfer_collection(monkeypatch, "收藏不存在")

    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/test", "auto_rename": False}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.COLLECTION_NOT_FOUND
    assert payload["error"]["field"] == "collection_id"
    assert payload["error"]["value"] == 1


@pytest.mark.asyncio
async def test_transfer_execute_returns_cookie_config_error_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """测试转存接口会把缺失 Quark Cookie 映射为配置错误"""
    patch_transfer_collection(monkeypatch, "未配置 QUARK_TRANSFER_COOKIE")

    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/test", "auto_rename": False}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.CONFIG_ERROR
    assert payload["error"]["field"] == "QUARK_TRANSFER_COOKIE"


@pytest.mark.asyncio
async def test_transfer_execute_returns_tmdb_config_error_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """测试转存接口会把缺失 TMDB 配置映射为配置错误"""
    patch_transfer_collection(monkeypatch, "未配置 TMDB_API_KEY，无法执行转存")

    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/test", "auto_rename": False}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.CONFIG_ERROR
    assert payload["error"]["field"] == "TMDB_API_KEY"


@pytest.mark.asyncio
async def test_transfer_execute_returns_timeout_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """测试转存接口会把超时映射为超时错误码"""
    patch_transfer_collection(monkeypatch, "转存超时，请稍后重试")

    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/test", "auto_rename": False}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_TIMEOUT
    assert payload["error"]["field"] == "collection_id"


@pytest.mark.asyncio
async def test_transfer_execute_returns_target_dir_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """测试转存接口会把目标目录失败映射为目录错误码"""
    patch_transfer_collection(monkeypatch, "创建目标目录失败: /mnt/media/电影")

    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/custom-target", "auto_rename": False}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_DIR_NOT_FOUND
    assert payload["error"]["field"] == "target_folder"
    assert payload["error"]["value"] == "/mnt/media/电影"


@pytest.mark.asyncio
async def test_transfer_execute_returns_no_files_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """测试转存接口会把空分享映射为无文件错误码"""
    patch_transfer_collection(monkeypatch, "分享链接中没有可转存的文件")

    response = await async_client.post(
        "/api/v1/transfers/1/execute",
        json={"target_folder": "/test", "auto_rename": False}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_NO_FILES
    assert payload["error"]["field"] == "collection_id"


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
