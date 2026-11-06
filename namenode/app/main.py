from fastapi import FastAPI

from app.database import create_tables
from app.routes.datanodes import router as datanodes_router


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