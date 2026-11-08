import sqlite3
import requests
import hashlib
import sys

DB_PATH = "namenode/dfsha.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 65)
print("       VERIFICACION FISICA DE REPLICAS - DFSha")
print("=" * 65)

# Obtener bloques y sus hashes originales
cursor.execute("""
    SELECT id, block_id, sha256, size
    FROM blocks
    ORDER BY id
""")

blocks = cursor.fetchall()

# Obtener replicas activas y sus datanodes
cursor.execute("""
    SELECT
        br.block_id,
        br.status,
        dn.node_id,
        dn.host,
        dn.port,
        dn.status AS node_status
    FROM block_replicas br
    JOIN datanodes dn ON dn.id = br.datanode_id
    WHERE br.status = 'ACTIVE'
    ORDER BY br.block_id, dn.node_id
""")

replicas = cursor.fetchall()

total_replicas = 0
valid_replicas = 0
failed_replicas = 0
blocks_without_two = 0

print(f"\nBloques registrados: {len(blocks)}")

for block in blocks:

    block_id = block["block_id"]
    expected_hash = block["sha256"]
    expected_size = block["size"]

    block_replicas = [
        replica for replica in replicas
        if replica["block_id"] == block["id"]
    ]

    print("\n" + "-" * 65)
    print(f"Bloque: {block_id}")
    print(f"Tamaño esperado: {expected_size} bytes")
    print(f"SHA-256 esperado: {expected_hash}")
    print(f"Réplicas ACTIVE: {len(block_replicas)}")

    active_nodes = set()

    for replica in block_replicas:

        total_replicas += 1

        node_id = replica["node_id"]
        host = replica["host"]
        port = replica["port"]

        active_nodes.add(node_id)

        print(f"\n  Nodo: {node_id}")

        if replica["node_status"] != "ACTIVE":
            print("  ERROR: El nodo no está ACTIVE")
            failed_replicas += 1
            continue

        try:
            url = f"http://{host}:{port}/blocks/{block_id}"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            content = response.content

            actual_hash = hashlib.sha256(content).hexdigest()

            if len(content) != expected_size:
                print("  ERROR: Tamaño incorrecto")
                failed_replicas += 1
                continue

            if actual_hash != expected_hash:
                print("  ERROR: SHA-256 no coincide")
                failed_replicas += 1
                continue

            print("  OK: Bloque recuperado")
            print("  OK: Tamaño correcto")
            print("  OK: SHA-256 coincide")

            valid_replicas += 1

        except Exception as error:
            print(f"  ERROR: No se pudo verificar: {error}")
            failed_replicas += 1

    if len(block_replicas) != 2 or len(active_nodes) != 2:
        blocks_without_two += 1
        print("\n  ADVERTENCIA: No tiene exactamente 2 replicas ACTIVE en nodos distintos.")

print("\n" + "=" * 65)
print("                    RESULTADO FINAL")
print("=" * 65)

print(f"Réplicas revisadas: {total_replicas}")
print(f"Réplicas válidas: {valid_replicas}")
print(f"Réplicas con errores: {failed_replicas}")
print(f"Bloques sin exactamente 2 réplicas: {blocks_without_two}")

if (
    total_replicas > 0
    and failed_replicas == 0
    and blocks_without_two == 0
):
    print("\nRESULTADO: CORRECTO")
    print("Todas las réplicas ACTIVE existen y superaron la verificación SHA-256.")
else:
    print("\nRESULTADO: REQUIERE REVISION")
    print("Hay réplicas o bloques que necesitan verificarse.")

conn.close()
