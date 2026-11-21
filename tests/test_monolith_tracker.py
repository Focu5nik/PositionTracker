import secrets
from unittest.mock import Mock

import httpx2
import jwt
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.monolith import tracker_client, tracker_tokens
from apps.monolith.catalog import tracker_views
from apps.monolith.catalog.models import Membership, Tenant

pytestmark = pytest.mark.django_db
TRACKER_URL = "http://tracker:8000/internal/v1/whoami"


@pytest.fixture
def signing_key(settings):
    settings.TRACKER_ENABLE_DEV_WHOAMI = True
    settings.TRACKER_BASE_URL = "http://tracker:8000"
    settings.TRACKER_DEV_SIGNING_KEY = secrets.token_urlsafe(32)
    return settings.TRACKER_DEV_SIGNING_KEY


@pytest.fixture
def membership(client):
    user = get_user_model().objects.create_user(username="reader")
    tenant = Tenant.objects.create(name="Own tenant")
    client.force_login(user)
    return Membership.objects.create(
        user=user, tenant=tenant, role=Membership.Role.VIEWER
    )


@pytest.fixture
def upstream(monkeypatch, signing_key):
    outbound = Mock()
    monkeypatch.setattr(tracker_client.httpx2, "get", outbound)
    return outbound


def whoami_url(tenant_id):
    return reverse("tracker-whoami", args=[tenant_id])


def tracker_response(tenant_id, **extra):
    return httpx2.Response(
        200,
        request=httpx2.Request("GET", TRACKER_URL),
        json={
            "service": "positiontracker-monolith",
            "tenant_id": tenant_id,
            "scopes": ["tracker:whoami"],
            "database": "tracker_db",
            **extra,
        },
    )


def test_member_gets_identity_and_monolith_sends_a_signed_tenant_token(
    client, membership, upstream, signing_key, monkeypatch
):
    now = 2_000_000_000
    monkeypatch.setattr(tracker_tokens, "time", lambda: now)
    tenant_id = membership.tenant_id
    upstream.return_value = tracker_response(tenant_id, extra_field="discard")

    response = client.get(
        whoami_url(tenant_id) + "?tenant_id=42&scopes=tracker:admin",
        HTTP_X_TENANT_ID="42",
        HTTP_AUTHORIZATION="Bearer user-supplied",
    )

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.json() == {
        "service": "positiontracker-monolith",
        "tenant_id": tenant_id,
        "scopes": ["tracker:whoami"],
        "database": "tracker_db",
    }
    assert upstream.call_count == 1
    outbound = upstream.call_args
    assert outbound.args == (TRACKER_URL,)
    assert outbound.kwargs["timeout"] == 2.0
    assert outbound.kwargs["follow_redirects"] is False
    assert outbound.kwargs["trust_env"] is False
    scheme, token = outbound.kwargs["headers"]["Authorization"].split()
    assert scheme == "Bearer"
    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["HS256"],
        issuer="positiontracker-dev",
        audience="positiontracker-tracker",
        options={"verify_exp": False},
    )
    assert claims == {
        "iss": "positiontracker-dev",
        "aud": "positiontracker-tracker",
        "sub": "positiontracker-monolith",
        "exp": now + 60,
        "tenant_id": tenant_id,
        "scopes": ["tracker:whoami"],
    }


def test_anonymous_request_cannot_trigger_a_tracker_call(client, upstream):
    assert client.get(whoami_url(1)).status_code == 403
    assert upstream.call_count == 0


def test_foreign_missing_and_revoked_memberships_are_indistinguishable(
    client, membership, upstream, monkeypatch
):
    issuer = Mock(wraps=tracker_tokens.issue_tracker_token)
    monkeypatch.setattr(tracker_views, "issue_tracker_token", issuer)
    foreign = Tenant.objects.create(name="Foreign tenant")
    original_tenant = membership.tenant_id
    own_url = whoami_url(original_tenant)
    upstream.return_value = tracker_response(original_tenant)
    assert client.get(own_url).status_code == 200

    membership.delete()
    for tenant_id in (original_tenant, foreign.pk, 0, 2**63 - 1, 2**63):
        response = client.get(
            whoami_url(tenant_id), HTTP_X_TENANT_ID=str(original_tenant)
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found."}
    assert upstream.call_count == 1
    assert issuer.call_count == 1


def test_disabled_route_is_hidden_before_authentication(client, upstream, settings):
    settings.TRACKER_ENABLE_DEV_WHOAMI = False

    assert client.get(whoami_url(1)).status_code == 404
    assert upstream.call_count == 0


def test_no_request_leaves_django_if_signing_key_is_missing(
    client, membership, upstream, settings
):
    settings.TRACKER_DEV_SIGNING_KEY = ""

    assert client.get(whoami_url(membership.tenant_id)).status_code == 503
    assert upstream.call_count == 0


def test_tracker_timeout_has_safe_response_and_next_call_can_succeed(
    client, membership, upstream
):
    tenant_id = membership.tenant_id
    upstream.side_effect = [
        httpx2.ReadTimeout("private upstream details"),
        tracker_response(tenant_id),
    ]

    timeout = client.get(whoami_url(tenant_id))
    assert timeout.status_code == 504
    assert timeout.json() == {"detail": "Tracker request timed out."}
    assert upstream.call_count == 1
    assert client.get(whoami_url(tenant_id)).status_code == 200
    assert upstream.call_count == 2


@pytest.mark.parametrize("upstream_status", [302, 401, 403, 503])
def test_tracker_http_errors_are_not_forwarded(
    client, membership, upstream, upstream_status
):
    upstream.return_value = httpx2.Response(
        upstream_status,
        request=httpx2.Request("GET", TRACKER_URL),
        json={"detail": "private upstream details"},
    )

    response = client.get(whoami_url(membership.tenant_id))
    assert response.status_code == 502
    assert response.json() == {"detail": "Tracker request failed."}


@pytest.mark.parametrize("failure", ["non-json", "invalid-shape", "wrong-tenant"])
def test_unexpected_tracker_response_is_not_forwarded(
    client, membership, upstream, failure
):
    request = httpx2.Request("GET", TRACKER_URL)
    upstream.return_value = {
        "non-json": httpx2.Response(200, request=request, text="unexpected"),
        "invalid-shape": httpx2.Response(200, request=request, json={}),
        "wrong-tenant": tracker_response(membership.tenant_id + 1),
    }[failure]

    response = client.get(whoami_url(membership.tenant_id))
    assert response.status_code == 502
    assert response.json() == {"detail": "Tracker request failed."}
