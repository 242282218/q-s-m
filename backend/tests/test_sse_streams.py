"""SSE 流式响应测试"""
import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.error_codes import ErrorCode


async def collect_sse_events(response) -> list[dict]:
    events: list[dict] = []
    async for line in response.aiter_lines():
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[6:]))
    return events


@pytest.fixture
def override_collection_settings():
    from app.main import app

    def _override(cookie: str | None) -> None:
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(quark_transfer_cookie=cookie)

    yield _override
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def install_transfer_service(monkeypatch: pytest.MonkeyPatch):
    def _install(
        *,
        rename_error: Exception | None = None,
        transfer_results: list[tuple[bool, str, list[dict]] | Exception] | None = None,
    ):
        instances = []
        queued_results = list(transfer_results or [])

        class FakeTransferService:
            def __init__(self, db, cookie, tmdb_client=None):
                self.db = db
                self.cookie = cookie
                self.tmdb_client = tmdb_client
                self.closed = False
                instances.append(self)

            async def rename_collection(self, collection_id: int):
                if rename_error is not None:
                    raise rename_error
                yield {
                    "type": "complete",
                    "current": 1,
                    "total": 1,
                    "percentage": 100,
                    "message": f"rename {collection_id}",
                    "level": "info",
                }

            async def transfer_collection(self, collection_id: int, target_folder=None, auto_rename=False):
                result = queued_results.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result

            async def close(self):
                self.closed = True

        monkeypatch.setattr("app.transfer.routes.TransferService", FakeTransferService)
        return instances

    return _install


