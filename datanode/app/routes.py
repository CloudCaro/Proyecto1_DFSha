import hashlib

from fastapi import APIRouter, HTTPException, Header, Response
from fastapi import Request

from app.storage import storage
from app.config import DN_ID


router = APIRouter()


@router.get("/health")
def health():

    return {
        "status": "ok",
        "datanode_id": DN_ID
    }


@router.put("/blocks/{block_id}")
async def upload_block(
    block_id: str,
    request: Request,
    x_content_sha256: str | None = Header(default=None)
):

    try:

        data = await request.body()

        if not data:
            raise HTTPException(
                status_code=400,
                detail="El bloque está vacío"
            )

        calculated_hash = hashlib.sha256(data).hexdigest()

        if (
            x_content_sha256 is not None
            and calculated_hash.lower() != x_content_sha256.lower()
        ):
            raise HTTPException(
                status_code=400,
                detail="El hash recibido no coincide"
            )

        result = storage.save_block(block_id, data)

        return {
            "message": "Bloque almacenado correctamente",
            "datanode_id": DN_ID,
            **result
        }

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@router.get("/blocks/{block_id}")
def download_block(block_id: str):

    try:

        result = storage.get_block(block_id)

        return Response(
            content=result["data"],
            media_type="application/octet-stream",
            headers={
                "X-Block-ID": block_id,
                "X-Content-SHA256": result["sha256"],
                "X-Block-Size": str(result["size"]),
                "X-Datanode-ID": DN_ID
            }
        )

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail="Bloque no encontrado"
        )

    except ValueError:

        raise HTTPException(
            status_code=500,
            detail="No fue posible verificar el bloque"
        )


@router.delete("/blocks/{block_id}")
def delete_block(block_id: str):

    try:

        result = storage.delete_block(block_id)

        return {
            "message": "Bloque eliminado correctamente",
            "datanode_id": DN_ID,
            **result
        }

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail="Bloque no encontrado"
        )