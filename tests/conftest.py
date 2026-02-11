"""Shared test fixtures for cruet."""
import io


def make_environ(method="GET", path="/", query_string="", content_type="",
                 body=b"", headers=None, host="localhost", port=80,
                 scheme="http"):
    """Create a minimal WSGI environ dict for testing."""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "SERVER_NAME": host,
        "SERVER_PORT": str(port),
        "HTTP_HOST": f"{host}:{port}" if port != 80 else host,
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": scheme,
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "SCRIPT_NAME": "",
    }
    if content_type:
        environ["CONTENT_TYPE"] = content_type
    if body:
        environ["CONTENT_LENGTH"] = str(len(body))
    if headers:
        for key, value in headers.items():
            key_upper = key.upper().replace("-", "_")
            if key_upper == "CONTENT_TYPE":
                environ["CONTENT_TYPE"] = value
            elif key_upper == "CONTENT_LENGTH":
                environ["CONTENT_LENGTH"] = value
            else:
                environ[f"HTTP_{key_upper}"] = value
    return environ
