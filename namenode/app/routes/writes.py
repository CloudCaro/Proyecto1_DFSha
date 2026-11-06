import hashlib
import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.models import (
    User,
    FileMetadata,
    Block
)

from app.security import get_current_user

from app.metadata import get_directory

from app.scheduler import create_block_placement

from app.replication import (
    store_block_replicas,
    cleanup_block_replicas
)

from app.config import BLOCK_SIZE


router = APIRouter(
    prefix="/writes",
    tags=["File Transfer"]
)

logger = logging.getLogger("DFSha-Writes")


# ==========================================
# SUBIR ARCHIVO
# ==========================================

@router.post("/upload/{directory_id}")
def upload_file(
    directory_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    filename = file.filename

    if not filename:

        raise HTTPException(
            status_code=400,
            detail="El archivo debe tener un nombre"
        )

    if (
        filename in [".", ".."]
        or "/" in filename
        or "\\" in filename
    ):

        raise HTTPException(
            status_code=400,
            detail="Nombre de archivo inválido"
        )

    # Verificar que el directorio pertenezca al usuario.

    directory = get_directory(
        db,
        current_user.id,
        directory_id
    )

    # Evitar archivos con nombres duplicados.

    existing_file = db.query(FileMetadata).filter(
        FileMetadata.directory_id == directory.id,
        FileMetadata.name == filename
    ).first()

    if existing_file:

        raise HTTPException(
            status_code=409,
            detail="Ya existe un archivo con ese nombre"
        )

    content = file.file.read()

    file_size = len(content)

    # Calcular hash del archivo completo.

    file_hash = hashlib.sha256(
        content
    ).hexdigest()

    # Dividir archivo en bloques de 4 MiB.

    blocks_content = [
        content[i:i + BLOCK_SIZE]
        for i in range(0, file_size, BLOCK_SIZE)
    ]

    block_sizes = [
        len(block)
        for block in blocks_content
    ]

    uploaded_blocks = []

    try:

        # Generar plan de distribución.

        placement = create_block_placement(
            db,
            block_sizes
        )

        # Crear metadatos del archivo.

        new_file = FileMetadata(
            name=filename,
            size=file_size,
            sha256=file_hash,
            owner_id=current_user.id,
            directory_id=directory.id,
            version=1,
            status="UPLOADING"
        )

        db.add(new_file)
        db.flush()

        # Procesar cada bloque.

        for index, block_content in enumerate(blocks_content):

            block_id = uuid.uuid4().hex

            block_hash = hashlib.sha256(
                block_content
            ).hexdigest()

            block = Block(
                block_id=block_id,
                block_index=index,
                size=len(block_content),
                sha256=block_hash,
                file_id=new_file.id
            )

            db.add(block)
            db.flush()

            # Obtener los Datanodes seleccionados.

            selected_node_ids = [
                replica["node_id"]
                for replica in placement[index]["replicas"]
            ]

            from app.models import DataNode

            selected_nodes = db.query(DataNode).filter(
                DataNode.node_id.in_(selected_node_ids)
            ).all()

            if len(selected_nodes) != len(selected_node_ids):

                raise RuntimeError(
                    "No se encontraron todos los Datanodes seleccionados"
                )

            # Enviar el bloque y almacenar sus réplicas.

            uploaded_nodes = store_block_replicas(
                db,
                block,
                block_content,
                selected_nodes
            )

            uploaded_blocks.append(
                (block_id, uploaded_nodes)
            )

        # Marcar el archivo como activo solamente
        # cuando todos los bloques fueron almacenados.

        new_file.status = "ACTIVE"

        db.commit()

        return {
            "message": "Archivo almacenado correctamente",
            "filename": filename,
            "size": file_size,
            "sha256": file_hash,
            "blocks": len(blocks_content),
            "replication_factor": 2,
            "status": "ACTIVE"
        }

    except Exception as error:

        # Eliminar los bloques almacenados remotamente
        # si la operación completa falla.

        for block_id, nodes in uploaded_blocks:

            cleanup_block_replicas(
                block_id,
                nodes
            )

        db.rollback()

        logger.exception(
            "Error durante la escritura del archivo"
        )

        raise HTTPException(
            status_code=500,
            detail=f"No se pudo almacenar el archivo: {error}"
        )

    finally:

        file.file.close()
 