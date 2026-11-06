import asyncio

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes import router
from app.heartbeat import heartbeat_loop


@asynccontextmanager
async def lifespan(app: FastAPI):

    heartbeat_task = asyncio.create_task(
        heartbeat_loop()
    )

    yield

    heartbeat_task.cancel()

    try:
        await heartbeat_task

    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="DFSha - DataNode",
    description="Servicio de almacenamiento distribuido",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router)


@app.get("/")
def root():

    return {
        "service": "DFSha DataNode",
        "status": "running"
    }