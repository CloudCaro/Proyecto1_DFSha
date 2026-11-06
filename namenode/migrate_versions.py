from sqlalchemy import inspect, text

from app.database import engine, create_tables


def migrate():
    # Crea las tablas nuevas sin borrar las existentes.
    create_tables()

    inspector = inspect(engine)

    with engine.begin() as connection:

        # Agregar version_id a write_sessions si todavía no existe.
        session_columns = {
            column["name"]
            for column in inspector.get_columns("write_sessions")
        }

        if "version_id" not in session_columns:
            connection.execute(text(
                "ALTER TABLE write_sessions "
                "ADD COLUMN version_id INTEGER"
            ))

        # Agregar mode a write_sessions si todavía no existe.
        if "mode" not in session_columns:
            connection.execute(text(
                "ALTER TABLE write_sessions "
                "ADD COLUMN mode VARCHAR(10) DEFAULT 'r'"
            ))

        # Crear snapshots iniciales para archivos existentes.
        files = connection.execute(text("""
            SELECT id, version, size, sha256
            FROM files
            WHERE status = 'ACTIVE'
        """)).fetchall()

        for file_id, version_number, size, sha256 in files:

            existing_version = connection.execute(text("""
                SELECT id
                FROM file_versions
                WHERE file_id = :file_id
                  AND version_number = :version
            """), {
                "file_id": file_id,
                "version": version_number
            }).fetchone()

            if existing_version:
                version_id = existing_version[0]
            else:
                result = connection.execute(text("""
                    INSERT INTO file_versions
                    (file_id, version_number, size, sha256, status)
                    VALUES (:file_id, :version, :size, :sha256, 'ACTIVE')
                """), {
                    "file_id": file_id,
                    "version": version_number,
                    "size": size or 0,
                    "sha256": sha256 or ""
                })

                version_id = result.lastrowid

            # Asociar los bloques actuales con la versión inicial.
            blocks = connection.execute(text("""
                SELECT id, block_index
                FROM blocks
                WHERE file_id = :file_id
                ORDER BY block_index
            """), {
                "file_id": file_id
            }).fetchall()

            for block_id, block_index in blocks:
                connection.execute(text("""
                    INSERT OR IGNORE INTO version_blocks
                    (version_id, block_id, block_index)
                    VALUES (:version_id, :block_id, :block_index)
                """), {
                    "version_id": version_id,
                    "block_id": block_id,
                    "block_index": block_index
                })

    print("Migración de versiones completada.")


if __name__ == "__main__":
    migrate()