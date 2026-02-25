import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.collection.verify_service import CollectionVerifyService
from app.db.models import Collection, TransferHistory
from app.db.session import Base
from app.quark.core.path_resolver import QuarkPathResolver


class FakeQuarkClient:
    def __init__(self, tree):
        self.tree = tree
        self.ls_calls = []

    async def ls_dir(self, pdir_fid: str):
        key = str(pdir_fid)
        self.ls_calls.append(key)
        return {"code": 0, "data": {"list": self.tree.get(key, [])}}


def _create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_path_resolver_prefix_cache_reduces_ls_calls():
    tree = {
        "0": [{"fid": "d1", "file_name": "影视收藏", "dir": True}],
        "d1": [{"fid": "d2", "file_name": "电影", "dir": True}],
        "d2": [
            {"fid": "d3", "file_name": "A", "dir": True},
            {"fid": "d4", "file_name": "B", "dir": True},
        ],
    }
    client = FakeQuarkClient(tree)
    resolver = QuarkPathResolver(client)

    fid_a = asyncio.run(resolver.find_fid_by_path_no_create("/影视收藏/电影/A"))
    fid_b = asyncio.run(resolver.find_fid_by_path_no_create("/影视收藏/电影/B"))

    assert fid_a == "d3"
    assert fid_b == "d4"
    assert len(client.ls_calls) == 3


def test_verify_single_switches_status_between_transferred_and_deleted():
    db = _create_session()
    try:
        collection = Collection(
            tmdb_id=27205,
            media_type="movie",
            title="盗梦空间",
            year=2010,
            quark_share_url="https://pan.quark.cn/s/demo-link",
            status=1,
            saved_at=datetime.now(timezone.utc),
        )
        db.add(collection)
        db.commit()
        db.refresh(collection)

        root_path = "/影视收藏/电影/盗梦空间 (2010) [tmdbid=27205]"
        db.add(
            TransferHistory(
                collection_id=collection.id,
                quark_fid="fid-root",
                local_path=root_path,
                file_name="盗梦空间 (2010).mkv",
                transferred_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        tree = {
            "0": [{"fid": "d1", "file_name": "影视收藏", "dir": True}],
            "d1": [{"fid": "d2", "file_name": "电影", "dir": True}],
            "d2": [],
        }
        client = FakeQuarkClient(tree)
        service = CollectionVerifyService(db, client)

        first_result = asyncio.run(service.verify_single(collection.id))
        db.refresh(collection)
        assert first_result["exists"] is False
        assert first_result["current_status"] == 3
        assert collection.status == 3

        tree["d2"].append({"fid": "d3", "file_name": "盗梦空间 (2010) [tmdbid=27205]", "dir": True})
        tree["d3"] = [{"fid": "f1", "file_name": "盗梦空间 (2010).mkv", "dir": False}]

        service = CollectionVerifyService(db, client)
        second_result = asyncio.run(service.verify_single(collection.id))
        db.refresh(collection)
        assert second_result["exists"] is True
        assert second_result["current_status"] == 1
        assert collection.status == 1
    finally:
        db.close()
