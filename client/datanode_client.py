import requests


class DatanodeClient:

    def __init__(self, timeout=30):
        self.timeout = timeout

    def health(self, host, port):

        url = f"http://{host}:{port}/health"

        response = requests.get(
            url,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    def upload_block(
        self,
        host,
        port,
        block_id,
        content,
        sha256
    ):

        url = (
            f"http://{host}:{port}"
            f"/blocks/{block_id}"
        )

        response = requests.put(
            url,
            data=content,
            headers={
                "X-Content-SHA256": sha256
            },
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    def download_block(
        self,
        host,
        port,
        block_id
    ):

        url = (
            f"http://{host}:{port}"
            f"/blocks/{block_id}"
        )

        response = requests.get(
            url,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.content