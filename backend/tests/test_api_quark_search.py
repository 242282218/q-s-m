from __future__ import annotations

from collections.abc import Callable

import pytest
from httpx import AsyncClient

from app.core.error_codes import ErrorCode
from app.quark.schemas.search import MediaDto, ResourceDto, SearchResponse


def build_search_response(
    *,
    success: bool,
    message: str,
    media: MediaDto | None,
    resources: list[ResourceDto],
    total: int,
    query_time: float | None,
) -> SearchResponse:
    return SearchResponse(
        success=success,
        message=message,
        media=media,
        resources=resources,
        total=total,
        query_time=query_time,
    )


def build_media(tmdb_id: int, title: str, year: int, media_type: str = "movie") -> MediaDto:
    return MediaDto(
        tmdb_id=tmdb_id,
        title=title,
        original_title=title,
        year=year,
        rating=8.7,
        overview=f"{title} overview",
        poster_path=f"/{title.lower()}-poster.jpg",
        backdrop_path=f"/{title.lower()}-backdrop.jpg",
        media_type=media_type,
    )


def build_resource(name: str, link: str) -> ResourceDto:
    return ResourceDto(
        name=name,
        link=link,
        overall_score=98.5,
        quality_level="2160p",
        resolution="2160p",
        codec="HEVC",
        is_best=True,
        normalized_name=name,
        conf=0.92,
        qual=0.95,
        alpha=0.88,
        tags=["4K", "HDR"],
        size_gb=18.6,
        c_text=0.91,
        c_intent=0.89,
        c_plaus=0.94,
        p=0.96,
        r=0.93,
    )


@pytest.fixture
def install_search_service(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[FakeSearchService]]:
    from app.main import app

    monkeypatch.setattr(app.state, "tmdb_client", object(), raising=False)
    monkeypatch.setattr(app.state, "quark_client", object(), raising=False)

    def _install(
        *,
        tmdb_response: SearchResponse | None = None,
        title_response: SearchResponse | None = None,
    ) -> list[FakeSearchService]:
        instances: list[FakeSearchService] = []

        class FakeSearchService:
            def __init__(self, tmdb_client=None, quark_client=None):
                self.tmdb_client = tmdb_client
                self.quark_client = quark_client
                self.calls: list[tuple[str, object, int | None, str | None]] = []
                self.closed = False
                instances.append(self)

            async def search_by_tmdb_id(self, tmdb_id: int, max_results: int, media_type: str):
                self.calls.append(("tmdb", tmdb_id, max_results, media_type))
                assert tmdb_response is not None
                return tmdb_response

            async def search_by_title(self, title: str, year: int | None, max_results: int):
                self.calls.append(("title", title, year, str(max_results)))
                assert title_response is not None
                return title_response

            async def close(self):
                self.closed = True

        monkeypatch.setattr("app.quark.api.routes.search.SearchService", FakeSearchService)
        return instances

    return _install


