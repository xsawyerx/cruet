"""Tests for the Blueprint system."""
import pytest
from cruet import Cruet, Blueprint


class TestBlueprintRegistration:
    def test_register_blueprint(self):
        app = Cruet(__name__)
        bp = Blueprint("auth", __name__, url_prefix="/auth")

        @bp.route("/login")
        def login():
            return "login page"

        app.register_blueprint(bp)
        resp = app.test_client().get("/auth/login")
        assert resp.status_code == 200
        assert resp.text == "login page"

    def test_blueprint_url_prefix(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api/v1")

        @bp.route("/users")
        def users():
            return "user list"

        app.register_blueprint(bp)
        resp = app.test_client().get("/api/v1/users")
        assert resp.status_code == 200
        assert resp.text == "user list"

    def test_blueprint_without_prefix(self):
        app = Cruet(__name__)
        bp = Blueprint("main", __name__)

        @bp.route("/hello")
        def hello():
            return "hello"

        app.register_blueprint(bp)
        assert app.test_client().get("/hello").text == "hello"


class TestBlueprintScopedBeforeRequest:
    def test_blueprint_before_request(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")
        called = [False]

        @bp.before_request
        def before():
            called[0] = True

        @bp.route("/data")
        def data():
            return "data"

        @app.route("/")
        def index():
            return "index"

        app.register_blueprint(bp)
        client = app.test_client()

        # Blueprint before_request should run for blueprint routes
        called[0] = False
        client.get("/api/data")
        assert called[0] is True

        # Should not run for non-blueprint routes
        called[0] = False
        client.get("/")
        assert called[0] is False


class TestBlueprintErrorHandlers:
    def test_blueprint_error_handler(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.errorhandler(404)
        def bp_not_found(e):
            return "api 404", 404

        app.register_blueprint(bp)
        resp = app.test_client().get("/api/nonexistent")
        assert resp.status_code == 404
        assert resp.text == "api 404"


class TestMultipleBlueprints:
    def test_two_blueprints(self):
        app = Cruet(__name__)
        auth = Blueprint("auth", __name__, url_prefix="/auth")
        posts = Blueprint("posts", __name__, url_prefix="/posts")

        @auth.route("/login")
        def login():
            return "login"

        @posts.route("/list")
        def post_list():
            return "posts"

        app.register_blueprint(auth)
        app.register_blueprint(posts)

        client = app.test_client()
        assert client.get("/auth/login").text == "login"
        assert client.get("/posts/list").text == "posts"

    def test_nested_style_blueprints(self):
        """Multiple blueprints with nested prefixes."""
        app = Cruet(__name__)
        api = Blueprint("api", __name__, url_prefix="/api")
        v1 = Blueprint("v1", __name__, url_prefix="/api/v1")

        @api.route("/status")
        def status():
            return "ok"

        @v1.route("/users")
        def users():
            return "users v1"

        app.register_blueprint(api)
        app.register_blueprint(v1)

        client = app.test_client()
        assert client.get("/api/status").text == "ok"
        assert client.get("/api/v1/users").text == "users v1"
