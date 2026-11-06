import requests
import hashlib
import os

# Direcciones de nuestros tres Datanodes
DATANODES = {
    "DN1": "http://localhost:8001",
    "DN2": "http://localhost:8002",
    "DN3": "http://localhost:8003"
}

BLOCK_ID = "bloque_prueba_001"

# Contenido de prueba
original_data = b"Hola DFSha! Estamos probando nuestro sistema distribuido."

# Calculamos el hash original
original_hash = hashlib.sha256(original_data).hexdigest()


def test_datanodes_health():

    print("\n--- COMPROBANDO DATANODES ---")

    for node_id, url in DATANODES.items():

        response = requests.get(f"{url}/health")

        assert response.status_code == 200
        assert response.json()["datanode_id"] == node_id

        print(f"{node_id}: FUNCIONANDO")


def test_upload_download():

    print("\n--- PROBANDO ALMACENAMIENTO ---")

    # Seleccionamos DN1
    url = DATANODES["DN1"]

    # Subimos el bloque
    upload = requests.put(
        f"{url}/blocks/{BLOCK_ID}",
        data=original_data,
        headers={
            "X-Content-SHA256": original_hash
        }
    )

    assert upload.status_code == 200

    print("Bloque almacenado correctamente")

    # Descargamos el bloque
    download = requests.get(
        f"{url}/blocks/{BLOCK_ID}"
    )

    assert download.status_code == 200

    recovered_data = download.content

    # Calculamos el hash recuperado
    recovered_hash = hashlib.sha256(
        recovered_data
    ).hexdigest()

    assert recovered_data == original_data
    assert recovered_hash == original_hash

    print("Bloque recuperado correctamente")
    print("SHA-256 original:", original_hash)
    print("SHA-256 recuperado:", recovered_hash)
    print("INTEGRIDAD VERIFICADA")


def test_block_is_not_replicated():

    print("\n--- COMPROBANDO INDEPENDENCIA ---")

    # El bloque está en DN1, pero no en DN2
    response = requests.get(
        f"{DATANODES['DN2']}/blocks/{BLOCK_ID}"
    )

    assert response.status_code == 404

    print("DN2 no tiene el bloque almacenado")
    print("Almacenamientos independientes")


def test_delete():

    print("\n--- PROBANDO ELIMINACION ---")

    response = requests.delete(
        f"{DATANODES['DN1']}/blocks/{BLOCK_ID}"
    )

    assert response.status_code == 200

    # Comprobamos que ya no existe
    response = requests.get(
        f"{DATANODES['DN1']}/blocks/{BLOCK_ID}"
    )

    assert response.status_code == 404

    print("Bloque eliminado correctamente")


if __name__ == "__main__":

    test_datanodes_health()
    test_upload_download()
    test_block_is_not_replicated()
    test_delete()

    print("\nTODAS LAS PRUEBAS FINALIZARON CORRECTAMENTE")