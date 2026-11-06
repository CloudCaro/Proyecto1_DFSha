from fastapi import FastAPI

from app.routes.deletes import router as deletes_router
from app.routes.reads import router as reads_router
from app.routes.writes import router as writes_router
from app.database import create_tables
from app.routes.datanodes import router as datanodes_router
from app.routes.auth import router as auth_router
from app.routes.filesystem import router as filesystem_router

app = FastAPI(
    title="DFSha - Namenode",
    description="Servicio de coordinación del sistema de archivos distribuido",
    version="1.0.0"
)


@app.on_event("startup")
def startup():
    create_tables()


app.include_router(datanodes_router)


@app.get("/")
def root():
    return {
        "service": "DFSha Namenode",
        "status": "running"
    }


@app.get("/health")
def health():
    return {
        "service": "Namenode",
        "status": "healthy"
    }

app.include_router(auth_router)
app.include_router(filesystem_router)
app.include_router(writes_router)
app.include_router(reads_router)
app.include_router(deletes_router)