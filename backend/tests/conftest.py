"""Pytest fixtures for FastAPI integration tests."""

from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import Base, get_db, init_db
from app.core.config import get_settings


@pytest.fixture(scope="session", autouse=True)
def initialized_default_db():
    """Create the file-backed schema for tests using SessionLocal directly."""
    init_db()


@pytest.fixture
def test_db():
    """Create a shared in-memory SQLite engine for threaded ASGI tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Ensure all ORM models are registered before metadata creation.
    from app.db import models  # noqa: F401
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def reset_rate_limiter_state():
    """Keep rate-limit tests isolated from shared middleware state."""
    from app.middleware.rate_limit import rate_limiter

    rate_limiter.requests.clear()
    yield
    rate_limiter.requests.clear()


@pytest.fixture
async def async_client(test_db):
    """Create an async HTTP client backed by the ASGI app."""
    from app.main import app

    testing_session = sessionmaker(bind=test_db, autocommit=False, autoflush=False)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    default_headers = {}
    settings = get_settings()
    if settings.api_key:
        default_headers["X-API-Key"] = settings.api_key
    async with AsyncClient(transport=transport, base_url="http://test", headers=default_headers) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
