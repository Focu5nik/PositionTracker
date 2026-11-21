from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def read_database_name(session: AsyncSession) -> str:
    result = await session.scalars(select(func.current_database(type_=String())))
    return result.one()
