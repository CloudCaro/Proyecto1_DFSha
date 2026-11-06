import os
from pathlib import Path
import base64

DN_ID = os.getenv("DN_ID", "DN1")

STORAGE_PATH = Path(
    os.getenv("STORAGE_PATH", "./storage")
)

STORAGE_PATH.mkdir(parents=True, exist_ok=True)

# Clave AES-256 obtenida mediante variable de entorno.
AES_KEY_B64 = os.getenv("AES_KEY")

if not AES_KEY_B64:
    raise RuntimeError(
        "No se ha configurado la variable de entorno AES_KEY"
    )

AES_KEY = base64.b64decode(AES_KEY_B64)

if len(AES_KEY) != 32:
    raise RuntimeError(
        "AES_KEY debe contener exactamente 32 bytes"
    )