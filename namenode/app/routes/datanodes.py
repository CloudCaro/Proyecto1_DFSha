from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DataNode
from app.config import HEARTBEAT_TIMEOUT


router = APIRouter(
    prefix="/datanodes",
    tags=["DataNodes"]
)


def current_time():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================================
# MODELO PARA REGISTRAR UN DATANODE
# ==========================================

class DataNodeRegistration(BaseModel):
    node_id: str
    host: str
    port: int
    capacity: int = 0


# ==========================================
# REGISTRO DE DATANODES
# ==========================================

@router.post("/register")
def register_datanode(
    data: DataNodeRegistration,
    db: Session = Depends(get_db)
):

    node = db.query(DataNode).filter(
        DataNode.node_id == data.node_id
    ).first()

    if node:
        node.host = data.host
        node.port = data.port
        node.capacity = data.capacity
        node.status = "ACTIVE"
        node.last_heartbeat = current_time()

    else:
        node = DataNode(
            node_id=data.node_id,
            host=data.host,
            port=data.port,
            capacity=data.capacity,
            used_space=0,
            status="ACTIVE",
            last_heartbeat=current_time()
        )

        db.add(node)

    db.commit()
    db.refresh(node)

    return {
        "message": "Datanode registrado correctamente",
        "node_id": node.node_id,
        "status": node.status
    }


# ==========================================
# RECEPCIÓN DE HEARTBEATS
# ==========================================

@router.post("/{node_id}/heartbeat")
def receive_heartbeat(
    node_id: str,
    db: Session = Depends(get_db)
):

    node = db.query(DataNode).filter(
        DataNode.node_id == node_id
    ).first()

    if not node:
        raise HTTPException(
            status_code=404,
            detail="Datanode no registrado"
        )

    node.last_heartbeat = current_time()
    node.status = "ACTIVE"

    db.commit()

    return {
        "message": "Heartbeat recibido",
        "node_id": node.node_id,
        "status": node.status,
        "timestamp": node.last_heartbeat
    }


# ==========================================
# CONSULTA DEL ESTADO DE LOS DATANODES
# ==========================================

@router.get("/")
def get_datanodes(
    db: Session = Depends(get_db)
):

    nodes = db.query(DataNode).all()

    now = current_time()

    result = []

    for node in nodes:

        if node.last_heartbeat is None:
            status = "INACTIVE"

        else:
            elapsed = (
                now - node.last_heartbeat
            ).total_seconds()

            status = (
                "ACTIVE"
                if elapsed <= HEARTBEAT_TIMEOUT
                else "INACTIVE"
            )

        if node.status != status:
            node.status = status

        result.append({
            "node_id": node.node_id,
            "host": node.host,
            "port": node.port,
            "status": status,
            "capacity": node.capacity,
            "used_space": node.used_space,
            "last_heartbeat": node.last_heartbeat
        })

    db.commit()

    return {
        "total_nodes": len(result),
        "nodes": result
    }


# ==========================================
# CONSULTA DE UN DATANODE ESPECÍFICO
# ==========================================

@router.get("/{node_id}")
def get_datanode(
    node_id: str,
    db: Session = Depends(get_db)
):

    node = db.query(DataNode).filter(
        DataNode.node_id == node_id
    ).first()

    if not node:
        raise HTTPException(
            status_code=404,
            detail="Datanode no encontrado"
        )

    if node.last_heartbeat is None:
        status = "INACTIVE"

    else:
        elapsed = (
            current_time() - node.last_heartbeat
        ).total_seconds()

        status = (
            "ACTIVE"
            if elapsed <= HEARTBEAT_TIMEOUT
            else "INACTIVE"
        )

    return {
        "node_id": node.node_id,
        "host": node.host,
        "port": node.port,
        "status": status,
        "capacity": node.capacity,
        "used_space": node.used_space
    }