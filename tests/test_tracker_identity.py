import asyncio
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError

from apps.tracker.src.tracker import service
from apps.tracker.src.tracker.main import create_app

PATH = "/internal/v1/whoami"


@pytest.fixture
def key():
    return secrets.token_urlsafe(48)


@pytest.fixture
def client(key, tracker_db_env):
    with TestClient(create_app(dev_signing_key=key)) as test_client:
        yield test_client


@pytest.fixture
def claims():
    return {
        "iss": "positiontracker-dev",
        "aud": "positiontracker-tracker",
        "sub": "catalog-demo",
        "exp": int(time.time()) + 60,
        "tenant_id": 7,
        "scopes": ["tracker:whoami"],
    }


def authorization(claims, key, algorithm="HS256"):
    return {"Authorization": f"Bearer {jwt.encode(claims, key, algorithm=algorithm)}"}


@pytest.fixture
def read_database(monkeypatch):
    async def read(session):
        assert session.in_transaction()
        return "tracker_test"

    probe = AsyncMock(side_effect=read)
    monkeypatch.setattr(service, "read_database_name", probe)
    return probe


@pytest.mark.parametrize("tenant_id", [1, 2**63 - 1])
def test_identity_uses_signed_tenant_and_ends_transaction(
    client, claims, key, tenant_id, read_database
):
    headers = {
        **authorization({**claims, "tenant_id": tenant_id}, key),
        "X-Tenant-ID": "42",
    }

    response = client.get(PATH, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "service": "catalog-demo",
        "tenant_id": tenant_id,
        "scopes": ["tracker:whoami"],
        "database": "tracker_test",
    }
    read_database.assert_awaited_once()
    assert not read_database.await_args.args[0].in_transaction()


@pytest.mark.parametrize("header", [None, "Basic rejected", "Bearer malformed"])
def test_missing_or_malformed_bearer_is_unauthorized(client, header, read_database):
    headers = {"X-Tenant-ID": "7"}
    if header is not None:
        headers["Authorization"] = header
    response = client.get(PATH, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    read_database.assert_not_awaited()


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "other-issuer"),
        ("aud", "monolith"),
        ("aud", ["positiontracker-tracker", "monolith"]),
        ("exp", 0),
        ("exp", None),
        ("exp", "9999999999"),
        ("sub", " "),
        ("tenant_id", True),
        ("tenant_id", 0),
        ("tenant_id", "7"),
        ("tenant_id", 2**63),
        ("scopes", "tracker:whoami"),
        ("scopes", [1]),
    ],
)
def test_invalid_claims_are_unauthorized(
    client, claims, key, claim, value, read_database
):
    response = client.get(PATH, headers=authorization({**claims, claim: value}, key))
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing service token"}
    read_database.assert_not_awaited()


@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "sub", "tenant_id", "scopes"])
def test_required_claims_cannot_be_omitted(client, claims, key, claim, read_database):
    del claims[claim]
    assert client.get(PATH, headers=authorization(claims, key)).status_code == 401
    read_database.assert_not_awaited()


@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "none"])
def test_requires_valid_signature_and_expected_algorithm(
    client, claims, key, algorithm, read_database
):
    signing_keys = {"HS256": secrets.token_urlsafe(32), "HS384": key, "none": None}
    response = client.get(
        PATH, headers=authorization(claims, signing_keys[algorithm], algorithm)
    )
    assert response.status_code == 401
    read_database.assert_not_awaited()


@pytest.mark.parametrize("scopes", [[], ["tracker:whoami:other"]])
def test_valid_token_without_required_scope_is_forbidden(
    client, claims, key, scopes, read_database
):
    response = client.get(
        PATH, headers=authorization({**claims, "scopes": scopes}, key)
    )
    assert response.status_code == 403
    read_database.assert_not_awaited()


def test_dev_route_is_absent_by_default(tracker_db_env):
    with TestClient(create_app()) as client:
        assert client.get(PATH).status_code == 404
        assert PATH not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("key", ["", " " * 32])
def test_enabled_dev_route_requires_a_signing_key(key):
    with pytest.raises(RuntimeError, match="TRACKER_DEV_SIGNING_KEY"):
        create_app(dev_signing_key=key)


def test_database_failure_ends_transaction_and_retry_uses_a_new_session(
    client,
    claims,
    key,
    read_database,
):
    read_database.side_effect = [
        TimeoutError("simulated database timeout"),
        "tracker_test",
    ]
    headers = authorization(claims, key)
    assert client.get(PATH, headers=headers).status_code == 503
    failed_session = read_database.await_args.args[0]
    assert not failed_session.in_transaction()
    assert client.get(PATH, headers=headers).status_code == 200
    assert read_database.await_args.args[0] is not failed_session


def test_concurrent_requests_use_separate_sessions_and_tenants(
    client, claims, key, monkeypatch
):
    sessions = []
    both_entered = asyncio.Event()

    async def read(session):
        assert session.in_transaction()
        sessions.append(session)
        if len(sessions) == 2:
            both_entered.set()
        await asyncio.wait_for(both_entered.wait(), timeout=5)
        return "tracker_test"

    monkeypatch.setattr(service, "read_database_name", read)

    def get_identity(tenant_id):
        return client.get(
            PATH, headers=authorization({**claims, "tenant_id": tenant_id}, key)
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(get_identity, [7, 42]))

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["tenant_id"] for response in responses] == [7, 42]
    assert len(set(sessions)) == 2
    assert all(not session.in_transaction() for session in sessions)
