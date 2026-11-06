from fastapi import FastAPI

from app.routes import router
from app.config import DN_ID


app = FastAPI(
    title="DFSha DataNode",
    description="Servicio de almacenamiento distribuido de bloques",
    version="1.0.0"
)


app.include_router(router)


@app.get("/")
def root():

    return {
        "service": "DFSha DataNode",
        "datanode_id": DN_ID,
        "status": "running"
    }