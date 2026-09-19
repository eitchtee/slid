import pytest

from slid import store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets an empty puzzle database instead of the real ./data/slid.db."""
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "slid.db")
    store.puzzle_for.cache_clear()
    yield
    store.puzzle_for.cache_clear()
