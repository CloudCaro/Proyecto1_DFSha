class SecurityManager:

    def __init__(self):
        self.token = None
        self.username = None

    def set_session(self, token, username):
        self.token = token
        self.username = username

    def clear_session(self):
        self.token = None
        self.username = None

    def is_authenticated(self):
        return self.token is not None

    def get_headers(self):

        if not self.token:
            return {}

        return {
            "Authorization": f"Bearer {self.token}"
        }