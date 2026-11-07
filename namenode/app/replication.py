import logging
import hashlib
import httpx

from sqlalchemy.orm import Session

from app.models import BlockReplica, DataNode, Block
from app.config import HEARTBEAT_TIMEOUT, REPLICATION_FACTOR
from datetime import datetime, timezone

logger = logging.getLogger("DFSha-Replication")


def current_time():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def delete_remote_block(node, block_id):
    url = f"http://{node.host}:{node.port}/blocks/{block_id}"
    try:
        response = httpx.delete(url, timeout=10.0)
        if response.status_code not in [200, 204, 404]:
            response.raise_for_status()
    except httpx.HTTPError as error:
        logger.error("No se pudo eliminar %s de %s: %s",
                     block_id, node.node_id, error)


def cleanup_block_replicas(block_id, nodes):
    for node in nodes:
        delete_remote_block(node, block_id)


def store_block_replicas(db: Session, block, content: bytes, selected_nodes: list):
    block_id = block.block_id
    expected_hash = block.sha256
    uploaded_nodes = []
    try:
        for node in selected_nodes:
            url = f"http://{node.host}:{node.port}/blocks/{block_id}"
            response = httpx.put(
                url, content=content,
                headers={"Content-Type": "application/octet-stream",
                         "X-Content-SHA256": expected_hash},
                timeout=60.0
            )
            response.raise_for_status()
            uploaded_nodes.append(node)
            result = response.json()
            if result.get("sha256") != expected_hash:
                raise ValueError(f"Hash incorrecto en {node.node_id}")

            replica = BlockReplica(
                block_id=block.id, datanode_id=node.id, status="ACTIVE"
            )
            db.add(replica)
            node.used_space += len(content)

            logger.info("Bloque %s almacenado en %s", block_id, node.node_id)
        return uploaded_nodes
    except Exception as error:
        cleanup_block_replicas(block_id, uploaded_nodes)
        raise RuntimeError(
            f"No se pudieron almacenar todas las réplicas del bloque "
            f"{block_id}: {error}"
        ) from error


def get_block_replicas(db: Session, block_id: int):
    return db.query(BlockReplica).filter(
        BlockReplica.block_id == block_id,
        BlockReplica.status == "ACTIVE"
    ).all()


def _node_is_alive(node, now):
    if node.status != "ACTIVE" or node.last_heartbeat is None:
        return False
    return (now - node.last_heartbeat).total_seconds() <= HEARTBEAT_TIMEOUT


def recover_under_replicated_blocks(db: Session):
    """
    Repara bloques que tengan menos réplicas ACTIVE que REPLICATION_FACTOR.
    Lee una copia sana, valida SHA-256 y crea la copia faltante en otro nodo.
    """
    now = current_time()
    nodes = db.query(DataNode).all()

    for node in nodes:
        alive = _node_is_alive(node, now)
        if node.status != ("ACTIVE" if alive else "INACTIVE"):
            node.status = "ACTIVE" if alive else "INACTIVE"

    db.flush()
    healthy_nodes = [n for n in nodes if _node_is_alive(n, now)]
    if not healthy_nodes:
        db.commit()
        return {"blocks_checked": 0, "replicas_created": 0}

    blocks = db.query(Block).all()
    replicas_created = 0
    blocks_checked = 0

    for block in blocks:
        blocks_checked += 1
        replicas = db.query(BlockReplica).filter(
            BlockReplica.block_id == block.id,
            BlockReplica.status == "ACTIVE"
        ).all()

        healthy_replicas = [
            r for r in replicas
            if r.datanode and _node_is_alive(r.datanode, now)
        ]

        # Marcar como INACTIVE las réplicas alojadas en nodos caídos.
        for replica in replicas:
            if not replica.datanode or not _node_is_alive(replica.datanode, now):
                replica.status = "INACTIVE"

        existing_node_ids = {r.datanode_id for r in healthy_replicas}
        if len(existing_node_ids) >= REPLICATION_FACTOR:
            continue

        # Buscar una fuente sana y descargar el bloque.
        content = None
        for replica in healthy_replicas:
            source = replica.datanode
            try:
                response = httpx.get(
                    f"http://{source.host}:{source.port}/blocks/{block.block_id}",
                    timeout=30.0
                )
                response.raise_for_status()
                candidate = response.content
                if hashlib.sha256(candidate).hexdigest() != block.sha256:
                    logger.error("Hash inválido al recuperar %s desde %s",
                                 block.block_id, source.node_id)
                    continue
                content = candidate
                break
            except httpx.HTTPError as error:
                logger.warning("No se pudo leer %s desde %s: %s",
                               block.block_id, source.node_id, error)

        if content is None:
            logger.error("Bloque %s no recuperable: no hay copia sana",
                         block.block_id)
            continue

        destinations = [
            n for n in healthy_nodes
            if n.id not in existing_node_ids
            and (n.capacity - n.used_space) >= block.size
        ]
        destinations.sort(key=lambda n: (
            n.used_space / n.capacity if n.capacity else 1,
            n.node_id
        ))

        missing = REPLICATION_FACTOR - len(existing_node_ids)
        for destination in destinations[:missing]:
            try:
                response = httpx.put(
                    f"http://{destination.host}:{destination.port}/blocks/{block.block_id}",
                    content=content,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Content-SHA256": block.sha256
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                result = response.json()
                if result.get("sha256") != block.sha256:
                    raise ValueError("El Datanode confirmó un hash diferente")

                previous = db.query(BlockReplica).filter(
                    BlockReplica.block_id == block.id,
                    BlockReplica.datanode_id == destination.id
                ).first()

                if previous:
                    previous.status = "ACTIVE"
                else:
                    db.add(BlockReplica(
                        block_id=block.id,
                        datanode_id=destination.id,
                        status="ACTIVE"
                    ))

                destination.used_space += block.size
                existing_node_ids.add(destination.id)
                replicas_created += 1
                db.commit()
                logger.info("Réplica recuperada: bloque %s en %s",
                            block.block_id, destination.node_id)
            except Exception:
                db.rollback()
                logger.exception("Falló recuperación de %s en %s",
                                 block.block_id, destination.node_id)

    db.commit()
    return {
        "blocks_checked": blocks_checked,
        "replicas_created": replicas_created
    }
