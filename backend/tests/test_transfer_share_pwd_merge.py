import asyncio

from app.quark.core.path_resolver import QuarkPathResolver
from app.transfer.service import TransferService


class FakeQuarkClient:
    cookie = "test-cookie"

    def __init__(self, tree):
        self.tree = tree
        self.created_dirs = []
        self.requested_paths = []

    async def get_fid_by_path(self, path: str):
        self.requested_paths.append(path)
        return None

    async def ls_dir(self, pdir_fid: str):
        return {"code": 0, "data": {"list": self.tree.get(str(pdir_fid), [])}}

    async def create_dir(self, dir_name: str, pdir_fid: str = "0"):
        self.created_dirs.append((dir_name, pdir_fid))
        fid = f"created-{len(self.created_dirs)}"
        self.tree.setdefault(str(pdir_fid), []).append(
            {"fid": fid, "file_name": dir_name, "dir": True}
        )
        self.tree.setdefault(fid, [])
        return fid

    async def close(self):
        return None


class FakeDb:
    pass


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


def test_ensure_target_dir_fid_falls_back_to_stepwise_create():
    tree = {
        "0": [{"fid": "root-media", "file_name": "影视收藏", "dir": True}],
        "root-media": [{"fid": "anime", "file_name": "动漫", "dir": True}],
        "anime": [],
    }
    client = FakeQuarkClient(tree)
    service = TransferService(FakeDb(), cookie="test-cookie")
    service._quark_client = client
    service._path_resolver = QuarkPathResolver(client)

    fid = asyncio.run(
        service._ensure_target_dir_fid(
            client,
            "/影视收藏/动漫/和班上第二可爱的女孩子成为了朋友 (2026)",
        )
    )
    asyncio.run(service.close())

    assert fid == "created-1"
    assert client.requested_paths == ["/影视收藏/动漫/和班上第二可爱的女孩子成为了朋友 (2026)"]
    assert client.created_dirs == [("和班上第二可爱的女孩子成为了朋友 (2026)", "anime")]


def test_ensure_target_dir_fid_creates_missing_parent_dirs():
    tree = {"0": []}
    client = FakeQuarkClient(tree)
    service = TransferService(FakeDb(), cookie="test-cookie")
    service._quark_client = client
    service._path_resolver = QuarkPathResolver(client)

    fid = asyncio.run(service._ensure_target_dir_fid(client, "/影视收藏/动漫/新番"))
    asyncio.run(service.close())

    assert fid == "created-3"
    assert client.created_dirs == [
        ("影视收藏", "0"),
        ("动漫", "created-1"),
        ("新番", "created-2"),
    ]
