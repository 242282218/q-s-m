from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.error_codes import ErrorCode


async def create_collection(
    async_client: AsyncClient,
    *,
    tmdb_id: int,
    title: str,
    share_url: str,
    media_type: str = "movie",
    year: int | None = 2024,
) -> int:
    response = await async_client.post(
        "/api/v1/collections",
        json={
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": title,
            "share_url": share_url,
            "year": year,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    return int(payload["data"]["id"])


@pytest.fixture
def override_collection_settings():
    from app.main import app

    def _override(cookie: str | None) -> None:
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(quark_transfer_cookie=cookie)

    yield _override
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def install_verify_single_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., tuple[list[FakeQuarkTransferClient], list[FakeCollectionVerifyService]]]:
    def _install(
        *,
        result: dict | None = None,
        error: Exception | None = None,
    ) -> tuple[list[FakeQuarkTransferClient], list[FakeCollectionVerifyService]]:
        client_instances: list[FakeQuarkTransferClient] = []
        service_instances: list[FakeCollectionVerifyService] = []

        class FakeQuarkTransferClient:
            def __init__(self, cookie: str):
                self.cookie = cookie
                self.closed = False
                client_instances.append(self)

            async def close(self):
                self.closed = True

        class FakeCollectionVerifyService:
            def __init__(self, db, client):
                self.db = db
                self.client = client
                self.calls: list[int] = []
                service_instances.append(self)

            async def verify_single(self, collection_id: int):
                self.calls.append(collection_id)
                if error is not None:
                    raise error
                assert result is not None
                return result

        monkeypatch.setattr("app.collection.routes.QuarkTransferClient", FakeQuarkTransferClient)
        monkeypatch.setattr("app.collection.routes.CollectionVerifyService", FakeCollectionVerifyService)
        return client_instances, service_instances

    return _install


@pytest.mark.asyncio
async def test_list_collections_cursor_returns_paginated_contract(
    async_client: AsyncClient,
):
    created_ids = {
        await create_collection(
            async_client,
            tmdb_id=101,
            title="Collection 1",
            share_url="https://pan.quark.cn/s/collection-1",
        ),
        await create_collection(
            async_client,
            tmdb_id=102,
            title="Collection 2",
            share_url="https://pan.quark.cn/s/collection-2",
        ),
        await create_collection(
            async_client,
            tmdb_id=103,
            title="Collection 3",
            share_url="https://pan.quark.cn/s/collection-3",
        ),
    }

    first_page = await async_client.get("/api/v1/collections/cursor", params={"limit": 2})

    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert set(first_payload) == {"code", "message", "data", "error", "request_id", "timestamp"}
    assert first_payload["code"] == 0
    assert first_payload["error"] is None
    assert len(first_payload["data"]["items"]) == 2
    assert first_payload["data"]["pagination"]["limit"] == 2
    assert first_payload["data"]["pagination"]["has_more"] is True
    assert isinstance(first_payload["data"]["pagination"]["next_cursor"], str)
    assert first_payload["data"]["pagination"]["prev_cursor"] is None
    first_page_ids = {item["id"] for item in first_payload["data"]["items"]}

    second_page = await async_client.get(
        "/api/v1/collections/cursor",
        params={"limit": 2, "cursor": first_payload["data"]["pagination"]["next_cursor"]},
    )

    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["code"] == 0
    assert len(second_payload["data"]["items"]) == 1
    assert second_payload["data"]["pagination"]["has_more"] is False
    assert second_payload["data"]["pagination"]["next_cursor"] is None
    assert isinstance(second_payload["data"]["pagination"]["prev_cursor"], str)
    second_page_ids = {item["id"] for item in second_payload["data"]["items"]}
    assert first_page_ids.isdisjoint(second_page_ids)
    assert first_page_ids | second_page_ids == created_ids


@pytest.mark.asyncio
async def test_check_links_collection_returns_results_in_input_order(
    async_client: AsyncClient,
):
    first_id = await create_collection(
        async_client,
        tmdb_id=201,
        title="Existing 1",
        share_url="https://pan.quark.cn/s/existing-1",
    )
    second_id = await create_collection(
        async_client,
        tmdb_id=202,
        title="Existing 2",
        share_url="https://pan.quark.cn/s/existing-2",
    )

    response = await async_client.post(
        "/api/v1/collections/by-links/check",
        json={
            "links": [
                "https://pan.quark.cn/s/missing-1",
                "https://pan.quark.cn/s/existing-2",
                "https://pan.quark.cn/s/existing-1",
                "https://pan.quark.cn/s/missing-2",
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["error"] is None
    assert payload["data"]["results"] == [
        {
            "link": "https://pan.quark.cn/s/missing-1",
            "collected": False,
            "id": None,
            "status": None,
        },
        {
            "link": "https://pan.quark.cn/s/existing-2",
            "collected": True,
            "id": second_id,
            "status": 0,
        },
        {
            "link": "https://pan.quark.cn/s/existing-1",
            "collected": True,
            "id": first_id,
            "status": 0,
        },
        {
            "link": "https://pan.quark.cn/s/missing-2",
            "collected": False,
            "id": None,
            "status": None,
        },
    ]


@pytest.mark.asyncio
async def test_verify_single_collection_returns_config_error_contract(
    async_client: AsyncClient,
    override_collection_settings,
):
    override_collection_settings(None)

    response = await async_client.post("/api/v1/collections/verify/7")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.CONFIG_ERROR
    assert payload["message"] == "未配置 QUARK_TRANSFER_COOKIE，无法验证收藏"
    assert payload["data"] is None
    assert payload["error"] == {
        "field": "QUARK_TRANSFER_COOKIE",
        "value": None,
        "reason": "missing runtime configuration",
        "context": None,
    }


@pytest.mark.asyncio
async def test_verify_single_collection_returns_success_payload_and_closes_client(
    async_client: AsyncClient,
    override_collection_settings,
    install_verify_single_dependencies,
):
    override_collection_settings("quark-cookie")
    clients, services = install_verify_single_dependencies(
        result={
            "collection_id": 7,
            "title": "Alien",
            "previous_status": 0,
            "current_status": 1,
            "exists": True,
            "checked_path": "/影视收藏/电影/Alien (1979) [tmdbid=348]",
            "path_source": "expected",
        }
    )

    response = await async_client.post("/api/v1/collections/verify/7")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["error"] is None
    assert payload["data"] == {
        "result": {
            "collection_id": 7,
            "title": "Alien",
            "previous_status": 0,
            "current_status": 1,
            "exists": True,
            "checked_path": "/影视收藏/电影/Alien (1979) [tmdbid=348]",
            "path_source": "expected",
        }
    }
    assert len(clients) == 1
    assert clients[0].cookie == "quark-cookie"
    assert clients[0].closed is True
    assert len(services) == 1
    assert services[0].calls == [7]


@pytest.mark.asyncio
async def test_verify_single_collection_returns_collection_not_found_contract(
    async_client: AsyncClient,
    override_collection_settings,
    install_verify_single_dependencies,
):
    override_collection_settings("quark-cookie")
    clients, services = install_verify_single_dependencies(error=ValueError("收藏不存在"))

    response = await async_client.post("/api/v1/collections/verify/999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.COLLECTION_NOT_FOUND
    assert payload["message"] == "收藏不存在"
    assert payload["data"] is None
    assert payload["error"] == {
        "field": "collection_id",
        "value": 999,
        "reason": "收藏不存在",
        "context": None,
    }
    assert len(clients) == 1
    assert clients[0].closed is True
    assert len(services) == 1
    assert services[0].calls == [999]
