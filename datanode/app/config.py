import os
from pathlib import Path
import base64

DN_ID = os.getenv("DN_ID", "DN1")

STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./storage"))
STORAGE_PATH.mkdir(parents=True, exist_ok=True)

AES_KEY_B64 = os.getenv("AES_KEY")

if not AES_KEY_B64:
    raise RuntimeError(
        "No se ha configurado la variable de entorno AES_KEY"
    )

AES_KEY = base64.b64decode(AES_KEY_B64)

if len(AES_KEY) != 32:
    raise RuntimeError("AES_KEY debe contener exactamente 32 bytes")


# Configuración de comunicación con el Namenode

NAMENODE_URL = os.getenv(
    "NAMENODE_URL",
    "http://127.0.0.1:8000"
)

NODE_HOST = os.getenv("NODE_HOST", "127.0.0.1")

HEARTBEAT_INTERVAL = 5

NODE_CAPACITY = int(
    os.getenv("NODE_CAPACITY", str(1024 * 1024 * 1024))
)
 