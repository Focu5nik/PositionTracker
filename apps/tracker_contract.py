from pydantic import BaseModel

DEV_ISSUER = "positiontracker-dev"
DEV_SIGNING_ALGORITHM = "HS256"
TRACKER_AUDIENCE = "positiontracker-tracker"
MONOLITH_SERVICE = "positiontracker-monolith"
INTERNAL_API_PREFIX = "/internal/v1"
WHOAMI_SCOPE = "tracker:whoami"
MAX_TENANT_ID = 2**63 - 1


def valid_dev_signing_key(key: str) -> bool:
    return len(key.strip().encode("utf-8")) >= 32


class Identity(BaseModel):
    service: str
    tenant_id: int
    scopes: list[str]
    database: str
