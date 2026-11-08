import asyncio
import logging

import httpx

from app.config import (
    DN_ID,
    NAMENODE_URL,
    NODE_HOST,
    NODE_CAPACITY,
    HEARTBEAT_INTERVAL
)


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("DFSha-Heartbeat")


async def register_node(client):

    try:
        response = await client.post(
            f"{NAMENODE_URL}/datanodes/register",
            json={
                "node_id": DN_ID,
                "host": NODE_HOST,
                "port": get_node_port(),
                "capacity": NODE_CAPACITY
            }
        )

        response.raise_for_status()

        logger.info(
            f"{DN_ID} registrado correctamente en el Namenode"
        )

        return True

    except httpx.HTTPError as error:

        logger.error(
            f"No se pudo registrar {DN_ID}: {error}"
        )

        return False


def get_node_port():
    return 8001


async def heartbeat_loop():

    async with httpx.AsyncClient(timeout=5.0) as client:

        registered = False

        while True:

            try:

                if not registered:

                    registered = await register_node(client)

                if registered:

                    response = await client.post(
                        f"{NAMENODE_URL}/datanodes/{DN_ID}/heartbeat"
                    )

                    response.raise_for_status()

                    logger.info(
                        f"Heartbeat enviado por {DN_ID}"
                    )

            except httpx.HTTPError as error:

                logger.error(
                    f"Error de comunicación de {DN_ID}: {error}"
                )

                registered = False

            await asyncio.sleep(HEARTBEAT_INTERVAL)