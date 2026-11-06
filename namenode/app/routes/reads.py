import hashlib
import logging
from urllib.parse import quote

import httpx

from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from fastapi.responses import Response

from sqlalchemy.orm import Session

from app.database import get_db

from app.models import (
    User,
    FileMetadata
)

from app.security import get_current_user

from app.config import HEARTBEAT_TIMEOUT

from datetime import datetime, timezone


router = APIRouter(
    prefix="/reads",
    tags=["File Transfer"]
)

logger = logging.getLogger("DFSha-Reads")


# ==========================================
# OBTENER UN BLOQUE DESDE SUS RÉPLICAS
# ==========================================

def retrieve_block(block):

    expected_hash = block.sha256

    # Obtener las réplicas registradas del bloque.

    replicas = block.replicas

    # Priorizar réplicas activas y con heartbeat reciente.

    current_time = datetime.now(timezone.utc).replace(tzinfo=None)

    available_replicas = []

    for replica in replicas:

        node = replica.datanode

        if replica.status != "ACTIVE":
            continue

        if node.status != "ACTIVE":
            continue

        if node.last_heartbeat is None:
            continue

        elapsed = (
            current_time - node.last_heartbeat
        ).total_seconds()

        if elapsed > HEARTBEAT_TIMEOUT:
            continue

        available_replicas.append(node)

    if not available_replicas:

        raise RuntimeError(
            f"No existen réplicas disponibles para el bloque {block.block_id}"
        )

    # Intentar recuperar el bloque desde cada réplica.

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

            # Verificar integridad del bloque.

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
                "No se pudo recuperar el bloque %s desde %s: %s",
                block.block_id,
                node.node_id,
                error
            )

    raise RuntimeError(
        f"No fue posible recuperar ninguna réplica válida "
        f"del bloque {block.block_id}"
    )


# ==========================================
# DESCARGAR Y RECONSTRUIR ARCHIVO
# ==========================================

@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Buscar el archivo verificando que pertenezca al usuario.

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

    try:

        reconstructed_content = bytearray()

        # Los bloques están ordenados por block_index
        # mediante la relación definida en models.py.

        for block in file_metadata.blocks:

            block_content = retrieve_block(block)

            reconstructed_content.extend(
                block_content
            )

        # Convertir el contenido reconstruido a bytes.

        reconstructed_content = bytes(
            reconstructed_content
        )

        # Verificar el tamaño total.

        if len(reconstructed_content) != file_metadata.size:

            raise RuntimeError(
                "El tamaño del archivo reconstruido no coincide"
            )

        # Verificar el hash del archivo completo.

        reconstructed_hash = hashlib.sha256(
            reconstructed_content
        ).hexdigest()

        if reconstructed_hash != file_metadata.sha256:

            raise RuntimeError(
                "El hash del archivo reconstruido no coincide"
            )

        logger.info(
            "Archivo %s descargado correctamente por %s",
            file_metadata.name,
            current_user.username
        )

        return Response(
            content=reconstructed_content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''"
                    f"{quote(file_metadata.name)}"
                ),
                "X-File-SHA256": reconstructed_hash,
                "X-File-Size": str(file_metadata.size)
            }
        )

    except Exception as error:

        logger.exception(
            "Error durante la reconstrucción del archivo"
        )

        raise HTTPException(
            status_code=500,
            detail=f"No se pudo descargar el archivo: {error}"
        )