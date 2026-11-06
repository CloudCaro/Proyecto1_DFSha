import uuid
import logging

from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.models import (
    User,
    FileMetadata,
    WriteSession,
    FileLock
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


# ==========================================
# OPEN: ABRIR ARCHIVO
# ==========================================

@router.post("/open/{file_id}")
def open_file(
    file_id: int,
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
            detail="Archivo no encontrado o no disponible"
        )

    session_id = uuid.uuid4().hex

    session = WriteSession(
        session_id=session_id,
        user_id=current_user.id,
        file_id=file_metadata.id,
        status="OPEN",
        expires_at=current_time() + timedelta(
            minutes=SESSION_DURATION
        )
    )

    db.add(session)
    db.commit()

    return {
        "message": "Archivo abierto correctamente",
        "session_id": session_id,
        "file_id": file_metadata.id,
        "filename": file_metadata.name,
        "size": file_metadata.size,
        "expires_at": session.expires_at.isoformat()
    }


# ==========================================
# CLOSE: CERRAR SESIÓN
# ==========================================

@router.post("/close/{session_id}")
def close_file(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = db.query(WriteSession).filter(
        WriteSession.session_id == session_id,
        WriteSession.user_id == current_user.id
    ).first()

    if not session:

        raise HTTPException(
            status_code=404,
            detail="Sesión no encontrada"
        )

    if session.status != "OPEN":

        raise HTTPException(
            status_code=409,
            detail="La sesión no está abierta"
        )

    session.status = "CLOSED"
    session.completed_at = current_time()

    db.commit()

    return {
        "message": "Sesión cerrada correctamente",
        "session_id": session_id
    }


# ==========================================
# READ: LEER CONTENIDO DEL ARCHIVO
# ==========================================

@router.get("/read/{session_id}")
def read_file(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    length: int = Query(default=4096, gt=0, le=4 * 1024 * 1024),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = db.query(WriteSession).filter(
        WriteSession.session_id == session_id,
        WriteSession.user_id == current_user.id
    ).first()

    if not session or session.status != "OPEN":

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

    file_metadata = db.query(FileMetadata).filter(
        FileMetadata.id == session.file_id,
        FileMetadata.owner_id == current_user.id,
        FileMetadata.status == "ACTIVE"
    ).first()

    if not file_metadata:

        raise HTTPException(
            status_code=404,
            detail="Archivo no disponible"
        )

    if offset >= file_metadata.size:

        return {
            "file_id": file_metadata.id,
            "offset": offset,
            "bytes_read": 0,
            "content_hex": ""
        }

    try:

        # Reconstruir el archivo verificando cada bloque.

        content = bytearray()

        for block in file_metadata.blocks:

            block_content = retrieve_block(block)

            content.extend(block_content)

        content = bytes(content)

        # Verificar integridad del archivo completo.

        import hashlib

        if hashlib.sha256(content).hexdigest() != file_metadata.sha256:

            raise RuntimeError(
                "La integridad del archivo no pudo verificarse"
            )

        # Leer el segmento solicitado.

        result = content[offset:offset + length]

        return {
            "file_id": file_metadata.id,
            "filename": file_metadata.name,
            "offset": offset,
            "bytes_read": len(result),
            "content_hex": result.hex()
        }

    except Exception as error:

        logger.exception(
            "Error leyendo archivo %s",
            file_metadata.id
        )

        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el archivo: {error}"
        )


# ==========================================
# LOCK: BLOQUEO EXCLUSIVO
# ==========================================

@router.post("/lock/{file_id}")
def lock_file(
    file_id: int,
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

    existing_lock = db.query(FileLock).filter(
        FileLock.file_id == file_id
    ).first()

    if existing_lock:

        if existing_lock.expires_at > current_time():

            if existing_lock.user_id == current_user.id:

                raise HTTPException(
                    status_code=409,
                    detail="El usuario ya tiene un bloqueo activo"
                )

            raise HTTPException(
                status_code=423,
                detail="El archivo está bloqueado por otro usuario"
            )

        # El bloqueo anterior expiró.

        db.delete(existing_lock)
        db.flush()

    lock_token = uuid.uuid4().hex

    new_lock = FileLock(
        file_id=file_id,
        user_id=current_user.id,
        lock_token=lock_token,
        acquired_at=current_time(),
        expires_at=current_time() + timedelta(
            seconds=LOCK_DURATION
        )
    )

    db.add(new_lock)
    db.commit()

    return {
        "message": "Bloqueo adquirido correctamente",
        "file_id": file_id,
        "lock_token": lock_token,
        "expires_in_seconds": LOCK_DURATION
    }


# ==========================================
# UNLOCK: LIBERAR BLOQUEO
# ==========================================

@router.post("/unlock/{file_id}")
def unlock_file(
    file_id: int,
    lock_token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    existing_lock = db.query(FileLock).filter(
        FileLock.file_id == file_id,
        FileLock.user_id == current_user.id,
        FileLock.lock_token == lock_token
    ).first()

    if not existing_lock:

        raise HTTPException(
            status_code=404,
            detail="No se encontró un bloqueo válido para este usuario"
        )

    db.delete(existing_lock)
    db.commit()

    return {
        "message": "Bloqueo liberado correctamente",
        "file_id": file_id
    }