from client.security import SecurityManager
from client.namenode_client import NamenodeClient
from client.file_manager import FileManager


class CommandManager:

    def __init__(self, base_url):

        self.security = SecurityManager()

        self.namenode = NamenodeClient(
            base_url,
            self.security
        )

        self.files = FileManager(
            self.namenode
        )

        self.current_directory = None

        self.current_session = None
        self.current_file_id = None
        self.lock_token = None

    def register(self, username, password):

        response = self.namenode.post(
            "/auth/register",
            json={
                "username": username,
                "password": password
            }
        )

        return response.json()

    def login(self, username, password):

        response = self.namenode.post(
            "/auth/login",
            data={
                "username": username,
                "password": password
            }
        )

        data = response.json()

        self.security.set_session(
            data["access_token"],
            data["username"]
        )

        root = self.namenode.get(
            "/filesystem/root"
        ).json()

        self.current_directory = root["id"]

        return data

    def logout(self):

        self.security.clear_session()

        self.current_directory = None
        self.current_session = None
        self.current_file_id = None
        self.lock_token = None

    def require_login(self):

        if not self.security.is_authenticated():
            raise RuntimeError(
                "Primero debes iniciar sesión"
            )

    def ls(self):

        self.require_login()

        response = self.namenode.get(
            f"/filesystem/ls/{self.current_directory}"
        )

        return response.json()

    def mkdir(self, name):

        self.require_login()

        response = self.namenode.post(
            "/filesystem/mkdir",
            json={
                "parent_id": self.current_directory,
                "name": name
            }
        )

        return response.json()

    def rmdir(self, directory_id):

        self.require_login()

        response = self.namenode.delete(
            f"/filesystem/rmdir/{directory_id}"
        )

        return response.json()

    def put(self, path):

        self.require_login()

        return self.files.upload(
            self.current_directory,
            path
        )

    def get(self, file_id, destination="."):

        self.require_login()

        return self.files.download(
            file_id,
            destination
        )

    def rm(self, file_id):

        self.require_login()

        return self.files.delete(
            file_id
        )

    def open(self, file_id, mode):

        self.require_login()

        result = self.files.open(
            file_id,
            mode
        )

        self.current_session = result["session_id"]
        self.current_file_id = file_id

        return result

    def lock(self):

        self.require_login()

        if not self.current_session:
            raise RuntimeError(
                "Primero debes abrir un archivo en modo escritura"
            )

        result = self.files.lock(
            self.current_file_id,
            self.current_session
        )

        self.lock_token = result["lock_token"]

        return result
    
    def unlock(self):

        self.require_login()

        if not self.current_session or not self.lock_token:
            raise RuntimeError(
                "No hay un bloqueo activo para liberar"
            )

        result = self.files.unlock(
            self.current_file_id,
            self.lock_token
        )

        self.lock_token = None

        return result

    def write(self, path):

        self.require_login()

        if not self.current_session or not self.lock_token:
            raise RuntimeError(
                "Necesitas abrir el archivo y adquirir el bloqueo"
            )

        return self.files.replace(
            self.current_file_id,
            self.current_session,
            self.lock_token,
            path
        )

    def read(self, offset=0, length=4096):

        self.require_login()

        if not self.current_session:
            raise RuntimeError(
                "Primero debes abrir un archivo"
            )

        return self.files.read(
            self.current_session,
            offset,
            length
        )

    def close(self):

        self.require_login()

        if not self.current_session:
            raise RuntimeError(
                "No hay ninguna sesión abierta"
            )

        result = self.files.close(
            self.current_session
        )

        self.current_session = None
        self.current_file_id = None
        self.lock_token = None

        return result