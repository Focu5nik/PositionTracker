from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from apps.tracker_contract import (
    DEV_ISSUER,
    DEV_SIGNING_ALGORITHM,
    MAX_TENANT_ID,
    TRACKER_AUDIENCE,
)

bearer = HTTPBearer(auto_error=False)
NonBlankString = Annotated[str, StringConstraints(pattern=r"\S")]


class ServicePrincipal(BaseModel):
    sub: NonBlankString
    tenant_id: Annotated[int, Field(gt=0, le=MAX_TENANT_ID)]
    scopes: list[NonBlankString]
    exp: int


async def get_service_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ServicePrincipal:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing service token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    key: str = request.app.state.dev_signing_key
    try:
        claims = jwt.decode(
            credentials.credentials,
            key,
            algorithms=[DEV_SIGNING_ALGORITHM],
            issuer=DEV_ISSUER,
            audience=TRACKER_AUDIENCE,
            options={
                "require": ["iss", "aud", "exp", "sub", "tenant_id", "scopes"],
                "strict_aud": True,
            },
        )
        return ServicePrincipal.model_validate(claims, strict=True)
    except jwt.InvalidTokenError, ValidationError, TypeError, OverflowError:
        raise unauthorized from None