@pytest.mark.asyncio
async def test_rename_sse_stream(async_client: AsyncClient):
    """测试重命名SSE流"""
    async with async_client.stream("POST", "/api/v1/transfers/1/rename") as response:
        assert response.status_code in [200, 401, 404]
        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_verify_sse_stream_returns_config_error_event(
    async_client: AsyncClient,
    override_collection_settings,
):
    """测试验证SSE流配置错误契约"""
    override_collection_settings(None)

    async with async_client.stream("POST", "/api/v1/collections/verify", json={}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = await collect_sse_events(response)

    assert len(events) == 1
    event = events[0]
    assert event["type"] == "error"
    assert event["level"] == "error"
    assert event["code"] == ErrorCode.CONFIG_ERROR
    assert event["message"] == "未配置 QUARK_TRANSFER_COOKIE，无法验证收藏"
    assert event["request_id"]
    assert event["data"] == {
        "current": 0,
        "total": 0,
        "percentage": 0,
        "message": "未配置 QUARK_TRANSFER_COOKIE，无法验证收藏",
    }


@pytest.mark.asyncio
async def test_batch_add_collections_sse_emits_progress_and_complete_summary(
    async_client: AsyncClient,
):
    """测试批量添加收藏 SSE 进度与汇总契约"""
    items = [
        {
            "tmdb_id": 301,
            "media_type": "movie",
            "title": "SSE Success",
            "share_url": "https://pan.quark.cn/s/sse-duplicate",
            "year": 2024,
        },
        {
            "tmdb_id": 302,
            "media_type": "movie",
            "title": "SSE Duplicate",
            "share_url": "https://pan.quark.cn/s/sse-duplicate",
            "year": 2025,
        },
    ]

    async with async_client.stream("POST", "/api/v1/collections/batch/sse", json={"items": items}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = await collect_sse_events(response)

    assert [event["type"] for event in events] == ["progress", "progress", "complete"]
    first_event, second_event, complete_event = events
    assert len({event["request_id"] for event in events}) == 1

    assert first_event["level"] == "info"
    assert first_event["message"] == "处理 SSE Success: 成功"
    assert first_event["data"] == {
        "current": 1,
        "total": 2,
        "percentage": 50.0,
        "success_count": 1,
        "failed_count": 0,
        "current_item": {
            "index": 0,
            "title": "SSE Success",
            "success": True,
            "id": 1,
        },
    }

    assert second_event["level"] == "warning"
    assert second_event["message"] == "处理 SSE Duplicate: 失败"
    assert second_event["data"] == {
        "current": 2,
        "total": 2,
        "percentage": 100.0,
        "success_count": 1,
        "failed_count": 1,
        "current_item": {
            "index": 1,
            "title": "SSE Duplicate",
            "success": False,
            "id": 1,
        },
    }

    assert complete_event["level"] == "info"
    assert complete_event["message"] == "批量添加完成: 成功 1, 失败 1"
    assert complete_event["data"] == {
        "total": 2,
        "success_count": 1,
        "failed_count": 1,
    }


@pytest.mark.asyncio
async def test_rename_sse_stream_returns_error_event_when_service_raises(
    async_client: AsyncClient,
    override_collection_settings,
    install_transfer_service,
):
    """测试重命名 SSE 错误事件契约"""
    override_collection_settings("transfer-cookie")
    instances = install_transfer_service(rename_error=RuntimeError("rename boom"))

    async with async_client.stream("POST", "/api/v1/transfers/7/rename") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = await collect_sse_events(response)

    assert len(events) == 1
    event = events[0]
    assert event["type"] == "error"
    assert event["level"] == "error"
    assert event["code"] == ErrorCode.RENAME_FAILED
    assert event["message"] == "重命名流异常：rename boom"
    assert event["request_id"]
    assert event["data"] == {
        "current": 0,
        "total": 0,
        "percentage": 0,
        "message": "重命名流异常：rename boom",
    }
    assert len(instances) == 1
    assert instances[0].cookie == "transfer-cookie"
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_batch_transfer_sse_emits_progress_error_and_complete_summary(
    async_client: AsyncClient,
    override_collection_settings,
    install_transfer_service,
):
    """测试批量转存 SSE 进度/错误/汇总契约"""
    override_collection_settings("transfer-cookie")
    instances = install_transfer_service(
        transfer_results=[
            (
                True,
                "转存成功",
                [{"fid": "fid-1", "name": "video.mkv", "size": 1024, "path": "/Movies/video.mkv"}],
            ),
            RuntimeError("quota exceeded"),
        ]
    )

    async with async_client.stream(
        "POST",
        "/api/v1/transfers/batch/sse",
        json={
            "items": [
                {"collection_id": 1, "target_folder": "Movies", "auto_rename": True},
                {"collection_id": 2, "target_folder": None, "auto_rename": False},
            ]
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = await collect_sse_events(response)

    assert [event["type"] for event in events] == ["progress", "error", "complete"]
    assert len({event["request_id"] for event in events}) == 1
    progress_event, error_event, complete_event = events

    assert progress_event["level"] == "info"
    assert progress_event["message"] == "转存收藏 1: 成功"
    assert progress_event["data"] == {
        "current": 1,
        "total": 2,
        "percentage": 50.0,
        "success_count": 1,
        "failed_count": 0,
        "current_item": {
            "collection_id": 1,
            "success": True,
            "files_count": 1,
        },
    }

    assert error_event["level"] == "error"
    assert error_event["message"] == "转存收藏 2 时出错: quota exceeded"
    assert error_event["data"] == {
        "current": 2,
        "total": 2,
        "percentage": 100.0,
        "success_count": 1,
        "failed_count": 1,
        "collection_id": 2,
    }

    assert complete_event["level"] == "info"
    assert complete_event["message"] == "批量转存完成: 成功 1, 失败 1"
    assert complete_event["data"] == {
        "total": 2,
        "success_count": 1,
        "failed_count": 1,
    }
    assert len(instances) == 1
    assert instances[0].cookie == "transfer-cookie"
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_batch_transfer_sse(async_client: AsyncClient):
    """测试批量转存SSE流"""
    items = [{"collection_id": 1, "auto_rename": False}]
    async with async_client.stream("POST", "/api/v1/transfers/batch/sse", json={"items": items}) as response:
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            assert response.headers["content-type"].startswith("text/event-stream")
