"""Tests for the Cruet application class."""
import pytest
from cruet import Cruet


class TestAppCreation:
    def test_create_app(self):
        app = Cruet(__name__)
        assert app is not None

    def test_app_is_callable(self):
        app = Cruet(__name__)
        assert callable(app)


class TestRouteDecorator:
    def test_simple_route(self):
        app = Cruet(__name__)

        @app.route("/hello")
        def hello():
            return "Hello, World!"

        client = app.test_client()
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert resp.text == "Hello, World!"

    def test_route_with_variable(self):
        app = Cruet(__name__)

        @app.route("/user/<name>")
        def user(name):
            return f"Hello, {name}!"

        client = app.test_client()
        resp = client.get("/user/john")
        assert resp.status_code == 200
        assert resp.text == "Hello, john!"

    def test_route_with_int_variable(self):
        app = Cruet(__name__)

        @app.route("/item/<int:id>")
        def item(id):
            return f"Item {id}"

        client = app.test_client()
        resp = client.get("/item/42")
        assert resp.status_code == 200
        assert resp.text == "Item 42"

    def test_route_with_methods(self):
        app = Cruet(__name__)

        @app.route("/submit", methods=["POST"])
        def submit():
            return "submitted"

        client = app.test_client()
        resp = client.post("/submit")
        assert resp.status_code == 200
        assert resp.text == "submitted"

    def test_multiple_routes(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "index"

        @app.route("/about")
        def about():
            return "about"

        client = app.test_client()
        assert client.get("/").text == "index"
        assert client.get("/about").text == "about"


class TestHTTPMethods:
    def test_method_not_allowed(self):
        app = Cruet(__name__)

        @app.route("/get-only")
        def get_only():
            return "ok"

        client = app.test_client()
        resp = client.post("/get-only")
        assert resp.status_code == 405

    def test_404_not_found(self):
        app = Cruet(__name__)

        @app.route("/exists")
        def exists():
            return "ok"

        client = app.test_client()
        resp = client.get("/not-exists")
        assert resp.status_code == 404


class TestResponseTypes:
    def test_string_response(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "hello"

        resp = app.test_client().get("/")
        assert resp.data == b"hello"

    def test_tuple_response_with_status(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "created", 201

        resp = app.test_client().get("/")
        assert resp.status_code == 201

    def test_tuple_response_with_headers(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "ok", 200, {"X-Custom": "value"}

        resp = app.test_client().get("/")
        assert resp.get_header("X-Custom") == "value"

    def test_dict_response_json(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return {"key": "value"}

        resp = app.test_client().get("/")
        assert resp.json == {"key": "value"}
        assert resp.get_header("Content-Type") == "application/json"
