import logging
import uuid

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db

from app.models import (
    User,
    FileMetadata,
    FileVersion,
    VersionBlock,
    WriteSession,
    FileLock,
    FileVersion,
    VersionBlock,
    Block,
    BlockReplica
)

from app.security import get_current_user
from app.routes.reads import retrieve_block


router = APIRouter(
    prefix="/operations",
    tags=["File Operations"]
)

logger = logging.getLogger("DFSha-Operations")

SESSION_DURATION = 60
LOCK_DURATION = 30


def current_time():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_session_or_404(db, session_id, user_id):

    session = db.query(WriteSession).filter(
        WriteSession.session_id == session_id,
        WriteSession.user_id == user_id
    ).first()

    if not session:
        raise HTTPException(404, "Sesión no encontrada")

    if session.status not in ("OPEN_READ", "OPEN_WRITE"):
        raise HTTPException(409, "La sesión no está abierta")

    if session.expires_at <= current_time():
        session.status = "EXPIRED"
        db.commit()
        raise HTTPException(401, "La sesión ha expirado")

    return session


@router.post("/open/{file_id}")
def open_file(
    file_id: int,
    mode: str = Query(default="r", regex="^(r|w)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    file_metadata = db.query(FileMetadata).filter(
        FileMetadata.id == file_id,
        FileMetadata.owner_id == current_user.id,
        FileMetadata.status == "ACTIVE"
    ).first()

    if not file_metadata:
        raise HTTPException(404, "Archivo no encontrado")

    version = db.query(FileVersion).filter(
        FileVersion.file_id == file_id,
        FileVersion.version_number == file_metadata.version,
        FileVersion.status == "ACTIVE"
    ).first()

    if not version:
        raise HTTPException(500, "No existe la versión activa del archivo")

    if mode == "w":

        lock = db.query(FileLock).filter(
            FileLock.file_id == file_id
        ).first()

        if lock and lock.expires_at > current_time():
            raise HTTPException(423, "El archivo ya está bloqueado")

        if lock:
            db.delete(lock)
            db.flush()

    session_id = uuid.uuid4().hex

    session = WriteSession(
        session_id=session_id,
        user_id=current_user.id,
        file_id=file_id,
        version_id=version.id,
        mode=mode,
        status="OPEN_READ" if mode == "r" else "OPEN_WRITE",
        expires_at=current_time() + timedelta(minutes=SESSION_DURATION)
    )

    db.add(session)
    db.commit()

    return {
        "message": "Archivo abierto correctamente",
        "session_id": session_id,
        "file_id": file_id,
        "filename": file_metadata.name,
        "mode": mode,
        "version": version.version_number,
        "version_id": version.id,
        "size": version.size
    }


@router.get("/read/{session_id}")
def read_file(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    length: int = Query(default=4096, gt=0, le=4 * 1024 * 1024),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = get_session_or_404(
        db,
        session_id,
        current_user.id
    )

    if session.status != "OPEN_READ":
        raise HTTPException(409, "La sesión no está abierta en modo lectura")

    version = db.query(FileVersion).options(
        joinedload(FileVersion.blocks)
        .joinedload(VersionBlock.block)
        .joinedload(Block.replicas)
        .joinedload(BlockReplica.datanode)
    ).filter(
        FileVersion.id == session.version_id,
        FileVersion.file_id == session.file_id
    ).first()

    if not version:
        raise HTTPException(404, "La versión de lectura no está disponible")

    if offset >= version.size:
        return {
            "file_id": session.file_id,
            "version": version.version_number,
            "offset": offset,
            "bytes_read": 0,
            "content_hex": ""
        }

    start = offset
    end = min(offset + length, version.size)

    result = bytearray()
    cursor = 0

    try:

        for version_block in sorted(
            version.blocks,
            key=lambda item: item.block_index
        ):

            block = version_block.block

            block_start = cursor
            block_end = cursor + block.size

            cursor = block_end

            if block_end <= start or block_start >= end:
                continue

            block_content = retrieve_block(block)

            local_start = max(start - block_start, 0)
            local_end = min(end - block_start, len(block_content))

            result.extend(block_content[local_start:local_end])

        return {
            "file_id": session.file_id,
            "version": version.version_number,
            "offset": offset,
            "bytes_read": len(result),
            "content_hex": bytes(result).hex()
        }

    except Exception as error:

        logger.exception("Error leyendo versión %s", version.id)

        raise HTTPException(
            500,
            detail=f"No se pudo leer el archivo: {error}"
        )


@router.post("/close/{session_id}")
def close_file(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = get_session_or_404(
        db,
        session_id,
        current_user.id
    )

    if session.status == "OPEN_WRITE":

        lock = db.query(FileLock).filter(
            FileLock.file_id == session.file_id,
            FileLock.user_id == current_user.id
        ).first()

        if lock:
            db.delete(lock)

    session.status = "CLOSED"
    session.completed_at = current_time()

    db.commit()

    return {
        "message": "Sesión cerrada correctamente",
        "session_id": session_id
    }


@router.post("/lock/{file_id}")
def lock_file(
    file_id: int,
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = get_session_or_404(
        db,
        session_id,
        current_user.id
    )

    if session.file_id != file_id or session.status != "OPEN_WRITE":
        raise HTTPException(
            409,
            "Se necesita una sesión abierta en modo escritura"
        )

    now = current_time()

    existing = db.query(FileLock).filter(
        FileLock.file_id == file_id
    ).first()

    if existing and existing.expires_at > now:
        raise HTTPException(423, "El archivo ya tiene un bloqueo activo")

    if existing:
        db.delete(existing)
        db.flush()

    token = uuid.uuid4().hex

    lock = FileLock(
        file_id=file_id,
        user_id=current_user.id,
        lock_token=token,
        acquired_at=now,
        expires_at=now + timedelta(seconds=LOCK_DURATION)
    )

    db.add(lock)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(423, "Otro usuario adquirió el bloqueo")

    return {
        "message": "Bloqueo adquirido correctamente",
        "file_id": file_id,
        "lock_token": token,
        "expires_in_seconds": LOCK_DURATION
    }


@router.post("/unlock/{file_id}")
def unlock_file(
    file_id: int,
    lock_token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    lock = db.query(FileLock).filter(
        FileLock.file_id == file_id,
        FileLock.user_id == current_user.id,
        FileLock.lock_token == lock_token
    ).first()

    if not lock:
        raise HTTPException(404, "Bloqueo no encontrado")

    if lock.expires_at <= current_time():
        db.delete(lock)
        db.commit()
        raise HTTPException(410, "El bloqueo ha expirado")

    db.delete(lock)
    db.commit()

    return {
        "message": "Bloqueo liberado correctamente",
        "file_id": file_id
    }