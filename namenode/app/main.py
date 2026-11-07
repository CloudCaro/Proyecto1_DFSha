import logging
import threading
import time

from fastapi import FastAPI

from app.routes.operations import router as operations_router
from app.routes.deletes import router as deletes_router
from app.routes.reads import router as reads_router
from app.routes.writes import router as writes_router
from app.database import create_tables, SessionLocal
from app.routes.datanodes import router as datanodes_router
from app.routes.auth import router as auth_router
from app.routes.filesystem import router as filesystem_router
from app.replication import recover_under_replicated_blocks
from app.config import HEARTBEAT_INTERVAL

logger = logging.getLogger("DFSha-Recovery")
RECOVERY_INTERVAL = max(HEARTBEAT_INTERVAL * 2, 10)


def recovery_loop():
    while True:
        db = SessionLocal()
        try:
            result = recover_under_replicated_blocks(db)
            if result["replicas_created"]:
                logger.info("Recuperación automática: %s réplicas creadas",
                            result["replicas_created"])
        except Exception:
            db.rollback()
            logger.exception("Error durante recuperación automática")
        finally:
            db.close()
        time.sleep(RECOVERY_INTERVAL)


app = FastAPI(
    title="DFSha - Namenode",
    description="Servicio de coordinación del sistema de archivos distribuido",
    version="1.0.0"
)


@app.on_event("startup")
def startup():
    create_tables()
    worker = threading.Thread(
        target=recovery_loop,
        name="dfsha-replication-recovery",
        daemon=True
    )
    worker.start()


app.include_router(datanodes_router)


@app.get("/")
def root():
    return {"service": "DFSha Namenode", "status": "running"}


@app.get("/health")
def health():
    return {"service": "Namenode", "status": "healthy"}


app.include_router(auth_router)
app.include_router(filesystem_router)
app.include_router(writes_router)
app.include_router(reads_router)
app.include_router(deletes_router)
app.include_router(operations_router)
