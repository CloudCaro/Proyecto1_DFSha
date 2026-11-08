#!/usr/bin/env python3
"""Migración de clave AES de DFSha usando réplicas recuperables como fuentes.

EXPORT (Datanodes con la clave antigua aún activos):
  - Lee metadatos y ubicaciones previstas desde namenode/dfsha.db.
  - Para cada bloque intenta GET en DN1, DN2 y DN3 hasta encontrar una copia
    descifrable.
  - Verifica tamaño y SHA-256 contra la tabla blocks.
  - Guarda una única copia plaintext por block_id en aes_migration_backup/blocks.
  - Guarda placements.json con los Datanodes que deben conservar cada réplica.

IMPORT (Datanodes reiniciados con la nueva AES_KEY):
  - Envía cada bloque solo a los Datanodes registrados en block_replicas.
  - Verifica después cada PUT mediante GET y SHA-256.

No modifica SQLite ni borra archivos .block. No elimina el respaldo plaintext.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "namenode" / "dfsha.db"
BACKUP = ROOT / "aes_migration_backup"
BLOCKS_DIR = BACKUP / "blocks"
NODES = {
    "DN1": "http://127.0.0.1:8001",
    "DN2": "http://127.0.0.1:8002",
    "DN3": "http://127.0.0.1:8003",
}


def http_request(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read(), dict(response.headers.items()), response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} en {url}: {detail}") from exc


def load_metadata():
    if not DB_PATH.is_file():
        raise RuntimeError(f"No existe la base de datos: {DB_PATH}")
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        blocks = con.execute("SELECT block_id, size, sha256 FROM blocks ORDER BY block_id").fetchall()
        placements_rows = con.execute(
            """SELECT b.block_id, d.node_id
               FROM block_replicas br
               JOIN blocks b ON b.id = br.block_id
               JOIN datanodes d ON d.id = br.datanode_id
               ORDER BY b.block_id, d.node_id"""
        ).fetchall()
    finally:
        con.close()

    placements = {}
    for block_id, node_id in placements_rows:
        if node_id in NODES:
            placements.setdefault(block_id, []).append(node_id)
    return blocks, placements


def export_all():
    blocks, placements = load_metadata()
    if not blocks:
        raise RuntimeError("La tabla blocks no contiene bloques.")

    BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    failures = []
    print(f"Bloques en Namenode: {len(blocks)}")

    for index, (block_id, expected_size, expected_sha) in enumerate(blocks, 1):
        saved = False
        errors = []
        # La fuente puede ser cualquier nodo que aún pueda descifrar la copia.
        for node_id, base_url in NODES.items():
            try:
                data, headers, _ = http_request(f"{base_url}/blocks/{block_id}")
                actual_sha = hashlib.sha256(data).hexdigest()
                if len(data) != expected_size:
                    raise RuntimeError(f"tamaño {len(data)} != metadato {expected_size}")
                if actual_sha.lower() != expected_sha.lower():
                    raise RuntimeError(f"SHA-256 {actual_sha} != metadato {expected_sha}")
                target = BLOCKS_DIR / f"{block_id}.plain"
                target.write_bytes(data)
                manifest.append({
                    "block_id": block_id,
                    "size": expected_size,
                    "sha256": expected_sha,
                    "source_node": node_id,
                    "targets": sorted(set(placements.get(block_id, []))),
                })
                print(f"[{index}/{len(blocks)}] {block_id}: recuperado desde {node_id}; destinos={','.join(manifest[-1]['targets']) or 'SIN DESTINO'}")
                saved = True
                break
            except Exception as exc:
                errors.append(f"{node_id}: {exc}")

        if not saved:
            failures.append((block_id, errors))

    if failures:
        # No generar manifiesto final si falta siquiera un bloque.
        raise RuntimeError(
            "No se pudieron recuperar todos los bloques. Sin migración importable:\n" +
            "\n".join(f"- {bid}: {' | '.join(errs)}" for bid, errs in failures)
        )

    (BACKUP / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nEXPORT COMPLETADO: {len(manifest)} bloques verificados.")
    print(f"Respaldo plaintext: {BACKUP}")
    print("ATENCIÓN: contiene datos sin cifrar. No lo compartas ni lo subas a GitHub.")
    empty_targets = [x["block_id"] for x in manifest if not x["targets"]]
    if empty_targets:
        print("ADVERTENCIA: bloques sin destinos en block_replicas:", ", ".join(empty_targets))


def import_all():
    manifest_path = BACKUP / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"No existe {manifest_path}. Ejecuta export primero.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    total = 0
    for index, item in enumerate(manifest, 1):
        block_id = item["block_id"]
        plain_path = BLOCKS_DIR / f"{block_id}.plain"
        if not plain_path.is_file():
            raise RuntimeError(f"Falta respaldo de {block_id}: {plain_path}")
        data = plain_path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if len(data) != item["size"] or sha.lower() != item["sha256"].lower():
            raise RuntimeError(f"Respaldo alterado o incorrecto: {block_id}")
        targets = item.get("targets", [])
        if not targets:
            raise RuntimeError(f"{block_id} no tiene destinos en block_replicas; no se escribe para evitar inventar ubicación.")

        for node_id in targets:
            base_url = NODES.get(node_id)
            if not base_url:
                raise RuntimeError(f"Nodo desconocido en manifiesto: {node_id}")
            http_request(
                f"{base_url}/blocks/{block_id}",
                method="PUT",
                data=data,
                headers={"Content-Type": "application/octet-stream", "X-Content-SHA256": sha},
            )
            downloaded, headers, _ = http_request(f"{base_url}/blocks/{block_id}")
            downloaded_sha = hashlib.sha256(downloaded).hexdigest()
            if len(downloaded) != item["size"] or downloaded_sha.lower() != item["sha256"].lower():
                raise RuntimeError(f"Verificación posterior falló en {node_id}/{block_id}")
            print(f"[{index}/{len(manifest)}] {block_id}: re-cifrado y verificado en {node_id}")
            total += 1

    print(f"\nIMPORT COMPLETADO: {total} réplicas re-cifradas y verificadas.")
    print("Conserva aes_migration_backup hasta completar las pruebas funcionales y de integridad.")


def main():
    parser = argparse.ArgumentParser(description="Migración AES DFSha con recuperación desde réplicas sanas")
    parser.add_argument("phase", choices=["export", "import"])
    args = parser.parse_args()
    try:
        if args.phase == "export":
            export_all()
        else:
            import_all()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
