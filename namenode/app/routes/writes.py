import hashlib
import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.models import (
    User,
    FileMetadata,
    Block,
    FileVersion,
    VersionBlock,
    WriteSession,
    FileLock,
    DataNode
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


def split_content(content):
    return [
        content[index:index + BLOCK_SIZE]
        for index in range(0, len(content), BLOCK_SIZE)
    ]


def validate_filename(filename):
    if not filename:
        raise HTTPException(400, "El archivo debe tener un nombre")

    if filename in [".", ".."] or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Nombre de archivo inválido")


def validate_session_and_lock(
    db,
    file_id,
    session_id,
    lock_token,
    user_id
):
    session = db.query(WriteSession).filter(
        WriteSession.session_id == session_id,
        WriteSession.user_id == user_id
    ).first()

    if not session:
        raise HTTPException(404, "Sesión de escritura no encontrada")

    if session.status != "OPEN_WRITE":
        raise HTTPException(409, "La sesión no está abierta en modo escritura")

    if session.file_id != file_id:
        raise HTTPException(409, "La sesión no corresponde a este archivo")

    from app.models import current_time

    now = current_time()

    if session.expires_at <= now:
        session.status = "EXPIRED"
        db.commit()
        raise HTTPException(401, "La sesión ha expirado")

    lock = db.query(FileLock).filter(
        FileLock.file_id == file_id,
        FileLock.user_id == user_id,
        FileLock.lock_token == lock_token
    ).first()

    if not lock:
        raise HTTPException(423, "No tienes el bloqueo del archivo")

    if lock.expires_at <= now:
        db.delete(lock)
        db.commit()
        raise HTTPException(423, "El bloqueo ha expirado")

    return session, lock


def store_new_blocks(db, file_metadata, content):
    blocks_content = split_content(content)

    block_sizes = [len(block) for block in blocks_content]

    placement = create_block_placement(db, block_sizes)

    created_blocks = []
    uploaded_blocks = []

    try:
        last_index = (
        db.query(Block.block_index)
        .filter(Block.file_id == file_metadata.id)
        .order_by(Block.block_index.desc())
        .first()
    )

        physical_index = last_index[0] + 1 if last_index else 0

        for logical_index, block_content in enumerate(blocks_content):
            index = physical_index + logical_index

            block_id = uuid.uuid4().hex

            block_hash = hashlib.sha256(block_content).hexdigest()

            block = Block(
                block_id=block_id,
                block_index=index,
                size=len(block_content),
                sha256=block_hash,
                file_id=file_metadata.id
            )

            db.add(block)
            db.flush()

            selected_node_ids = [
                replica["node_id"]
                for replica in placement[index]["replicas"]
            ]

            selected_nodes = db.query(DataNode).filter(
                DataNode.node_id.in_(selected_node_ids)
            ).all()

            if len(selected_nodes) != len(selected_node_ids):
                raise RuntimeError(
                    "No se encontraron todos los Datanodes seleccionados"
                )

            uploaded_nodes = store_block_replicas(
                db,
                block,
                block_content,
                selected_nodes
            )

            uploaded_blocks.append((block_id, uploaded_nodes))
            created_blocks.append(block)

        return created_blocks, uploaded_blocks

    except Exception:
        for block_id, nodes in uploaded_blocks:
            cleanup_block_replicas(block_id, nodes)

        raise


@router.post("/upload/{directory_id}")
def upload_file(
    directory_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    filename = file.filename
    validate_filename(filename)

    directory = get_directory(
        db,
        current_user.id,
        directory_id
    )

    existing_file = db.query(FileMetadata).filter(
        FileMetadata.directory_id == directory.id,
        FileMetadata.name == filename
    ).first()

    if existing_file:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un archivo con ese nombre. Usa la operación de reemplazo."
        )

    content = file.file.read()
    file_size = len(content)
    file_hash = hashlib.sha256(content).hexdigest()

    uploaded_blocks = []

    try:
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

        blocks, uploaded_blocks = store_new_blocks(
            db,
            new_file,
            content
        )

        version = FileVersion(
            file_id=new_file.id,
            version_number=1,
            size=file_size,
            sha256=file_hash,
            status="ACTIVE"
        )

        db.add(version)
        db.flush()

        for block in blocks:
            db.add(VersionBlock(
                version_id=version.id,
                block_id=block.id,
                block_index=block.block_index
            ))

        new_file.status = "ACTIVE"

        db.commit()

        return {
            "message": "Archivo almacenado correctamente",
            "file_id": new_file.id,
            "filename": filename,
            "size": file_size,
            "sha256": file_hash,
            "version": 1,
            "blocks": len(blocks),
            "status": "ACTIVE"
        }

    except Exception as error:
        for block_id, nodes in uploaded_blocks:
            cleanup_block_replicas(block_id, nodes)

        db.rollback()

        logger.exception("Error durante la escritura inicial")

        raise HTTPException(
            status_code=500,
            detail=f"No se pudo almacenar el archivo: {error}"
        )

    finally:
        file.file.close()


@router.post("/replace/{file_id}")
def replace_file(
    file_id: int,
    session_id: str = Form(...),
    lock_token: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    file_metadata = db.query(FileMetadata).filter(
        FileMetadata.id == file_id,
        FileMetadata.owner_id == current_user.id,
        FileMetadata.status == "ACTIVE"
    ).first()

    if not file_metadata:
        raise HTTPException(404, "Archivo no encontrado o no disponible")

    session, lock = validate_session_and_lock(
        db,
        file_id,
        session_id,
        lock_token,
        current_user.id
    )

    content = file.file.read()
    new_size = len(content)
    new_hash = hashlib.sha256(content).hexdigest()

    uploaded_blocks = []
    created_blocks = []

    try:
        # La versión anterior permanece intacta.
        # Los bloques nuevos se crean con nuevos identificadores.
        created_blocks, uploaded_blocks = store_new_blocks(
            db,
            file_metadata,
            content
        )

        new_version_number = file_metadata.version + 1

        new_version = FileVersion(
            file_id=file_metadata.id,
            version_number=new_version_number,
            size=new_size,
            sha256=new_hash,
            status="ACTIVE"
        )

        db.add(new_version)
        db.flush()

        for logical_index, block in enumerate(created_blocks):
            db.add(VersionBlock(
                version_id=new_version.id,
                block_id=block.id,
                block_index=logical_index
            ))

        # Publicación de la versión: se actualizan los metadatos
        # únicamente después de almacenar todas las réplicas.
        old_version = db.query(FileVersion).filter(
            FileVersion.file_id == file_metadata.id,
            FileVersion.version_number == file_metadata.version
        ).first()

        if old_version:
            old_version.status = "RETAINED"

        file_metadata.size = new_size
        file_metadata.sha256 = new_hash
        file_metadata.version = new_version_number

        session.version_id = new_version.id
        session.status = "COMPLETED"
        session.completed_at = __import__(
            "app.models", fromlist=["current_time"]
        ).current_time()

        db.delete(lock)
        db.commit()

        return {
            "message": "Archivo reemplazado correctamente",
            "file_id": file_metadata.id,
            "filename": file_metadata.name,
            "version": new_version_number,
            "size": new_size,
            "sha256": new_hash,
            "blocks": len(created_blocks),
            "status": "ACTIVE"
        }

    except Exception as error:
        for block_id, nodes in uploaded_blocks:
            cleanup_block_replicas(block_id, nodes)

        db.rollback()

        logger.exception("Error durante el reemplazo del archivo")

        raise HTTPException(
            status_code=500,
            detail=f"No se pudo reemplazar el archivo: {error}"
        )

    finally:
        file.file.close()