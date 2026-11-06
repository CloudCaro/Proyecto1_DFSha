from datetime import datetime, timezone

from fastapi import HTTPException, status

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import DataNode, BlockReplica
from app.config import (
    HEARTBEAT_TIMEOUT,
    REPLICATION_FACTOR
)


# ==========================================
# OBTENER HORA ACTUAL
# ==========================================

def current_time():

    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


# ==========================================
# CONSULTAR DATANODES DISPONIBLES
# ==========================================

def get_available_datanodes(
    db: Session,
    block_size: int
):

    now = current_time()

    nodes = db.query(DataNode).filter(
        DataNode.status == "ACTIVE"
    ).all()

    available_nodes = []

    for node in nodes:

        if node.last_heartbeat is None:
            continue

        elapsed = (
            now - node.last_heartbeat
        ).total_seconds()

        # Verificar que el heartbeat siga vigente

        if elapsed > HEARTBEAT_TIMEOUT:
            continue

        # Calcular espacio disponible

        free_space = node.capacity - node.used_space

        if free_space < block_size:
            continue

        available_nodes.append(node)

    return available_nodes


# ==========================================
# CONTAR RÉPLICAS POR DATANODE
# ==========================================

def count_replicas_per_node(db: Session):

    results = db.query(
        BlockReplica.datanode_id,
        func.count(BlockReplica.id)
    ).filter(
        BlockReplica.status == "ACTIVE"
    ).group_by(
        BlockReplica.datanode_id
    ).all()

    return {
        node_id: count
        for node_id, count in results
    }


# ==========================================
# SELECCIONAR DATANODES
# ==========================================

def select_datanodes(
    db: Session,
    block_size: int,
    replication_factor: int = REPLICATION_FACTOR
):

    if block_size <= 0:

        raise HTTPException(
            status_code=400,
            detail="El tamaño del bloque debe ser mayor que cero"
        )

    if replication_factor <= 0:

        raise HTTPException(
            status_code=400,
            detail="El factor de replicación debe ser mayor que cero"
        )

    nodes = get_available_datanodes(
        db,
        block_size
    )

    if len(nodes) < replication_factor:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No hay suficientes Datanodes disponibles "
                "para cumplir el factor de replicación"
            )
        )

    replica_counts = count_replicas_per_node(db)

    # Ordenar primero por cantidad de réplicas almacenadas
    # y después por porcentaje de utilización.

    nodes.sort(
        key=lambda node: (
            replica_counts.get(node.id, 0),

            (
                node.used_space / node.capacity
                if node.capacity > 0
                else 1
            ),

            node.node_id
        )
    )

    # Seleccionar nodos diferentes

    selected_nodes = nodes[:replication_factor]

    return selected_nodes


# ==========================================
# GENERAR PLAN DE DISTRIBUCIÓN
# ==========================================

def create_block_placement(
    db: Session,
    block_sizes: list[int]
):

    placement = []

    # Llevar un registro temporal de la carga
    # durante la planificación actual.

    temporary_load = {}

    nodes = get_available_datanodes(
        db,
        max(block_sizes)
    )

    for node in nodes:

        temporary_load[node.id] = {
            "replicas": 0,
            "used_space": node.used_space,
            "capacity": node.capacity
        }

    for index, block_size in enumerate(block_sizes):

        available_nodes = get_available_datanodes(
            db,
            block_size
        )

        # Ordenar considerando la carga real
        # y la carga temporal de esta planificación.

        available_nodes.sort(
            key=lambda node: (
                temporary_load[node.id]["replicas"],

                (
                    temporary_load[node.id]["used_space"]
                    / temporary_load[node.id]["capacity"]
                    if temporary_load[node.id]["capacity"] > 0
                    else 1
                ),

                node.node_id
            )
        )

        if len(available_nodes) < REPLICATION_FACTOR:

            raise HTTPException(
                status_code=503,
                detail="No hay suficientes Datanodes disponibles"
            )

        selected_nodes = available_nodes[:REPLICATION_FACTOR]

        replicas = []

        for node in selected_nodes:

            replicas.append({
                "node_id": node.node_id,
                "host": node.host,
                "port": node.port
            })

            temporary_load[node.id]["replicas"] += 1

            temporary_load[node.id]["used_space"] += block_size

        placement.append({
            "block_index": index,
            "block_size": block_size,
            "replicas": replicas
        })

    return placement