import threading
import time

from app.db import session


def test_init_db_serializes_concurrent_calls(monkeypatch, tmp_path):
    lock_path = tmp_path / ".init_db.lock"
    monkeypatch.setattr(session, "INIT_LOCK_PATH", lock_path)

    state_lock = threading.Lock()
    state = {"active": 0, "max_active": 0, "calls": 0}

    def fake_create_all(*, bind):
        _ = bind
        with state_lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.2)
        with state_lock:
            state["calls"] += 1
            state["active"] -= 1

    monkeypatch.setattr(session.Base.metadata, "create_all", fake_create_all)

    threads = [threading.Thread(target=session.init_db) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert state["calls"] == 2
    assert state["max_active"] == 1
    assert not lock_path.exists()
