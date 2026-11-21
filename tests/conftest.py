import pytest


@pytest.fixture
def tracker_db_env(monkeypatch):
    monkeypatch.setenv("TRACKER_DB_HOST", "localhost")
    monkeypatch.setenv("TRACKER_DB_NAME", "tracker_test")
    monkeypatch.setenv("TRACKER_DB_USER", "tracker_test")
    monkeypatch.setenv("TRACKER_DB_PASSWORD", "")
