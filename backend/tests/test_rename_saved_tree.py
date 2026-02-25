import asyncio

from app.quark.api.routes.search import rename_saved_tree
from app.transfer.renamer import Renamer


class FakeQuarkClient:
    def __init__(self, tree: dict):
        self.tree = tree
        self.renamed = []

    async def ls_dir(self, pdir_fid: str):
        return {"code": 0, "data": {"list": self.tree.get(pdir_fid, [])}}

    async def rename(self, fid: str, new_name: str):
        self.renamed.append((fid, new_name))
        for items in self.tree.values():
            for item in items:
                if item.get("fid") == fid:
                    if "file_name" in item:
                        item["file_name"] = new_name
                    if "name" in item:
                        item["name"] = new_name
        return True


def test_rename_saved_tree_tv_recursive():
    tree = {
        "root": [
            {"fid": "d1", "file_name": "Season 1", "dir": True},
            {"fid": "note", "file_name": "README.txt", "dir": False},
        ],
        "d1": [
            {"fid": "f1", "file_name": "Takagi.S01E01.1080p.mkv", "dir": False},
            {"fid": "d2", "file_name": "Season 2", "dir": 1},
        ],
        "d2": [
            {"fid": "f2", "name": "Takagi.S02E03.WEB-DL.mp4", "file_type": 1},
            {"fid": "img", "file_name": "poster.jpg", "dir": False},
        ],
    }
    client = FakeQuarkClient(tree)
    renamer = Renamer()

    renamed_count = asyncio.run(
        rename_saved_tree(
            client=client,
            root_fid="root",
            renamer=renamer,
            title="擅长捉弄的高木同学",
            year=2018,
            media_type="tv",
        )
    )

    assert renamed_count == 4
    renamed_map = dict(client.renamed)
    assert renamed_map["d1"] == "Season 01"
    assert renamed_map["d2"] == "Season 02"
    assert renamed_map["f1"] == "擅长捉弄的高木同学 (2018) - S01E01.mkv"
    assert renamed_map["f2"] == "擅长捉弄的高木同学 (2018) - S02E03.mp4"
