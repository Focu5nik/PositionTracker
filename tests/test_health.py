from unittest.mock import AsyncMock, Mock

import pytest
from django.db import OperationalError as DjangoOperationalError
from django.test import Client
from fastapi.testclient import TestClient
from psycopg import OperationalError

from apps.monolith.config import health
from apps.tracker.src.tracker import main


@pytest.fixture(params=["monolith", "tracker"])
def health_client(request, monkeypatch):
    if request.param == "monolith":
        probe = Mock()
        monkeypatch.setattr(health, "check_database", probe)
        yield Client(headers={"Host": "localhost"}), probe, DjangoOperationalError
    else:
        probe = AsyncMock()
        monkeypatch.setattr(main, "check_database", probe)
        with TestClient(main.app) as client:
            yield client, probe, OperationalError


def test_live_does_not_need_database(health_client):
    client, probe, error = health_client
    probe.side_effect = error("simulated database failure")

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    probe.assert_not_called()


def test_ready_when_database_responds(health_client):
    client, probe, _ = health_client

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    probe.assert_called_once_with()


def test_ready_recovers_after_database_failure(health_client):
    client, probe, error = health_client
    probe.side_effect = [error("simulated database failure"), None]

    unavailable = client.get("/health/ready")
    recovered = client.get("/health/ready")

    assert unavailable.status_code == 503
    assert unavailable.json() == {"status": "unavailable"}
    assert recovered.status_code == 200
    assert recovered.json() == {"status": "ready"}
    assert probe.call_count == 2
