from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from app.database import get_db

from app.models import User, Directory

from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# ==========================================
# MODELO DE REGISTRO
# ==========================================

class RegisterRequest(BaseModel):

    username: str = Field(
        min_length=3,
        max_length=50
    )

    password: str = Field(
        min_length=8,
        max_length=72
    )


# ==========================================
# REGISTRO
# ==========================================

@router.post("/register")
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):

    existing_user = db.query(User).filter(
        User.username == data.username
    ).first()

    if existing_user:

        raise HTTPException(
            status_code=409,
            detail="El nombre de usuario ya existe"
        )

    user = User(
        username=data.username,
        password_hash=hash_password(data.password)
    )

    db.add(user)
    db.flush()

    # Crear directorio raíz del usuario

    root_directory = Directory(
        name="/",
        owner_id=user.id,
        parent_id=None
    )

    db.add(root_directory)

    db.commit()

    return {
        "message": "Usuario registrado correctamente",
        "username": user.username
    }


# ==========================================
# INICIO DE SESIÓN
# ==========================================

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.username == form_data.username
    ).first()

    if not user or not verify_password(
        form_data.password,
        user.password_hash
    ):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username
    }


# ==========================================
# CONSULTAR USUARIO ACTUAL
# ==========================================

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user)
):

    return {
        "id": current_user.id,
        "username": current_user.username
    }