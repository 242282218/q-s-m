from app.transfer.service import TransferService


def test_attach_share_passcode_adds_pwd_when_missing():
    merged = TransferService._attach_share_passcode(
        "https://pan.quark.cn/s/abc123",
        "xYz9",
    )

    assert merged == "https://pan.quark.cn/s/abc123?pwd=xYz9"


def test_attach_share_passcode_keeps_existing_pwd():
    merged = TransferService._attach_share_passcode(
        "https://pan.quark.cn/s/abc123?pwd=from_url",
        "from_field",
    )

    assert merged == "https://pan.quark.cn/s/abc123?pwd=from_url"


def test_attach_share_passcode_fills_blank_pwd_param():
    merged = TransferService._attach_share_passcode(
        "https://pan.quark.cn/s/abc123?pwd=&foo=bar",
        "filled",
    )

    assert merged == "https://pan.quark.cn/s/abc123?pwd=filled&foo=bar"
