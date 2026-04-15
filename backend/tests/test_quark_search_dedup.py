import pytest

from app.quark.core.quark_client import AsyncQuarkAPIClient


@pytest.mark.asyncio
async def test_search_resources_keeps_distinct_resources_without_valid_id():
    client = AsyncQuarkAPIClient(base_url="http://example.com")

    async def fake_post(url, data):
        return {
            "code": 200,
            "data": {
                "list": [
                    {"id": 0, "title": "A", "url": "https://pan.quark.cn/s/a"},
                    {"id": None, "title": "B", "url": "https://pan.quark.cn/s/b"},
                ]
            },
        }

    client._post = fake_post  # type: ignore[method-assign]

    resources = await client.search_resources("keyword", deduplicate=True)

    assert len(resources) == 2
    assert {resource.link for resource in resources} == {
        "https://pan.quark.cn/s/a",
        "https://pan.quark.cn/s/b",
    }


@pytest.mark.asyncio
async def test_search_resources_dedups_same_valid_id():
    client = AsyncQuarkAPIClient(base_url="http://example.com")

    async def fake_post(url, data):
        return {
            "code": 200,
            "data": {
                "list": [
                    {"id": 123, "title": "A", "url": "https://pan.quark.cn/s/a"},
                    {"id": "123", "title": "B", "url": "https://pan.quark.cn/s/b"},
                ]
            },
        }

    client._post = fake_post  # type: ignore[method-assign]

    resources = await client.search_resources("keyword", deduplicate=True)

    assert len(resources) == 1
    assert resources[0].id in (123, "123")
    assert resources[0].link == "https://pan.quark.cn/s/a"


@pytest.mark.asyncio
async def test_search_resources_invalid_id_does_not_conflict_with_missing_id():
    client = AsyncQuarkAPIClient(base_url="http://example.com")

    async def fake_post(url, data):
        return {
            "code": 200,
            "data": {
                "list": [
                    {"id": "invalid", "title": "A", "url": "https://pan.quark.cn/s/a"},
                    {"title": "B", "url": "https://pan.quark.cn/s/b"},
                ]
            },
        }

    client._post = fake_post  # type: ignore[method-assign]

    resources = await client.search_resources("keyword", deduplicate=True)

    assert len(resources) == 2
    assert {resource.link for resource in resources} == {
        "https://pan.quark.cn/s/a",
        "https://pan.quark.cn/s/b",
    }
