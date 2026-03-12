import asyncio
from typing import Any, Dict, List

from app.transfer.emby import transfer_share_to_target_fid


class FakeTransferClient:
    def __init__(self, tree: Dict[str, List[Dict[str, Any]]]):
        self.tree = tree
        self.save_calls: List[Dict[str, Any]] = []

    async def validate_share_link(self, share_url: str):
        return True, "pwd_id", "stoken"

    async def get_detail(self, pwd_id: str, stoken: str, pdir_fid: str = "0"):
        return {"code": 0, "data": {"list": self.tree.get(pdir_fid, [])}}

    async def save_file(
        self,
        fid_list,
        fid_token_list,
        to_pdir_fid,
        pwd_id,
        stoken,
    ):
        self.save_calls.append(
            {
                "fid_list": list(fid_list),
                "fid_token_list": list(fid_token_list),
                "to_pdir_fid": to_pdir_fid,
                "pwd_id": pwd_id,
                "stoken": stoken,
            }
        )
        return {"status": 200, "code": 0, "data": {"task_id": "task_1"}}


def test_transfer_flatten_single_root_recurses_to_files():
    tree = {
        "0": [{"fid": "d1", "file_name": "合集", "dir": True, "share_fid_token": "td1"}],
        "d1": [{"fid": "d2", "file_name": "资源", "dir": True, "share_fid_token": "td2"}],
        "d2": [
            {"fid": "f1", "file_name": "EP01.mkv", "dir": False, "share_fid_token": "tf1"},
            {"fid": "f2", "file_name": "EP02.mkv", "dir": False, "share_fid_token": "tf2"},
        ],
    }
    client = FakeTransferClient(tree)

    success, _, transferred_items, _ = asyncio.run(
        transfer_share_to_target_fid(client, "https://pan.quark.cn/s/demo", "target", flatten_single_root=True)
    )

    assert success is True
    assert [item.get("fid") for item in transferred_items] == ["f1", "f2"]
    assert client.save_calls[0]["fid_list"] == ["f1", "f2"]


def test_transfer_flatten_single_root_stops_on_multiple_children():
    tree = {
        "0": [{"fid": "d1", "file_name": "资源", "dir": 1, "share_fid_token": "td1"}],
        "d1": [
            {"fid": "s1", "file_name": "Season 1", "dir": True, "share_fid_token": "ts1"},
            {"fid": "s2", "file_name": "Season 2", "dir": True, "share_fid_token": "ts2"},
        ],
    }
    client = FakeTransferClient(tree)

    success, _, transferred_items, _ = asyncio.run(
        transfer_share_to_target_fid(client, "https://pan.quark.cn/s/demo", "target", flatten_single_root=True)
    )

    assert success is True
    assert [item.get("fid") for item in transferred_items] == ["s1", "s2"]
    assert client.save_calls[0]["fid_list"] == ["s1", "s2"]


def test_transfer_flatten_single_root_respects_max_depth():
    tree = {
        "0": [{"fid": "d1", "file_name": "L1", "dir": True, "share_fid_token": "t1"}],
        "d1": [{"fid": "d2", "file_name": "L2", "dir": True, "share_fid_token": "t2"}],
        "d2": [{"fid": "d3", "file_name": "L3", "dir": True, "share_fid_token": "t3"}],
        "d3": [{"fid": "d4", "file_name": "L4", "dir": True, "share_fid_token": "t4"}],
        "d4": [{"fid": "d5", "file_name": "L5", "dir": True, "share_fid_token": "t5"}],
        "d5": [{"fid": "d6", "file_name": "L6", "dir": True, "share_fid_token": "t6"}],
        "d6": [{"fid": "d7", "file_name": "L7", "dir": True, "share_fid_token": "t7"}],
    }
    client = FakeTransferClient(tree)

    success, _, transferred_items, _ = asyncio.run(
        transfer_share_to_target_fid(client, "https://pan.quark.cn/s/demo", "target", flatten_single_root=True)
    )

    assert success is True
    assert [item.get("fid") for item in transferred_items] == ["d6"]
    assert client.save_calls[0]["fid_list"] == ["d6"]
