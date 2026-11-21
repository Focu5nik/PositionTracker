import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.tracker_contract import valid_dev_signing_key

from .db import database_url, get_db
from .internal_router import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_async_engine(
        database_url(), pool_pre_ping=True, hide_parameters=True
    )
    app.state.sessions = async_sessionmaker(engine)
    try:
        yield
    finally:
        await engine.dispose()


async def live() -> dict[str, str]:
    return {"status": "live"}


async def check_database(session: AsyncSession) -> None:
    await session.execute(text("SELECT 1"))


async def ready(
    response: Response, session: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, str]:
    try:
        await check_database(session)
    except OperationalError, TimeoutError:
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ready"}


def create_app(dev_signing_key: str | None = None) -> FastAPI:
    app = FastAPI(title="PositionTracker API", lifespan=lifespan)
    app.add_api_route("/health/live", live, methods=["GET"])
    app.add_api_route(
        "/health/ready",
        ready,
        methods=["GET"],
        responses={503: {"description": "Database unavailable"}},
    )
    if dev_signing_key is not None:
        if not valid_dev_signing_key(dev_signing_key):
            raise RuntimeError("TRACKER_DEV_SIGNING_KEY must contain at least 32 bytes")
        app.state.dev_signing_key = dev_signing_key
        app.include_router(router)
    return app


app = create_app(
    dev_signing_key=os.getenv("TRACKER_DEV_SIGNING_KEY", "")
    if os.getenv("TRACKER_ENABLE_DEV_WHOAMI") == "1"
    else None
)
