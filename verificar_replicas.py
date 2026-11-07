import sqlite3

conn = sqlite3.connect("namenode/dfsha.db")

cursor = conn.cursor()

print("=== REPLICAS ACTIVAS POR BLOQUE ===")

cursor.execute("""
    SELECT block_id, COUNT(*)
    FROM block_replicas
    WHERE status = 'ACTIVE'
    GROUP BY block_id
    ORDER BY block_id
""")

replicas = cursor.fetchall()

for block_id, cantidad in replicas:
    print(f"Bloque {block_id}: {cantidad} replicas activas")

print("\n=== RESULTADO ===")

if replicas and all(cantidad == 2 for _, cantidad in replicas):
    print("CORRECTO: Todos los bloques tienen 2 replicas activas.")
else:
    print("ATENCION: Hay bloques que no tienen exactamente 2 replicas activas.")

conn.close()
