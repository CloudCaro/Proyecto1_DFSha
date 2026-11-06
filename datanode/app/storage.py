import hashlib
import os
import re
import tempfile

from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import STORAGE_PATH, AES_KEY


class BlockStorage:

    def __init__(self):
        self.storage_path = STORAGE_PATH
        self.aes = AESGCM(AES_KEY)

    def _get_block_path(self, block_id: str) -> Path:

        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", block_id):
            raise ValueError("Identificador de bloque inválido")

        return self.storage_path / f"{block_id}.block"

    def save_block(self, block_id: str, data: bytes):

        if not data:
            raise ValueError("El bloque no puede estar vacío")

        block_hash = hashlib.sha256(data).hexdigest()

        # Generar un nonce aleatorio de 96 bits.
        nonce = os.urandom(12)

        # Cifrar el contenido.
        encrypted_data = self.aes.encrypt(
            nonce,
            data,
            block_id.encode()
        )

        # Guardar nonce + contenido cifrado.
        content = nonce + encrypted_data

        destination = self._get_block_path(block_id)

        # Escritura temporal y reemplazo atómico.
        fd, temp_name = tempfile.mkstemp(
            dir=self.storage_path,
            prefix=".tmp_"
        )

        try:
            with os.fdopen(fd, "wb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_name, destination)

        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

        return {
            "block_id": block_id,
            "sha256": block_hash,
            "size": len(data)
        }

    def get_block(self, block_id: str):

        path = self._get_block_path(block_id)

        if not path.exists():
            raise FileNotFoundError("Bloque no encontrado")

        encrypted_content = path.read_bytes()

        if len(encrypted_content) < 28:
            raise ValueError("Contenido cifrado inválido")

        nonce = encrypted_content[:12]
        ciphertext = encrypted_content[12:]

        # Descifrar y verificar autenticidad mediante GCM.
        data = self.aes.decrypt(
            nonce,
            ciphertext,
            block_id.encode()
        )

        block_hash = hashlib.sha256(data).hexdigest()

        return {
            "block_id": block_id,
            "data": data,
            "sha256": block_hash,
            "size": len(data)
        }

    def delete_block(self, block_id: str):

        path = self._get_block_path(block_id)

        if not path.exists():
            raise FileNotFoundError("Bloque no encontrado")

        path.unlink()

        return {
            "block_id": block_id,
            "deleted": True
        }


storage = BlockStorage()