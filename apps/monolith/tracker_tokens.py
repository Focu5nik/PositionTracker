from time import time

import jwt

from apps.tracker_contract import (
    DEV_ISSUER,
    DEV_SIGNING_ALGORITHM,
    MAX_TENANT_ID,
    MONOLITH_SERVICE,
    TRACKER_AUDIENCE,
    valid_dev_signing_key,
)


def issue_tracker_token(*, tenant_id: int, scopes: list[str], signing_key: str) -> str:
    if type(tenant_id) is not int or not 0 < tenant_id <= MAX_TENANT_ID:
        raise ValueError("Tracker tenant ID is out of range")
    if not valid_dev_signing_key(signing_key):
        raise ValueError("Tracker signing key must contain at least 32 bytes")

    return jwt.encode(
        {
            "iss": DEV_ISSUER,
            "aud": TRACKER_AUDIENCE,
            "sub": MONOLITH_SERVICE,
            "exp": int(time()) + 60,
            "tenant_id": tenant_id,
            "scopes": scopes,
        },
        signing_key,
        algorithm=DEV_SIGNING_ALGORITHM,
    )
