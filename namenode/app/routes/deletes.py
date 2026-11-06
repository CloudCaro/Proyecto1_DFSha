import logging
import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db

from app.models import (
    User,
    FileMetadata,
    FileLock,
    WriteSession
)

from app.security import get_current_user


router = APIRouter(
    prefix="/deletes",
    tags=["File Management"]
)

logger = logging.getLogger("DFSha-Deletes")


@router.delete("/file/{file_id}")
def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    file_metadata = db.query(FileMetadata).filter(
        FileMetadata.id == file_id,
        FileMetadata.owner_id == current_user.id
    ).first()

    if not file_metadata:
        raise HTTPException(404, "Archivo no encontrado")

    if file_metadata.status not in ("ACTIVE", "DELETING"):
        raise HTTPException(409, "El archivo no se puede eliminar")

    from app.models import current_time

    now = current_time()

    active_lock = db.query(FileLock).filter(
        FileLock.file_id == file_id,
        FileLock.expires_at > now
    ).first()

    if active_lock:
        raise HTTPException(
            423,
            "No se puede eliminar un archivo bloqueado"
        )

    active_sessions = db.query(WriteSession).filter(
        WriteSession.file_id == file_id,
        WriteSession.status.in_(["OPEN_READ", "OPEN_WRITE"]),
        WriteSession.expires_at > now
    ).count()

    if active_sessions:
        raise HTTPException(
            409,
            "No se puede eliminar: existen sesiones activas"
        )

    filename = file_metadata.name

    file_metadata.status = "DELETING"
    db.commit()

    deleted_replicas = 0
    errors = []

    try:

        # Los bloques actuales incluyen también los bloques
        # de versiones anteriores que todavía se conservan.
        for block in list(file_metadata.blocks):

            for replica in list(block.replicas):

                if replica.status == "DELETED":
                    continue

                node = replica.datanode

                url = (
                    f"http://{node.host}:{node.port}"
                    f"/blocks/{block.block_id}"
                )

                try:

                    response = httpx.delete(
                        url,
                        timeout=10.0
                    )

                    if response.status_code not in (200, 204, 404):
                        response.raise_for_status()

                    replica.status = "DELETED"

                    node.used_space = max(
                        0,
                        node.used_space - block.size
                    )

                    db.commit()

                    deleted_replicas += 1

                except Exception as error:

                    errors.append({
                        "block_id": block.block_id,
                        "node_id": node.node_id,
                        "error": str(error)
                    })

                    logger.exception(
                        "Error eliminando bloque %s",
                        block.block_id
                    )

        if errors:
            raise HTTPException(
                503,
                detail={
                    "message": "Eliminación parcial. Puedes reintentar.",
                    "deleted_replicas": deleted_replicas,
                    "errors": errors
                }
            )

        db.delete(file_metadata)
        db.commit()

        return {
            "message": "Archivo eliminado correctamente",
            "filename": filename,
            "deleted_replicas": deleted_replicas
        }

    except HTTPException:
        raise

    except Exception as error:

        db.rollback()

        logger.exception("Error eliminando archivo")

        raise HTTPException(
            500,
            detail=f"No se pudo eliminar el archivo: {error}"
        )