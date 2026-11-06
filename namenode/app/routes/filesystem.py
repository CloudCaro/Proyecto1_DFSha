from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

from app.security import get_current_user

from app.metadata import (
    get_root_directory,
    create_directory,
    list_directory,
    delete_directory
)


router = APIRouter(
    prefix="/filesystem",
    tags=["File System"]
)


# ==========================================
# MODELO PARA CREAR DIRECTORIOS
# ==========================================

class DirectoryRequest(BaseModel):

    parent_id: int

    name: str = Field(
        min_length=1,
        max_length=255
    )


# ==========================================
# CONSULTAR DIRECTORIO RAÍZ
# ==========================================

@router.get("/root")
def root_directory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    directory = get_root_directory(
        db,
        current_user.id
    )

    return {
        "id": directory.id,
        "name": directory.name
    }


# ==========================================
# CREAR DIRECTORIO
# ==========================================

@router.post("/mkdir")
def mkdir(
    data: DirectoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    directory = create_directory(
        db,
        current_user.id,
        data.parent_id,
        data.name
    )

    return {
        "message": "Directorio creado correctamente",
        "id": directory.id,
        "name": directory.name
    }


# ==========================================
# LISTAR DIRECTORIO
# ==========================================

@router.get("/ls/{directory_id}")
def ls(
    directory_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    return list_directory(
        db,
        current_user.id,
        directory_id
    )


# ==========================================
# ELIMINAR DIRECTORIO
# ==========================================

@router.delete("/rmdir/{directory_id}")
def rmdir(
    directory_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    return delete_directory(
        db,
        current_user.id,
        directory_id
    )