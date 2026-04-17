from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.error_codes import ErrorCode


def build_runtime_settings(
    *,
    quark_transfer_cookie: str | None = "cookie=value",
    tmdb_api_key: str | None = "tmdb-key",
):
    return SimpleNamespace(
        quark_transfer_cookie=quark_transfer_cookie,
        tmdb_api_key=tmdb_api_key,
        tmdb_api_base="https://api.themoviedb.org/3",
        tmdb_image_base="https://image.tmdb.org/t/p",
        default_language="zh-CN",
        http_proxy=None,
        transfer_keep_extras=False,
        transfer_keep_subtitles=False,
        transfer_dry_run=False,
        transfer_cleanup_enabled=False,
        transfer_cleanup_delete_non_video=False,
        transfer_cleanup_delete_unselected_video=False,
        transfer_cleanup_delete_empty_dirs=False,
    )


class FakeTransferClient:
    def __init__(self, fid: str | None):
        self._fid = fid
        self.closed = False
        self.requested_paths: list[str] = []

    async def get_fid_by_path(self, path: str) -> str | None:
        self.requested_paths.append(path)
        return self._fid

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def transfer_payload():
    return {
        "link": "https://pan.quark.cn/s/share123",
        "media_type": "movie",
        "title": "流浪地球",
        "year": 2019,
        "tmdb_id": 535167,
    }


@pytest.fixture
def install_tmdb_client(monkeypatch: pytest.MonkeyPatch):
    from app.main import app

    def _install(client):
        monkeypatch.setattr(app.state, "tmdb_client", client, raising=False)

    return _install


def patch_runtime_settings(monkeypatch: pytest.MonkeyPatch, settings):
    monkeypatch.setattr("app.quark.api.routes.search.get_settings", lambda: settings)


def patch_naming_resolution(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.quark.api.routes.search.resolve_tmdb_naming_info",
        AsyncMock(
            return_value=SimpleNamespace(
                title="流浪地球",
                year=2019,
                tmdb_id=535167,
                media_type="movie",
                category="movie",
            )
        ),
    )
    monkeypatch.setattr("app.quark.api.routes.search.get_category_base_dir", lambda category: "/Movies")


@pytest.mark.asyncio
async def test_quark_transfer_returns_cookie_config_error(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    transfer_payload,
):
    patch_runtime_settings(monkeypatch, build_runtime_settings(quark_transfer_cookie=None))

    response = await async_client.post("/api/v1/quark/transfer", json=transfer_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.CONFIG_ERROR
    assert payload["error"]["field"] == "QUARK_TRANSFER_COOKIE"


@pytest.mark.asyncio
async def test_quark_transfer_returns_tmdb_config_error_when_client_missing(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    install_tmdb_client,
    transfer_payload,
):
    install_tmdb_client(None)
    patch_runtime_settings(monkeypatch, build_runtime_settings(tmdb_api_key=None))

    response = await async_client.post("/api/v1/quark/transfer", json=transfer_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.CONFIG_ERROR
    assert payload["error"]["field"] == "TMDB_API_KEY"


@pytest.mark.asyncio
async def test_quark_transfer_returns_target_dir_error_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    install_tmdb_client,
    transfer_payload,
):
    install_tmdb_client(object())
    patch_runtime_settings(monkeypatch, build_runtime_settings())
    patch_naming_resolution(monkeypatch)
    fake_client = FakeTransferClient(fid=None)
    monkeypatch.setattr("app.quark.api.routes.search.QuarkTransferClient", lambda cookie: fake_client)

    response = await async_client.post("/api/v1/quark/transfer", json=transfer_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_DIR_NOT_FOUND
    assert payload["error"]["field"] == "target_folder"
    assert payload["error"]["value"] == "/Movies/流浪地球 (2019) [tmdbid=535167]"
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_quark_transfer_returns_link_expired_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    install_tmdb_client,
    transfer_payload,
):
    install_tmdb_client(object())
    patch_runtime_settings(monkeypatch, build_runtime_settings())
    patch_naming_resolution(monkeypatch)
    fake_client = FakeTransferClient(fid="target-fid")
    monkeypatch.setattr("app.quark.api.routes.search.QuarkTransferClient", lambda cookie: fake_client)
    monkeypatch.setattr(
        "app.quark.api.routes.search.transfer_share_to_target_fid",
        AsyncMock(return_value=(False, "分享链接无效或已失效", [], "")),
    )

    response = await async_client.post("/api/v1/quark/transfer", json=transfer_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_LINK_EXPIRED
    assert payload["error"]["field"] == "link"
    assert payload["error"]["value"] == transfer_payload["link"]


@pytest.mark.asyncio
async def test_quark_transfer_returns_no_files_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    install_tmdb_client,
    transfer_payload,
):
    install_tmdb_client(object())
    patch_runtime_settings(monkeypatch, build_runtime_settings())
    patch_naming_resolution(monkeypatch)
    fake_client = FakeTransferClient(fid="target-fid")
    monkeypatch.setattr("app.quark.api.routes.search.QuarkTransferClient", lambda cookie: fake_client)
    monkeypatch.setattr(
        "app.quark.api.routes.search.transfer_share_to_target_fid",
        AsyncMock(return_value=(False, "分享链接中没有可转存的文件", [], "")),
    )

    response = await async_client.post("/api/v1/quark/transfer", json=transfer_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_NO_FILES
    assert payload["error"]["field"] == "link"
    assert payload["error"]["value"] == transfer_payload["link"]


@pytest.mark.asyncio
async def test_quark_transfer_returns_generic_transfer_failure_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    install_tmdb_client,
    transfer_payload,
):
    install_tmdb_client(object())
    patch_runtime_settings(monkeypatch, build_runtime_settings())
    patch_naming_resolution(monkeypatch)
    fake_client = FakeTransferClient(fid="target-fid")
    monkeypatch.setattr("app.quark.api.routes.search.QuarkTransferClient", lambda cookie: fake_client)
    monkeypatch.setattr(
        "app.quark.api.routes.search.transfer_share_to_target_fid",
        AsyncMock(return_value=(False, "转存失败: 空间不足", [], "task-1")),
    )

    response = await async_client.post("/api/v1/quark/transfer", json=transfer_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.TRANSFER_FAILED
    assert payload["data"]["task_id"] == "task-1"
    assert payload["error"]["field"] == "link"
    assert payload["error"]["value"] == transfer_payload["link"]
