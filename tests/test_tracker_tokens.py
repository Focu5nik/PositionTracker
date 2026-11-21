import secrets

import jwt
import pytest

from apps.monolith import tracker_tokens


@pytest.mark.parametrize(
    ("tenant_id", "scopes"),
    [(1, ["tracker:whoami"]), (2**63 - 1, ["tracker:projects:read", "tracker:whoami"])],
)
def test_issuer_signs_the_supplied_tenant_and_scopes(tenant_id, scopes, monkeypatch):
    signing_key = secrets.token_urlsafe(32)
    monkeypatch.setattr(tracker_tokens, "time", lambda: 2_000_000_000)

    token = tracker_tokens.issue_tracker_token(
        tenant_id=tenant_id, scopes=scopes, signing_key=signing_key
    )
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
        "exp": 2_000_000_060,
        "tenant_id": tenant_id,
        "scopes": scopes,
    }


@pytest.mark.parametrize("tenant_id", [True, 0, 2**63])
def test_issuer_rejects_invalid_tenant_id(tenant_id):
    with pytest.raises(ValueError, match="tenant ID"):
        tracker_tokens.issue_tracker_token(
            tenant_id=tenant_id, scopes=[], signing_key=secrets.token_urlsafe(32)
        )


def test_issuer_rejects_missing_signing_key():
    with pytest.raises(ValueError, match="signing key"):
        tracker_tokens.issue_tracker_token(tenant_id=1, scopes=[], signing_key="")
