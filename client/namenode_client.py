import requests


class NamenodeClient:

    def __init__(self, base_url, security):

        self.base_url = base_url.rstrip("/")
        self.security = security

        self.timeout = 30

    def request(
        self,
        method,
        endpoint,
        **kwargs
    ):

        url = f"{self.base_url}{endpoint}"

        headers = kwargs.pop("headers", {})

        headers.update(
            self.security.get_headers()
        )

        try:

            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                **kwargs
            )

            if not response.ok:

                try:
                    detail = response.json().get(
                        "detail",
                        response.text
                    )

                except ValueError:
                    detail = response.text

                raise RuntimeError(
                    f"Error HTTP {response.status_code}: {detail}"
                )

            return response

        except requests.ConnectionError:

            raise RuntimeError(
                "No fue posible conectar con el Namenode"
            )

        except requests.Timeout:

            raise RuntimeError(
                "La solicitud superó el tiempo de espera"
            )

    def get(self, endpoint, **kwargs):
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        return self.request("POST", endpoint, **kwargs)

    def delete(self, endpoint, **kwargs):
        return self.request("DELETE", endpoint, **kwargs)