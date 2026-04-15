from unittest.mock import AsyncMock

import pytest

from app.quark.core.transfer_client import QuarkTransferClient


def test_extract_url_parses_pwd_param():
    client = QuarkTransferClient(cookie="")

    pwd_id, passcode = client.extract_url("https://pan.quark.cn/s/abc123?pwd=9xYz")

    assert pwd_id == "abc123"
    assert passcode == "9xYz"


@pytest.mark.asyncio
async def test_validate_share_link_passes_passcode_to_get_stoken():
    client = QuarkTransferClient(cookie="")
    client.get_stoken = AsyncMock(return_value="stoken_1")

    is_valid, pwd_id, stoken = await client.validate_share_link(
        "https://pan.quark.cn/s/share001?pwd=pass88"
    )

    assert is_valid is True
    assert pwd_id == "share001"
    assert stoken == "stoken_1"
    client.get_stoken.assert_awaited_once_with("share001", "pass88")


@pytest.mark.asyncio
async def test_validate_share_link_without_pwd_passes_empty_string():
    client = QuarkTransferClient(cookie="")
    client.get_stoken = AsyncMock(return_value="stoken_2")

    is_valid, pwd_id, stoken = await client.validate_share_link("https://pan.quark.cn/s/share002")

    assert is_valid is True
    assert pwd_id == "share002"
    assert stoken == "stoken_2"
    client.get_stoken.assert_awaited_once_with("share002", "")
