"""Tests for helper functions: jsonify, redirect, abort, url_for, make_response."""
import pytest
from cruet import Cruet, jsonify, redirect, abort, url_for, make_response
from cruet._cruet import CResponse


class TestJsonify:
    def test_jsonify_dict(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return jsonify(key="value")

        resp = app.test_client().get("/")
        assert resp.json == {"key": "value"}
        assert "application/json" in resp.get_header("Content-Type")

    def test_jsonify_positional(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return jsonify({"a": 1})

        resp = app.test_client().get("/")
        assert resp.json == {"a": 1}

    def test_jsonify_list(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return jsonify([1, 2, 3])

        resp = app.test_client().get("/")
        assert resp.json == [1, 2, 3]


class TestRedirect:
    def test_redirect_302(self):
        app = Cruet(__name__)

        @app.route("/old")
        def old():
            return redirect("/new")

        resp = app.test_client().get("/old")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/new"

    def test_redirect_301(self):
        app = Cruet(__name__)

        @app.route("/old")
        def old():
            return redirect("/new", code=301)

        resp = app.test_client().get("/old")
        assert resp.status_code == 301


class TestAbort:
    def test_abort_404(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            abort(404)

        resp = app.test_client().get("/")
        assert resp.status_code == 404

    def test_abort_403(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            abort(403)

        resp = app.test_client().get("/")
        assert resp.status_code == 403

    def test_abort_with_handler(self):
        app = Cruet(__name__)

        from cruet.helpers import HTTPException

        @app.errorhandler(HTTPException)
        def handle_http(e):
            return f"Error {e.code}", e.code

        @app.route("/")
        def index():
            abort(418, "I'm a teapot")

        resp = app.test_client().get("/")
        assert resp.status_code == 418


class TestUrlFor:
    def test_url_for_static(self):
        app = Cruet(__name__)

        @app.route("/", endpoint="index")
        def index():
            return url_for("index")

        resp = app.test_client().get("/")
        assert resp.text == "/"

    def test_url_for_with_values(self):
        app = Cruet(__name__)

        @app.route("/user/<name>", endpoint="user_profile")
        def user(name):
            return "ok"

        @app.route("/")
        def index():
            return url_for("user_profile", name="john")

        resp = app.test_client().get("/")
        assert resp.text == "/user/john"


class TestMakeResponse:
    def test_make_response_string(self):
        resp = make_response("hello")
        assert isinstance(resp, CResponse)
        assert resp.data == b"hello"

    def test_make_response_with_status(self):
        resp = make_response("not found", 404)
        assert resp.status_code == 404

    def test_make_response_with_headers(self):
        resp = make_response("ok", 200, {"X-Custom": "val"})
        assert resp.headers.get("X-Custom") == "val"

    def test_make_response_passthrough(self):
        original = CResponse("original")
        result = make_response(original)
        assert result is original
