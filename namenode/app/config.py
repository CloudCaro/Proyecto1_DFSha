import os
from pathlib import Path

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