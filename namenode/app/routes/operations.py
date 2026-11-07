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
    Block,
    BlockReplica,
    current_time
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


def get_session_or_404(db, session_id, user_id):

    session = db.query(WriteSession).filter(
        WriteSession.session_id == session_id,
        WriteSession.user_id == user_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Sesión no encontrada"
        )

    if session.status not in (
        "OPEN_READ",
        "OPEN_WRITE"
    ):
        raise HTTPException(
            status_code=409,
            detail="La sesión no está abierta"
        )

    if session.expires_at <= current_time():
        session.status = "EXPIRED"
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="La sesión ha expirado"
        )

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
        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado"
        )

    version = db.query(FileVersion).filter(
        FileVersion.file_id == file_id,
        FileVersion.version_number == file_metadata.version,
        FileVersion.status == "ACTIVE"
    ).first()

    if not version:
        raise HTTPException(
            status_code=500,
            detail="No existe la versión activa del archivo"
        )

    if mode == "w":

        lock = db.query(FileLock).filter(
            FileLock.file_id == file_id
        ).first()

        if lock and lock.expires_at > current_time():
            raise HTTPException(
                status_code=423,
                detail="El archivo ya está bloqueado"
            )

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
        expires_at=current_time() + timedelta(
            minutes=SESSION_DURATION
        )
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
    length: int = Query(
        default=4096,
        gt=0,
        le=4 * 1024 * 1024
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = get_session_or_404(
        db,
        session_id,
        current_user.id
    )

    if session.status != "OPEN_READ":
        raise HTTPException(
            status_code=409,
            detail="La sesión no está abierta en modo lectura"
        )

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
        raise HTTPException(
            status_code=404,
            detail="La versión de lectura no está disponible"
        )

    if offset >= version.size:
        return {
            "file_id": session.file_id,
            "version": version.version_number,
            "offset": offset,
            "bytes_read": 0,
            "content_hex": ""
        }

    start = offset
    end = min(
        offset + length,
        version.size
    )

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

            local_start = max(
                start - block_start,
                0
            )

            local_end = min(
                end - block_start,
                len(block_content)
            )

            result.extend(
                block_content[local_start:local_end]
            )

        if len(result) != end - start:
            raise RuntimeError(
                "La cantidad de bytes leídos no coincide con el rango solicitado"
            )

        return {
            "file_id": session.file_id,
            "version": version.version_number,
            "offset": offset,
            "bytes_read": len(result),
            "content_hex": bytes(result).hex()
        }

    except Exception as error:

        logger.exception(
            "Error leyendo versión %s",
            version.id
        )

        raise HTTPException(
            status_code=500,
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

        # Si hay una versión pendiente, CLOSE debe publicarla.
        pending_version = None

        if session.version_id:
            pending_version = db.query(FileVersion).filter(
                FileVersion.id == session.version_id,
                FileVersion.file_id == session.file_id,
                FileVersion.status == "PENDING"
            ).first()

        if pending_version:

            if not lock:
                raise HTTPException(
                    status_code=423,
                    detail="No existe un bloqueo para confirmar la escritura"
                )

            if lock.expires_at <= current_time():
                db.delete(lock)
                db.commit()

                raise HTTPException(
                    status_code=423,
                    detail="El bloqueo expiró antes de confirmar la escritura"
                )

            file_metadata = db.query(FileMetadata).filter(
                FileMetadata.id == session.file_id,
                FileMetadata.owner_id == current_user.id,
                FileMetadata.status == "ACTIVE"
            ).with_for_update().first()

            if not file_metadata:
                raise HTTPException(
                    status_code=404,
                    detail="Archivo no disponible para publicar la versión"
                )

            # Control de concurrencia:
            # la versión anterior debe seguir siendo la publicada.
            expected_version = pending_version.version_number - 1

            if file_metadata.version != expected_version:
                raise HTTPException(
                    status_code=409,
                    detail="El archivo cambió desde que se inició el reemplazo"
                )

            # Verificar que todos los bloques tengan las réplicas requeridas.
            version_blocks = db.query(VersionBlock).filter(
                VersionBlock.version_id == pending_version.id
            ).all()

            for version_block in version_blocks:

                active_replicas = db.query(BlockReplica).filter(
                    BlockReplica.block_id == version_block.block_id,
                    BlockReplica.status == "ACTIVE"
                ).count()

                if active_replicas < 2:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "No se puede publicar la versión: "
                            "un bloque no tiene las dos réplicas requeridas"
                        )
                    )

            old_version = db.query(FileVersion).filter(
                FileVersion.file_id == file_metadata.id,
                FileVersion.version_number == file_metadata.version,
                FileVersion.status == "ACTIVE"
            ).first()

            if not old_version:
                raise HTTPException(
                    status_code=500,
                    detail="No se encontró la versión anterior activa"
                )

            old_version.status = "RETAINED"

            pending_version.status = "ACTIVE"

            file_metadata.size = pending_version.size
            file_metadata.sha256 = pending_version.sha256
            file_metadata.version = pending_version.version_number

            db.delete(lock)

        elif lock:
            # Si no hubo reemplazo, CLOSE solo libera el bloqueo.
            db.delete(lock)

    session.status = "CLOSED"
    session.completed_at = current_time()

    db.commit()

    return {
        "message": "Sesión cerrada correctamente",
        "session_id": session_id,
        "write_committed": bool(
            session.mode == "w" and pending_version
        ) if session.mode == "w" else False
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
            status_code=409,
            detail="Se necesita una sesión abierta en modo escritura"
        )

    now = current_time()

    existing = db.query(FileLock).filter(
        FileLock.file_id == file_id
    ).first()

    if existing and existing.expires_at > now:
        raise HTTPException(
            status_code=423,
            detail="El archivo ya tiene un bloqueo activo"
        )

    if existing:
        db.delete(existing)
        db.flush()

    token = uuid.uuid4().hex

    lock = FileLock(
        file_id=file_id,
        user_id=current_user.id,
        lock_token=token,
        acquired_at=now,
        expires_at=now + timedelta(
            seconds=LOCK_DURATION
        )
    )

    db.add(lock)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=423,
            detail="Otro usuario adquirió el bloqueo"
        )

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
        raise HTTPException(
            status_code=404,
            detail="Bloqueo no encontrado"
        )

    if lock.expires_at <= current_time():
        db.delete(lock)
        db.commit()

        raise HTTPException(
            status_code=410,
            detail="El bloqueo ha expirado"
        )

    db.delete(lock)
    db.commit()

    return {
        "message": "Bloqueo liberado correctamente",
        "file_id": file_id
    }