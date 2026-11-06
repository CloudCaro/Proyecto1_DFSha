import logging

import httpx
 
from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session
 
from app.database import get_db

from app.models import User, FileMetadata

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
 
    # Buscar el archivo y verificar su propietario.
 
    file_metadata = db.query(FileMetadata).filter(

        FileMetadata.id == file_id,

        FileMetadata.owner_id == current_user.id

    ).first()
 
    if not file_metadata:
 
        raise HTTPException(

            status_code=404,

            detail="Archivo no encontrado"

        )
 
    if file_metadata.status not in ("ACTIVE", "DELETING"):
 
        raise HTTPException(

            status_code=409,

            detail="El archivo no se encuentra en un estado eliminable"

        )
 
    # Marcar el archivo para eliminación.
 
    file_metadata.status = "DELETING"

    db.commit()
 
    deleted_replicas = 0

    errors = []
 
    try:
 
        # Recorrer todos los bloques del archivo.
 
        for block in file_metadata.blocks:
 
            for replica in block.replicas:
 
                # Ignorar réplicas que ya fueron eliminadas.
 
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
 
                    # Si el bloque ya no existe,

                    # consideramos que está eliminado.
 
                    if response.status_code not in (200, 204, 404):

                        response.raise_for_status()
 
                    replica.status = "DELETED"
 
                    # Actualizar el espacio utilizado.
 
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

                        "Error eliminando bloque %s en %s",

                        block.block_id,

                        node.node_id

                    )
 
        # Si alguna réplica no pudo eliminarse,

        # conservar los metadatos para permitir reintentar.
 
        if errors:
 
            raise HTTPException(

                status_code=503,

                detail={

                    "message": "Eliminación parcial. Se puede reintentar.",

                    "deleted_replicas": deleted_replicas,

                    "errors": errors

                }

            )
 
        # Eliminar los metadatos.

        # Las relaciones tienen cascade delete-orphan.
 
        db.delete(file_metadata)

        db.commit()
 
        return {

            "message": "Archivo eliminado correctamente",

            "filename": file_metadata.name,

            "deleted_replicas": deleted_replicas

        }
 
    except HTTPException:

        raise
 
    except Exception as error:
 
        db.rollback()
 
        logger.exception(

            "Error durante la eliminación del archivo"

        )
 
        raise HTTPException(

            status_code=500,

            detail=f"No se pudo eliminar el archivo: {error}"

        )
 