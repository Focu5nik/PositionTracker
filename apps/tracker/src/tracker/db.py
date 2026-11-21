import os
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def database_url() -> URL:
    return URL.create(
        "postgresql+psycopg",
        host=os.environ["TRACKER_DB_HOST"],
        database=os.environ["TRACKER_DB_NAME"],
        username=os.environ["TRACKER_DB_USER"],
        password=os.environ["TRACKER_DB_PASSWORD"],
        query={"connect_timeout": "2"},
    )


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with sessions() as session:
        yield session
