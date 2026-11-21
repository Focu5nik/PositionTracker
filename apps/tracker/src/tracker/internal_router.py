from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tracker_contract import INTERNAL_API_PREFIX, WHOAMI_SCOPE, Identity

from .auth import ServicePrincipal, get_service_principal
from .db import get_db
from .service import describe_identity

router = APIRouter(prefix=INTERNAL_API_PREFIX)


async def require_whoami_scope(
    principal: Annotated[ServicePrincipal, Depends(get_service_principal)],
) -> ServicePrincipal:
    if WHOAMI_SCOPE not in principal.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient scope")
    return principal


@router.get(
    "/whoami",
    name="whoami",
    responses={
        401: {"description": "Invalid or missing service token"},
        403: {"description": "Insufficient scope"},
        503: {"description": "Database unavailable"},
    },
)
async def get_tracker_identity(
    principal: Annotated[ServicePrincipal, Depends(require_whoami_scope)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Identity:
    try:
        return await describe_identity(session, principal)
    except OperationalError, TimeoutError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable"
        ) from None
