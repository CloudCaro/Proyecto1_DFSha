from pathlib import Path

from client.namenode_client import NamenodeClient


class FileManager:

    def __init__(self, namenode):
        self.namenode = namenode

    def upload(self, directory_id, local_path):

        path = Path(local_path)

        if not path.is_file():
            raise RuntimeError(
                "El archivo local no existe"
            )

        with path.open("rb") as file:

            response = self.namenode.post(
                f"/writes/upload/{directory_id}",
                files={
                    "file": (
                        path.name,
                        file,
                        "application/octet-stream"
                    )
                }
            )

        return response.json()

    def download(self, file_id, destination="."):

        response = self.namenode.get(
            f"/reads/download/{file_id}"
        )

        filename = response.headers.get(
            "content-disposition",
            ""
        )

        if "filename=" in filename:
            filename = filename.split("filename=")[-1]
            filename = filename.strip('"')

        else:
            filename = f"archivo_{file_id}"

        destination_path = Path(destination)

        if destination_path.is_dir():
            destination_path = destination_path / filename

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        destination_path.write_bytes(
            response.content
        )

        return destination_path

    def delete(self, file_id):

        response = self.namenode.delete(
            f"/deletes/file/{file_id}"
        )

        return response.json()

    def open(self, file_id, mode="r"):

        response = self.namenode.post(
            f"/operations/open/{file_id}",
            params={
                "mode": mode
            }
        )

        return response.json()

    def close(self, session_id):

        response = self.namenode.post(
            f"/operations/close/{session_id}"
        )

        return response.json()

    def lock(self, file_id, session_id):

        response = self.namenode.post(
            f"/operations/lock/{file_id}",
            params={
                "session_id": session_id
            }
        )

        return response.json()

    def unlock(self, file_id, lock_token):

        response = self.namenode.post(
            f"/operations/unlock/{file_id}",
            params={
                "lock_token": lock_token
            }
        )

        return response.json()

    def replace(
        self,
        file_id,
        session_id,
        lock_token,
        local_path
    ):

        path = Path(local_path)

        if not path.is_file():
            raise RuntimeError(
                "El archivo local no existe"
            )

        with path.open("rb") as file:

            response = self.namenode.post(
                f"/writes/replace/{file_id}",
                data={
                    "session_id": session_id,
                    "lock_token": lock_token
                },
                files={
                    "file": (
                        path.name,
                        file,
                        "application/octet-stream"
                    )
                }
            )

        return response.json()

    def read(
        self,
        session_id,
        offset=0,
        length=4096
    ):

        response = self.namenode.get(
            f"/operations/read/{session_id}",
            params={
                "offset": offset,
                "length": length
            }
        )

        return bytes.fromhex(
            response.json()["content_hex"]
        )