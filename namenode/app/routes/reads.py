import hashlib
import logging
from urllib.parse import quote
from datetime import datetime, timezone

import httpx

from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from fastapi.responses import Response

from sqlalchemy.orm import Session, joinedload

from app.database import get_db

from app.models import (
    User,
    FileMetadata,
    FileVersion,
    VersionBlock,
    Block,
    BlockReplica
)

from app.security import get_current_user
from app.config import HEARTBEAT_TIMEOUT


router = APIRouter(
    prefix="/reads",
    tags=["File Transfer"]
)

logger = logging.getLogger("DFSha-Reads")


def retrieve_block(block):
    """
    Recupera un bloque desde alguna de sus réplicas disponibles.
    Verifica su integridad mediante SHA-256.
    """

    expected_hash = block.sha256

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    available_replicas = []

    for replica in block.replicas:

        node = replica.datanode

        if replica.status != "ACTIVE":
            continue

        if node.status != "ACTIVE":
            continue

        if node.last_heartbeat is None:
            continue

        elapsed = (now - node.last_heartbeat).total_seconds()

        if elapsed > HEARTBEAT_TIMEOUT:
            continue

        available_replicas.append(node)

    if not available_replicas:
        raise RuntimeError(
            f"No existen réplicas disponibles para el bloque {block.block_id}"
        )

    for node in available_replicas:

        url = (
            f"http://{node.host}:{node.port}"
            f"/blocks/{block.block_id}"
        )

        try:

            response = httpx.get(
                url,
                timeout=10.0
            )

            response.raise_for_status()

            block_content = response.content

            received_hash = hashlib.sha256(
                block_content
            ).hexdigest()

            if received_hash != expected_hash:

                logger.warning(
                    "Hash incorrecto en bloque %s desde %s",
                    block.block_id,
                    node.node_id
                )

                continue

            return block_content

        except Exception as error:

            logger.warning(
                "No se pudo recuperar bloque %s desde %s: %s",
                block.block_id,
                node.node_id,
                error
            )

    raise RuntimeError(
        f"No fue posible recuperar ninguna réplica válida del bloque {block.block_id}"
    )


def reconstruct_version(version):
    """
    Reconstruye el archivo utilizando exclusivamente
    los bloques asociados a una versión específica.
    """

    content = bytearray()

    ordered_blocks = sorted(
        version.blocks,
        key=lambda item: item.block_index
    )

    for version_block in ordered_blocks:

        block_content = retrieve_block(
            version_block.block
        )

        content.extend(block_content)

    result = bytes(content)

    if len(result) != version.size:

        raise RuntimeError(
            f"El tamaño reconstruido ({len(result)}) "
            f"no coincide con el esperado ({version.size})"
        )

    received_hash = hashlib.sha256(result).hexdigest()

    if received_hash != version.sha256:

        raise RuntimeError(
            "El hash SHA-256 del archivo reconstruido no coincide"
        )

    return result


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Descarga la versión actualmente publicada del archivo.
    """

    file_metadata = db.query(FileMetadata).filter(
        FileMetadata.id == file_id,
        FileMetadata.owner_id == current_user.id
    ).first()

    if not file_metadata:

        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado"
        )

    if file_metadata.status != "ACTIVE":

        raise HTTPException(
            status_code=409,
            detail="El archivo no está disponible para descarga"
        )

    version = db.query(FileVersion).options(
    joinedload(FileVersion.blocks)
    .joinedload(VersionBlock.block)
    .joinedload(Block.replicas)
    .joinedload(BlockReplica.datanode)
    ).filter(
        FileVersion.file_id == file_metadata.id,
        FileVersion.version_number == file_metadata.version,
        FileVersion.status == "ACTIVE"
    ).first()

    if not version:

        raise HTTPException(
            status_code=500,
            detail="No se encontraron los metadatos de la versión activa"
        )

    try:

        content = reconstruct_version(version)

        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''"
                    f"{quote(file_metadata.name)}"
                ),
                "X-File-SHA256": version.sha256,
                "X-File-Size": str(version.size),
                "X-File-Version": str(version.version_number)
            }
        )

    except Exception as error:

        logger.exception(
            "Error durante la descarga del archivo %s",
            file_id
        )

        raise HTTPException(
            status_code=500,
            detail=f"No se pudo descargar el archivo: {error}"
        )