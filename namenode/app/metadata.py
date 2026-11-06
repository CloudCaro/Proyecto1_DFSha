from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.models import Directory, FileMetadata


# ==========================================
# OBTENER DIRECTORIO
# ==========================================

def get_directory(
    db: Session,
    user_id: int,
    directory_id: int
):

    directory = db.query(Directory).filter(
        Directory.id == directory_id,
        Directory.owner_id == user_id
    ).first()

    if not directory:

        raise HTTPException(
            status_code=404,
            detail="Directorio no encontrado"
        )

    return directory


# ==========================================
# OBTENER DIRECTORIO RAÍZ
# ==========================================

def get_root_directory(
    db: Session,
    user_id: int
):

    directory = db.query(Directory).filter(
        Directory.owner_id == user_id,
        Directory.parent_id.is_(None)
    ).first()

    if not directory:

        raise HTTPException(
            status_code=404,
            detail="No existe el directorio raíz"
        )

    return directory


# ==========================================
# CREAR DIRECTORIO
# ==========================================

def create_directory(
    db: Session,
    user_id: int,
    parent_id: int,
    name: str
):

    if not name or name in [".", "..", "/"]:

        raise HTTPException(
            status_code=400,
            detail="Nombre de directorio inválido"
        )

    if "/" in name or "\\" in name:

        raise HTTPException(
            status_code=400,
            detail="El nombre no puede contener separadores"
        )

    parent = get_directory(
        db,
        user_id,
        parent_id
    )

    existing = db.query(Directory).filter(
        Directory.owner_id == user_id,
        Directory.parent_id == parent.id,
        Directory.name == name
    ).first()

    existing_file = db.query(FileMetadata).filter(
        FileMetadata.directory_id == parent.id,
        FileMetadata.name == name
    ).first()

    if existing or existing_file:

        raise HTTPException(
            status_code=409,
            detail="Ya existe un archivo o directorio con ese nombre"
        )

    directory = Directory(
        name=name,
        owner_id=user_id,
        parent_id=parent.id
    )

    db.add(directory)
    db.commit()
    db.refresh(directory)

    return directory


# ==========================================
# LISTAR CONTENIDO DE DIRECTORIO
# ==========================================

def list_directory(
    db: Session,
    user_id: int,
    directory_id: int
):

    directory = get_directory(
        db,
        user_id,
        directory_id
    )

    directories = db.query(Directory).filter(
        Directory.owner_id == user_id,
        Directory.parent_id == directory.id
    ).all()

    files = db.query(FileMetadata).filter(
        FileMetadata.owner_id == user_id,
        FileMetadata.directory_id == directory.id
    ).all()

    return {
        "directory": directory.name,

        "directories": [
            {
                "id": item.id,
                "name": item.name
            }
            for item in directories
        ],

        "files": [
            {
                "id": item.id,
                "name": item.name,
                "size": item.size,
                "status": item.status
            }
            for item in files
        ]
    }


# ==========================================
# ELIMINAR DIRECTORIO VACÍO
# ==========================================

def delete_directory(
    db: Session,
    user_id: int,
    directory_id: int
):

    directory = get_directory(
        db,
        user_id,
        directory_id
    )

    if directory.parent_id is None:

        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar el directorio raíz"
        )

    has_directories = db.query(Directory).filter(
        Directory.parent_id == directory.id
    ).first()

    has_files = db.query(FileMetadata).filter(
        FileMetadata.directory_id == directory.id
    ).first()

    if has_directories or has_files:

        raise HTTPException(
            status_code=409,
            detail="El directorio no está vacío"
        )

    db.delete(directory)
    db.commit()

    return {
        "message": "Directorio eliminado correctamente"
    }