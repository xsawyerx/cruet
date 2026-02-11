"""Testing helpers compatible with flask.testing."""
import io
import json as _json
from urllib.parse import urlsplit, urlencode

from click.testing import CliRunner

from cruet.app import _make_test_environ, TestClient
from cruet.cli import ScriptInfo


class EnvironBuilder:
    def __init__(
        self,
        app,
        path="/",
        method="GET",
        base_url=None,
        query_string=None,
        data=None,
        json=None,
        headers=None,
        environ_base=None,
        url_scheme=None,
        subdomain=None,
    ):
        self.app = app
        self.method = method
        self.headers = headers
        self.environ_base = environ_base

        if "://" in path:
            parsed = urlsplit(path)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            path = parsed.path or "/"
            if parsed.query:
                query_string = parsed.query
            if not url_scheme and parsed.scheme:
                url_scheme = parsed.scheme

        if subdomain and not base_url:
            server_name = app.config.get("SERVER_NAME")
            if server_name:
                scheme = url_scheme or app.config.get("PREFERRED_URL_SCHEME") or "http"
                script_root = app.config.get("APPLICATION_ROOT") or ""
                base_url = f"{scheme}://{subdomain}.{server_name}{script_root}"

        if base_url is None:
            server_name = app.config.get("SERVER_NAME")
            if server_name:
                scheme = url_scheme or app.config.get("PREFERRED_URL_SCHEME") or "http"
                script_root = app.config.get("APPLICATION_ROOT") or ""
                base_url = f"{scheme}://{server_name}{script_root}"

        self.base_url = base_url
        if url_scheme is None:
            url_scheme = app.config.get("PREFERRED_URL_SCHEME") or "http"
        self.url_scheme = url_scheme

        body = b""
        content_type = ""
        if json is not None:
            body = app.json.dumps(json).encode("utf-8")
            content_type = "application/json"
        elif isinstance(data, dict):
            body = urlencode(data).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        elif data is not None:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")

        self.input_stream = io.BytesIO(body)

        self._environ = _make_test_environ(
            path,
            method,
            query_string=query_string or "",
            body=body,
            content_type=content_type,
            headers=headers,
            base_url=base_url,
            scheme=self.url_scheme,
            environ_base=environ_base,
        )

        self.host = self._environ.get("HTTP_HOST", self._environ.get("SERVER_NAME"))
        self.script_root = self._environ.get("SCRIPT_NAME", "")
        self.path = self._environ.get("PATH_INFO", "/")

    def get_environ(self):
        return dict(self._environ)

    def close(self):
        try:
            self.input_stream.close()
        except Exception:
            pass


class FlaskClient(TestClient):
    pass


class FlaskCliRunner(CliRunner):
    def __init__(self, app, **kwargs):
        self.app = app
        super().__init__(**kwargs)

    def invoke(self, cli=None, args=None, **kwargs):
        if cli is None:
            cli = self.app.cli
        if "obj" not in kwargs:
            kwargs["obj"] = ScriptInfo(create_app=lambda: self.app)
        return super().invoke(cli, args, **kwargs)
