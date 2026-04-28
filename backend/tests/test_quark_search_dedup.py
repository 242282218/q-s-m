import pytest

from app.quark.core.quark_client import AsyncQuarkAPIClient


@pytest.mark.asyncio
async def test_search_resources_keeps_distinct_resources_without_valid_id():
    client = AsyncQuarkAPIClient(base_url="http://example.com")

    async def fake_get(url, params):
        return {
            "code": 200,
            "data": {
                "list": [
                    {"id": 0, "title": "A", "url": "https://pan.quark.cn/s/a"},
                    {"id": None, "title": "B", "url": "https://pan.quark.cn/s/b"},
                ]
            },
        }

    client._get = fake_get  # type: ignore[method-assign]

    resources = await client.search_resources("keyword", deduplicate=True)

    assert len(resources) == 2
    assert {resource.link for resource in resources} == {
        "https://pan.quark.cn/s/a",
        "https://pan.quark.cn/s/b",
    }


@pytest.mark.asyncio
async def test_search_resources_dedups_same_valid_id():
    client = AsyncQuarkAPIClient(base_url="http://example.com")

    async def fake_get(url, params):
        return {
            "code": 200,
            "data": {
                "list": [
                    {"id": 123, "title": "A", "url": "https://pan.quark.cn/s/a"},
                    {"id": "123", "title": "B", "url": "https://pan.quark.cn/s/b"},
                ]
            },
        }

    client._get = fake_get  # type: ignore[method-assign]

    resources = await client.search_resources("keyword", deduplicate=True)

    assert len(resources) == 1
    assert resources[0].id == 123
    assert resources[0].link == "https://pan.quark.cn/s/a"


@pytest.mark.asyncio
async def test_search_resources_invalid_id_does_not_conflict_with_missing_id():
    client = AsyncQuarkAPIClient(base_url="http://example.com")

    async def fake_get(url, params):
        return {
            "code": 200,
            "data": {
                "list": [
                    {"id": "invalid", "title": "A", "url": "https://pan.quark.cn/s/a"},
                    {"title": "B", "url": "https://pan.quark.cn/s/b"},
                ]
            },
        }

    client._get = fake_get  # type: ignore[method-assign]

    resources = await client.search_resources("keyword", deduplicate=True)

    assert len(resources) == 2
    assert {resource.link for resource in resources} == {
        "https://pan.quark.cn/s/a",
        "https://pan.quark.cn/s/b",
    }


@pytest.mark.asyncio
async def test_search_resources_uses_pansou_api_params():
    client = AsyncQuarkAPIClient(base_url="https://so.252035.xyz")
    calls = []

    async def fake_get(url, params):
        calls.append((url, params))
        return {
            "code": 0,
            "data": {
                "merged_by_type": {
                    "quark": [
                        {
                            "title": "教父2 4K",
                            "url": "https://pan.quark.cn/s/godfather2",
                            "datetime": "2026-04-28",
                            "source": "pansou",
                        }
                    ]
                }
            },
        }

    client._get = fake_get  # type: ignore[method-assign]

    resources = await client.search_resources("教父2", page=2, page_size=30)

    assert calls == [
        (
            "https://so.252035.xyz/api/search",
            {"kw": "教父2", "cloud_types": "quark", "page": 2, "res": 30},
        )
    ]
    assert len(resources) == 1
    assert resources[0].name == "教父2 4K"
    assert resources[0].link == "https://pan.quark.cn/s/godfather2"
    assert resources[0].updatetime == "2026-04-28"
    assert resources[0].uploaderid == "pansou"


@pytest.mark.asyncio
async def test_search_resources_extracts_quark_links_from_pansou_results():
    client = AsyncQuarkAPIClient(base_url="https://so.252035.xyz")

    async def fake_get(url, params):
        return {
            "code": 0,
            "data": {
                "results": [
                    {
                        "title": "教父2",
                        "datetime": "2026-04-28",
                        "source": "source-a",
                        "links": [
                            {"type": "baidu", "url": "https://pan.baidu.com/s/ignored"},
                            {"type": "quark", "url": "https://pan.quark.cn/s/from-results"},
                        ],
                    }
                ]
            },
        }

    client._get = fake_get  # type: ignore[method-assign]

    resources = await client.search_resources("教父2")

    assert len(resources) == 1
    assert resources[0].name == "教父2"
    assert resources[0].link == "https://pan.quark.cn/s/from-results"
    assert resources[0].updatetime == "2026-04-28"
    assert resources[0].uploaderid == "source-a"


@pytest.mark.asyncio
async def test_search_resources_rejects_failed_pansou_code():
    client = AsyncQuarkAPIClient(base_url="https://so.252035.xyz")

    async def fake_get(url, params):
        return {"code": 500, "message": "failed", "data": {}}

    client._get = fake_get  # type: ignore[method-assign]

    resources = await client.search_resources("教父2")

    assert resources == []
