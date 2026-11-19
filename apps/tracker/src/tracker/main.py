import os

from fastapi import FastAPI, Response
from psycopg import AsyncConnection, OperationalError

app = FastAPI(title="PositionTracker API")


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


async def check_database() -> None:
    connection = await AsyncConnection.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=2,
    )
    async with connection:
        await connection.execute("SELECT 1")


@app.get("/health/ready", responses={503: {"description": "Database unavailable"}})
async def ready(response: Response) -> dict[str, str]:
    try:
        await check_database()
    except OperationalError:
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ready"}
