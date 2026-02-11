"""Debug helper exceptions compatible with Flask."""
from werkzeug.exceptions import BadRequestKeyError


class DebugFilesKeyError(BadRequestKeyError):
    def __init__(self, key, filename=None):
        super().__init__(key)
        self.key = key
        self.filename = filename

    def __str__(self):
        base = super().__str__()
        if self.filename is None:
            return base
        return (
            f"{base}\n\n"
            "The browser (or proxy) sent a request that this server could not "
            "understand.\n\n"
            "no file contents were transmitted.\n\n"
            f"This was submitted: '{self.filename}'"
        )
