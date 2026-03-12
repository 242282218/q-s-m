import asyncio
from typing import Dict, List, Optional

from app.transfer.emby import (
    cleanup_non_video_files,
    collect_video_files,
    reorganize_to_emby_structure,
)
from app.transfer.renamer import Renamer


class FakeQuarkClient:
    def __init__(self, tree: Dict[str, List[dict]]):
        self.tree = tree
        self.parent_map: Dict[str, Optional[str]] = {}
        self.deleted: List[str] = []
        self.created_dirs: List[str] = []
        self._next_dir_id = 100
        self._rebuild_parent_map()

    def _rebuild_parent_map(self):
        self.parent_map.clear()
        for parent, items in self.tree.items():
            for item in items:
                self.parent_map[item["fid"]] = parent

    async def ls_dir(self, pdir_fid: str):
        return {"code": 0, "data": {"list": self.tree.get(pdir_fid, [])}}

    async def create_dir(self, dir_name: str, pdir_fid: str = "0"):
        new_fid = f"dir_{self._next_dir_id}"
        self._next_dir_id += 1
        self.created_dirs.append(dir_name)
        self.tree.setdefault(pdir_fid, []).append({"fid": new_fid, "file_name": dir_name, "dir": True})
        self.tree.setdefault(new_fid, [])
        self.parent_map[new_fid] = pdir_fid
        return new_fid

    async def move_file(self, fid_list, to_pdir_fid: str, current_dir_fid: str | None = None):
        for fid in fid_list:
            src_parent = self.parent_map.get(fid)
            if src_parent is None:
                return False
            src_items = self.tree.get(src_parent, [])
            item = next((x for x in src_items if x.get("fid") == fid), None)
            if not item:
                return False
            src_items.remove(item)
            self.tree.setdefault(to_pdir_fid, []).append(item)
            self.parent_map[fid] = to_pdir_fid
        return True

    async def rename(self, fid: str, new_name: str):
        parent = self.parent_map.get(fid)
        if parent is None:
            return False
        for item in self.tree.get(parent, []):
            if item.get("fid") == fid:
                if "file_name" in item:
                    item["file_name"] = new_name
                if "name" in item:
                    item["name"] = new_name
                return True
        return False

    async def delete_file(self, fid_list):
        for fid in fid_list:
            parent = self.parent_map.get(fid)
            if parent is None:
                continue
            items = self.tree.get(parent, [])
            item = next((x for x in items if x.get("fid") == fid), None)
            if item:
                items.remove(item)
                self.deleted.append(fid)
            if fid in self.tree:
                del self.tree[fid]
            self.parent_map.pop(fid, None)
        return True


def test_reorganize_and_cleanup_tv_recursive():
    tree = {
        "root": [
            {"fid": "d1", "file_name": "Season 1", "dir": True},
            {"fid": "note", "file_name": "README.txt", "dir": False},
        ],
        "d1": [
            {"fid": "f1", "file_name": "Takagi.S01E01.1080p.mkv", "dir": False, "size": 1000},
            {"fid": "d2", "file_name": "Season 2", "dir": 1},
        ],
        "d2": [
            {"fid": "f2", "name": "Takagi.S02E03.WEB-DL.mp4", "file_type": 1, "size": 900},
            {"fid": "img", "file_name": "poster.jpg", "dir": False},
        ],
    }

    client = FakeQuarkClient(tree)
    renamer = Renamer()

    video_files = asyncio.run(collect_video_files(client=client, root_fid="root", renamer=renamer))
    assert len(video_files) == 2

    retained_fids = set()

    async def _run_reorganize():
        async for event in reorganize_to_emby_structure(
            client=client,
            root_fid="root",
            root_path="/影视收藏/电视剧/Takagi-san (2018) [tmdbid=75865]",
            video_files=video_files,
            renamer=renamer,
            title="Takagi-san",
            year=2018,
            media_type="tv",
        ):
            if event.get("type") == "complete":
                retained_fids.update(event.get("retained_fids") or [])

    asyncio.run(_run_reorganize())

    assert "Season 01" in client.created_dirs
    assert "Season 02" in client.created_dirs

    all_names = [item.get("file_name") or item.get("name") for items in client.tree.values() for item in items]
    assert "Takagi-san (2018) - S01E01.mkv" in all_names
    assert "Takagi-san (2018) - S02E03.mp4" in all_names

    async def _run_cleanup():
        async for _ in cleanup_non_video_files(
            client=client,
            root_fid="root",
            renamer=renamer,
            protected_video_fids=retained_fids,
            keep_subtitles=False,
            delete_non_video=True,
            delete_unselected_videos=True,
            delete_empty_dirs=True,
        ):
            pass

    asyncio.run(_run_cleanup())

    assert "note" in client.deleted
    assert "img" in client.deleted
