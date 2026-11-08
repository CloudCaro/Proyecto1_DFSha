import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar secretos desde el .env ubicado en la raíz del repositorio.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        str(BASE_DIR / "dfsha.db")
    )
)

DATABASE_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)

NAMENODE_ID = os.getenv("NAMENODE_ID", "NN1")

HEARTBEAT_INTERVAL = 5

HEARTBEAT_TIMEOUT = 15

BLOCK_SIZE = 4 * 1024 * 1024

REPLICATION_FACTOR = 2

# ==========================================
# CONFIGURACIÓN DE SEGURIDAD
# ==========================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "No se ha configurado JWT_SECRET_KEY"
    )

JWT_ALGORITHM = "HS256"

JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60