@pytest.mark.asyncio
async def test_quark_search_by_tmdb_id_returns_success_payload_contract(
    async_client: AsyncClient,
    install_search_service,
):
    response_model = build_search_response(
        success=True,
        message="匹配到 1 个资源",
        media=build_media(27205, "Inception", 2010),
        resources=[
            build_resource(
                "Inception.2010.2160p.BluRay.HEVC",
                "https://pan.quark.cn/s/inception4k",
            )
        ],
        total=1,
        query_time=0.42,
    )
    instances = install_search_service(tmdb_response=response_model)

    response = await async_client.get(
        "/api/v1/quark/searches/tmdb/27205",
        params={"media_type": "movie", "max_results": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"code", "message", "data", "error", "request_id", "timestamp"}
    assert payload["code"] == 0
    assert payload["message"] == "匹配到 1 个资源"
    assert payload["error"] is None
    assert payload["request_id"] is None
    assert payload["timestamp"]
    assert payload["data"] == {
        "media": {
            "tmdb_id": 27205,
            "title": "Inception",
            "original_title": "Inception",
            "year": 2010,
            "rating": 8.7,
            "overview": "Inception overview",
            "poster_path": "/inception-poster.jpg",
            "backdrop_path": "/inception-backdrop.jpg",
            "media_type": "movie",
        },
        "resources": [
            {
                "name": "Inception.2010.2160p.BluRay.HEVC",
                "link": "https://pan.quark.cn/s/inception4k",
                "overall_score": 98.5,
                "quality_level": "2160p",
                "resolution": "2160p",
                "codec": "HEVC",
                "is_best": True,
                "normalized_name": "Inception.2010.2160p.BluRay.HEVC",
                "conf": 0.92,
                "qual": 0.95,
                "alpha": 0.88,
                "tags": ["4K", "HDR"],
                "size_gb": 18.6,
                "c_text": 0.91,
                "c_intent": 0.89,
                "c_plaus": 0.94,
                "p": 0.96,
                "r": 0.93,
            }
        ],
        "total": 1,
        "query_time": 0.42,
    }
    assert len(instances) == 1
    assert instances[0].calls == [("tmdb", 27205, 1, "movie")]
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_quark_search_by_title_returns_success_payload_contract(
    async_client: AsyncClient,
    install_search_service,
):
    response_model = build_search_response(
        success=True,
        message="找到多个资源",
        media=build_media(348, "Alien", 1979),
        resources=[
            build_resource(
                "Alien.1979.2160p.REMUX",
                "https://pan.quark.cn/s/alien4k",
            )
        ],
        total=1,
        query_time=0.77,
    )
    instances = install_search_service(title_response=response_model)

    response = await async_client.get(
        "/api/v1/quark/searches/by-title",
        params={"title": "Alien", "year": 1979, "max_results": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"code", "message", "data", "error", "request_id", "timestamp"}
    assert payload["code"] == 0
    assert payload["message"] == "找到多个资源"
    assert payload["error"] is None
    assert payload["request_id"] is None
    assert payload["timestamp"]
    assert payload["data"] == {
        "media": {
            "tmdb_id": 348,
            "title": "Alien",
            "original_title": "Alien",
            "year": 1979,
            "rating": 8.7,
            "overview": "Alien overview",
            "poster_path": "/alien-poster.jpg",
            "backdrop_path": "/alien-backdrop.jpg",
            "media_type": "movie",
        },
        "resources": [
            {
                "name": "Alien.1979.2160p.REMUX",
                "link": "https://pan.quark.cn/s/alien4k",
                "overall_score": 98.5,
                "quality_level": "2160p",
                "resolution": "2160p",
                "codec": "HEVC",
                "is_best": True,
                "normalized_name": "Alien.1979.2160p.REMUX",
                "conf": 0.92,
                "qual": 0.95,
                "alpha": 0.88,
                "tags": ["4K", "HDR"],
                "size_gb": 18.6,
                "c_text": 0.91,
                "c_intent": 0.89,
                "c_plaus": 0.94,
                "p": 0.96,
                "r": 0.93,
            }
        ],
        "total": 1,
        "query_time": 0.77,
    }
    assert len(instances) == 1
    assert instances[0].calls == [("title", "Alien", 1979, "100")]
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_quark_search_by_tmdb_id_returns_stable_search_failed_payload(
    async_client: AsyncClient,
    install_search_service,
):
    instances = install_search_service(
        tmdb_response=build_search_response(
            success=False,
            message="夸克搜索超时",
            media=None,
            resources=[],
            total=0,
            query_time=1.15,
        )
    )

    response = await async_client.get("/api/v1/quark/searches/tmdb/7", params={"max_results": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.SEARCH_FAILED
    assert payload["message"] == "夸克搜索超时"
    assert payload["data"] == {
        "media": None,
        "resources": [],
        "total": 0,
        "query_time": 1.15,
    }
    assert payload["error"] == {
        "field": "tmdb_id",
        "value": 7,
        "reason": "夸克搜索超时",
        "context": None,
    }
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_quark_search_by_title_returns_stable_search_failed_payload(
    async_client: AsyncClient,
    install_search_service,
):
    instances = install_search_service(
        title_response=build_search_response(
            success=False,
            message="没有找到可用资源",
            media=None,
            resources=[],
            total=0,
            query_time=0.08,
        )
    )

    response = await async_client.get(
        "/api/v1/quark/searches/by-title",
        params={"title": "Alien", "year": 1979, "max_results": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.SEARCH_FAILED
    assert payload["message"] == "没有找到可用资源"
    assert payload["data"] == {
        "media": None,
        "resources": [],
        "total": 0,
        "query_time": 0.08,
    }
    assert payload["error"] == {
        "field": "title",
        "value": "Alien",
        "reason": "没有找到可用资源",
        "context": None,
    }
    assert instances[0].closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "params", "expected_field"),
    [
        ("/api/v1/quark/searches/tmdb/7", {"max_results": 0}, "max_results"),
        ("/api/v1/quark/searches/by-title", {"max_results": 5}, "title"),
        ("/api/v1/quark/searches/by-title", {"title": "Alien", "max_results": 101}, "max_results"),
    ],
)
async def test_quark_search_endpoints_validate_boundary_inputs(
    async_client: AsyncClient,
    path: str,
    params: dict[str, int | str],
    expected_field: str,
):
    response = await async_client.get(path, params=params)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == 422
    assert payload["message"] == "Validation Error"
    assert isinstance(payload["data"], list)
    assert payload["data"][0]["loc"][-1] == expected_field
