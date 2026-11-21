import httpx2

from apps.tracker_contract import (
    INTERNAL_API_PREFIX,
    MONOLITH_SERVICE,
    WHOAMI_SCOPE,
    Identity,
)


class TrackerResponseError(Exception):
    pass


def fetch_tracker_identity(base_url: str, *, token: str, tenant_id: int) -> Identity:
    response = httpx2.get(
        f"{base_url.rstrip('/')}{INTERNAL_API_PREFIX}/whoami",
        headers={"Authorization": f"Bearer {token}"},
        timeout=2.0,
        follow_redirects=False,
        trust_env=False,
    )
    response.raise_for_status()
    try:
        identity = Identity.model_validate(response.json(), strict=True)
    except ValueError:
        raise TrackerResponseError("Invalid Tracker response") from None

    if (identity.service, identity.tenant_id, identity.scopes) != (
        MONOLITH_SERVICE,
        tenant_id,
        [WHOAMI_SCOPE],
    ):
        raise TrackerResponseError("Unexpected Tracker identity")
    return identity
