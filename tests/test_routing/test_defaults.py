"""Tests for the defaults= kwarg support in route() / add_url_rule()."""

from cruet import Flask
from cruet.blueprints import Blueprint


class TestRouteDefaults:
    """Unit tests for defaults= on app.route() and add_url_rule()."""

    def test_single_route_with_defaults(self):
        """A static route with defaults= provides the default value."""
        app = Flask(__name__)

        @app.route("/hello", defaults={"name": "World"})
        def hello(name):
            return f"Hello, {name}!"

        client = app.test_client()
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert resp.text == "Hello, World!"

    def test_two_routes_same_endpoint(self):
        """Static route with defaults + dynamic route share the same view."""
        app = Flask(__name__)

        @app.route("/greet", defaults={"name": "Programmer"})
        @app.route("/greet/<name>")
        def greet(name):
            return f"Hi, {name}!"

        client = app.test_client()
        # Static route uses default
        resp = client.get("/greet")
        assert resp.status_code == 200
        assert resp.text == "Hi, Programmer!"
        # Dynamic route uses matched value
        resp = client.get("/greet/Alice")
        assert resp.status_code == 200
        assert resp.text == "Hi, Alice!"

    def test_matched_values_override_defaults(self):
        """When a URL variable matches, it takes precedence over defaults."""
        app = Flask(__name__)

        # Register with defaults that would supply 'name', but
        # also register a dynamic route that captures 'name'.
        @app.route("/user", defaults={"name": "Anonymous"})
        @app.route("/user/<name>")
        def user(name):
            return name

        client = app.test_client()
        resp = client.get("/user/Bob")
        assert resp.text == "Bob"

    def test_defaults_via_add_url_rule(self):
        """defaults= works via the add_url_rule() API too."""
        app = Flask(__name__)

        def page(slug):
            return f"Page: {slug}"

        app.add_url_rule("/page", "page", page, defaults={"slug": "index"})
        app.add_url_rule("/page/<slug>", "page", page)

        client = app.test_client()
        resp = client.get("/page")
        assert resp.status_code == 200
        assert resp.text == "Page: index"

    def test_multiple_defaults_accumulated(self):
        """Multiple defaults from separate decorators are merged."""
        app = Flask(__name__)

        def view(a, b):
            return f"{a},{b}"

        app.add_url_rule("/both", "view", view, defaults={"a": "1"})
        # Second call adds another default for the same endpoint
        app.add_url_rule("/both-alt", "view", view, defaults={"b": "2"})

        client = app.test_client()
        # /both should have a=1 and b=2 (accumulated)
        resp = client.get("/both")
        assert resp.status_code == 200
        assert resp.text == "1,2"

    def test_blueprint_route_with_defaults(self):
        """defaults= works on blueprint routes."""
        app = Flask(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.route("/items", defaults={"item_id": "all"})
        @bp.route("/items/<item_id>")
        def items(item_id):
            return f"items:{item_id}"

        app.register_blueprint(bp)

        client = app.test_client()
        resp = client.get("/api/items")
        assert resp.status_code == 200
        assert resp.text == "items:all"

        resp = client.get("/api/items/42")
        assert resp.status_code == 200
        assert resp.text == "items:42"

    def test_defaults_not_stored_when_none(self):
        """No entry is created in _endpoint_defaults when defaults is None."""
        app = Flask(__name__)

        @app.route("/plain")
        def plain():
            return "ok"

        assert "plain" not in app._endpoint_defaults
