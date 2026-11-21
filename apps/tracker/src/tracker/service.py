from sqlalchemy.ext.asyncio import AsyncSession

from apps.tracker_contract import Identity

from .auth import ServicePrincipal
from .repository import read_database_name


async def describe_identity(
    session: AsyncSession, principal: ServicePrincipal
) -> Identity:
    async with session.begin():
        database = await read_database_name(session)

    return Identity(
        service=principal.sub,
        tenant_id=principal.tenant_id,
        scopes=principal.scopes,
        database=database,
    )
