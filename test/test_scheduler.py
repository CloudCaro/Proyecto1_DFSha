from app.database import SessionLocal
from app.scheduler import (
    get_available_datanodes,
    select_datanodes,
    create_block_placement
)


def test_scheduler():

    db = SessionLocal()

    try:

        print("\n========== DATANODES DISPONIBLES ==========")

        nodes = get_available_datanodes(
            db,
            block_size=4 * 1024 * 1024
        )

        for node in nodes:

            print(
                node.node_id,
                node.host,
                node.port
            )

        print("\n========== SELECCIÓN DE RÉPLICAS ==========")

        selected = select_datanodes(
            db,
            block_size=4 * 1024 * 1024
        )

        for node in selected:

            print("Réplica:", node.node_id)

        print("\n========== PLAN DE DISTRIBUCIÓN ==========")

        block_sizes = [
            4 * 1024 * 1024,
            4 * 1024 * 1024,
            2 * 1024 * 1024
        ]

        placement = create_block_placement(
            db,
            block_sizes
        )

        for block in placement:

            print(
                f"\nBloque {block['block_index']}"
            )

            print(
                f"Tamaño: {block['block_size']} bytes"
            )

            for replica in block["replicas"]:

                print(
                    "Ubicación:",
                    replica["node_id"]
                )

    finally:

        db.close()


if __name__ == "__main__":
    test_scheduler()