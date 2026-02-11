"""Flask compatibility tests.

Runs identical tests against both Flask and cruet to ensure API compatibility.
Flask is imported conditionally -- if not installed, the Flask-parametrized tests
are skipped automatically.
"""

import json
import pytest

# ---------------------------------------------------------------------------
# Fixture: create an app from either Flask or cruet
# ---------------------------------------------------------------------------

def _make_flask_app():
    """Create a Flask app with the standard test routes."""
    flask = pytest.importorskip("flask")
    app = flask.Flask(__name__)
    _register_routes(app, framework="flask")
    return app


def _make_cruet_app():
    """Create a cruet app with the standard test routes."""
    from cruet import Flask
    app = Flask(__name__)
    _register_routes(app, framework="cruet")
    return app


def _register_routes(app, framework="cruet"):
    """Register a common set of routes on *app* (works for both frameworks)."""

    @app.route("/")
    def index():
        return "Hello, World!"

    @app.route("/hello/<name>")
    def hello_name(name):
        return f"Hello, {name}!"

    @app.route("/add/<int:a>/<int:b>")
    def add(a, b):
        return str(a + b)

    @app.route("/json")
    def json_view():
        return {"message": "ok", "framework": framework}

    @app.route("/status")
    def status_view():
        return "Created", 201

    @app.route("/status-headers")
    def status_headers_view():
        return "OK", 200, {"X-Custom": "yes"}

    @app.route("/post-echo", methods=["POST"])
    def post_echo():
        if framework == "flask":
            from flask import request as req
        else:
            from cruet import request as req
        return req.data.decode("utf-8")

    @app.route("/query")
    def query_view():
        if framework == "flask":
            from flask import request as req
        else:
            from cruet import request as req
        name = req.args.get("name", "world")
        return f"Hello, {name}!"

    @app.route("/redirect-me")
    def redirect_view():
        if framework == "flask":
            from flask import redirect
        else:
            from cruet import redirect
        return redirect("/destination")

    @app.route("/methods-test", methods=["GET", "POST", "PUT", "DELETE"])
    def methods_test():
        if framework == "flask":
            from flask import request as req
        else:
            from cruet import request as req
        return req.method

    @app.route("/json-post", methods=["POST"])
    def json_post():
        if framework == "flask":
            from flask import request as req, jsonify
        else:
            from cruet import request as req
            from cruet import jsonify
        data = json.loads(req.data.decode("utf-8"))
        data["received"] = True
        return jsonify(data)

    @app.errorhandler(404)
    def not_found(e):
        return "custom 404", 404

    @app.route("/abort-test")
    def abort_test():
        if framework == "flask":
            from flask import abort
        else:
            from cruet import abort
        abort(403)

    @app.route("/make-resp")
    def make_resp_view():
        if framework == "flask":
            from flask import make_response
        else:
            from cruet import make_response
        resp = make_response("custom body", 200)
        resp.headers["X-Made"] = "yes"
        return resp


@pytest.fixture(params=["flask", "cruet"])
def app(request):
    """Yield an app instance for the requested framework."""
    if request.param == "flask":
        return _make_flask_app()
    else:
        return _make_cruet_app()


@pytest.fixture
def client(app):
    """Return a test client for the app."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper to perform requests through the test client
# ---------------------------------------------------------------------------

def _get(client, path, **kwargs):
    return client.get(path, **kwargs)


def _post(client, path, **kwargs):
    return client.post(path, **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBasicRouting:
    """Test that basic routing works identically on both frameworks."""

    def test_index(self, client):
        resp = _get(client, "/")
        assert resp.status_code == 200
        assert b"Hello, World!" in resp.data

    def test_url_variable_string(self, client):
        resp = _get(client, "/hello/Alice")
        assert resp.status_code == 200
        assert b"Hello, Alice!" in resp.data

    def test_url_variable_int(self, client):
        resp = _get(client, "/add/3/4")
        assert resp.status_code == 200
        assert b"7" in resp.data

    def test_trailing_slash_redirect(self, client):
        """Routes defined without trailing slash should still 200 on exact path."""
        resp = _get(client, "/json")
        assert resp.status_code == 200


class TestResponses:
    """Test response types and status codes."""

    def test_dict_response_is_json(self, client):
        resp = _get(client, "/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["message"] == "ok"

    def test_tuple_status(self, client):
        resp = _get(client, "/status")
        assert resp.status_code == 201

    def test_tuple_status_headers(self, client):
        resp = _get(client, "/status-headers")
        assert resp.status_code == 200
        # Check custom header (works for both frameworks)
        header_val = None
        if hasattr(resp, "headers"):
            header_val = resp.headers.get("X-Custom")
        elif hasattr(resp, "get_header"):
            header_val = resp.get_header("X-Custom")
        assert header_val == "yes"

    def test_make_response(self, client):
        resp = _get(client, "/make-resp")
        assert resp.status_code == 200
        assert b"custom body" in resp.data
        header_val = None
        if hasattr(resp, "headers"):
            header_val = resp.headers.get("X-Made")
        elif hasattr(resp, "get_header"):
            header_val = resp.get_header("X-Made")
        assert header_val == "yes"


class TestRequestParsing:
    """Test request data parsing."""

    def test_post_body(self, client):
        resp = _post(client, "/post-echo", data=b"raw body data",
                     content_type="text/plain")
        assert resp.status_code == 200
        assert b"raw body data" in resp.data

    def test_query_string(self, client):
        resp = _get(client, "/query", query_string="name=Flask")
        assert resp.status_code == 200
        assert b"Hello, Flask!" in resp.data

    def test_query_string_default(self, client):
        resp = _get(client, "/query")
        assert resp.status_code == 200
        assert b"Hello, world!" in resp.data


class TestHTTPMethods:
    """Test HTTP method handling."""

    def test_get_method(self, client):
        resp = _get(client, "/methods-test")
        assert resp.status_code == 200
        assert b"GET" in resp.data

    def test_post_method(self, client):
        resp = _post(client, "/methods-test")
        assert resp.status_code == 200
        assert b"POST" in resp.data

    def test_put_method(self, client):
        resp = client.put("/methods-test")
        assert resp.status_code == 200
        assert b"PUT" in resp.data

    def test_delete_method(self, client):
        resp = client.delete("/methods-test")
        assert resp.status_code == 200
        assert b"DELETE" in resp.data


class TestJSON:
    """Test JSON request/response handling."""

    def test_json_response(self, client):
        resp = _get(client, "/json")
        data = json.loads(resp.data)
        assert "message" in data
        assert data["message"] == "ok"

    def test_json_post_roundtrip(self, client):
        payload = json.dumps({"key": "value"}).encode("utf-8")
        resp = _post(client, "/json-post", data=payload,
                     content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["key"] == "value"
        assert data["received"] is True


class TestRedirects:
    """Test redirect responses."""

    def test_redirect_status(self, client):
        resp = _get(client, "/redirect-me")
        assert resp.status_code == 302

    def test_redirect_location(self, client):
        resp = _get(client, "/redirect-me")
        location = None
        if hasattr(resp, "headers"):
            location = resp.headers.get("Location")
        elif hasattr(resp, "get_header"):
            location = resp.get_header("Location")
        assert location is not None
        assert "/destination" in location


class TestErrorHandling:
    """Test error handling."""

    def test_custom_404(self, client):
        resp = _get(client, "/nonexistent-path")
        assert resp.status_code == 404
        assert b"custom 404" in resp.data

    def test_abort(self, client):
        resp = _get(client, "/abort-test")
        assert resp.status_code == 403
