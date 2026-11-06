import logging
import httpx

from sqlalchemy.orm import Session

from app.models import BlockReplica


logger = logging.getLogger("DFSha-Replication")


# ==========================================
# ELIMINAR UN BLOQUE REMOTO
# ==========================================

def delete_remote_block(node, block_id):

    url = (
        f"http://{node.host}:{node.port}"
        f"/blocks/{block_id}"
    )

    try:

        response = httpx.delete(
            url,
            timeout=10.0
        )

        if response.status_code not in [200, 204, 404]:
            response.raise_for_status()

    except httpx.HTTPError as error:

        logger.error(
            f"No se pudo eliminar {block_id} "
            f"de {node.node_id}: {error}"
        )


# ==========================================
# ELIMINAR RÉPLICAS DE UN BLOQUE
# ==========================================

def cleanup_block_replicas(
    block_id,
    nodes
):

    for node in nodes:

        delete_remote_block(
            node,
            block_id
        )


# ==========================================
# ALMACENAR RÉPLICAS DE UN BLOQUE
# ==========================================

def store_block_replicas(
    db: Session,
    block,
    content: bytes,
    selected_nodes: list
):

    block_id = block.block_id
    expected_hash = block.sha256

    uploaded_nodes = []

    try:

        for node in selected_nodes:

            url = (
                f"http://{node.host}:{node.port}"
                f"/blocks/{block_id}"
            )

            response = httpx.put(
                url,
                content=content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Content-SHA256": expected_hash
                },
                timeout=60.0
            )

            response.raise_for_status()

            # Registrar inmediatamente que el bloque
            # llegó al nodo, para poder limpiarlo
            # si la verificación posterior falla.

            uploaded_nodes.append(node)

            result = response.json()

            received_hash = result.get("sha256")

            if received_hash != expected_hash:

                raise ValueError(
                    f"Hash incorrecto en {node.node_id}"
                )

            # Registrar la réplica en SQLite.

            replica = BlockReplica(
                block_id=block.id,
                datanode_id=node.id,
                status="ACTIVE"
            )

            db.add(replica)

            # Actualizar el espacio utilizado.

            node.used_space += len(content)

            logger.info(
                f"Bloque {block_id} almacenado "
                f"correctamente en {node.node_id}"
            )

        return uploaded_nodes

    except Exception as error:

        # Si una réplica falla, eliminar las copias
        # que ya se hayan enviado para este bloque.

        cleanup_block_replicas(
            block_id,
            uploaded_nodes
        )

        raise RuntimeError(
            f"No se pudieron almacenar todas las réplicas "
            f"del bloque {block_id}: {error}"
        ) from error


# ==========================================
# CONSULTAR RÉPLICAS DE UN BLOQUE
# ==========================================

def get_block_replicas(
    db: Session,
    block_id: int
):

    replicas = db.query(BlockReplica).filter(
        BlockReplica.block_id == block_id,
        BlockReplica.status == "ACTIVE"
    ).all()

    return replicas
 