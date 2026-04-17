from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.collection.service import CollectionService
from app.db.models import Collection
from app.db.session import Base


def _create_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_list_cursor_first_page_generates_next_cursor_without_cursor_input():
    db = _create_session()
    try:
        service = CollectionService(db)
        for index in range(25):
            db.add(
                Collection(
                    tmdb_id=10000 + index,
                    media_type="movie",
                    title=f"Movie {index}",
                    quark_share_url=f"https://pan.quark.cn/s/cursor-{index}",
                    status=1,
                )
            )
        db.commit()

        items, has_more, next_cursor, prev_cursor = service.list_cursor(
            cursor=None,
            limit=20,
            sort_by="saved_at",
            order="desc",
        )

        assert len(items) == 20
        assert has_more is True
        assert isinstance(next_cursor, str)
        assert next_cursor != ""
        assert prev_cursor is None
    finally:
        db.close()


def test_list_cursor_roundtrip_advances_when_sorting_by_saved_at():
    db = _create_session()
    try:
        service = CollectionService(db)
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(3):
            db.add(
                Collection(
                    tmdb_id=20000 + index,
                    media_type="movie",
                    title=f"Roundtrip {index}",
                    quark_share_url=f"https://pan.quark.cn/s/roundtrip-{index}",
                    status=1,
                    saved_at=base_time + timedelta(minutes=index),
                )
            )
        db.commit()

        first_items, has_more, next_cursor, prev_cursor = service.list_cursor(
            cursor=None,
            limit=2,
            sort_by="saved_at",
            order="desc",
        )
        second_items, second_has_more, second_next_cursor, second_prev_cursor = service.list_cursor(
            cursor=next_cursor,
            limit=2,
            sort_by="saved_at",
            order="desc",
        )

        assert [item.title for item in first_items] == ["Roundtrip 2", "Roundtrip 1"]
        assert has_more is True
        assert next_cursor
        assert prev_cursor is None
        assert [item.title for item in second_items] == ["Roundtrip 0"]
        assert second_has_more is False
        assert second_next_cursor is None
        assert isinstance(second_prev_cursor, str)
    finally:
        db.close()
