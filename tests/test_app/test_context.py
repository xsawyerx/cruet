"""Tests for application and request context."""
import pytest
from cruet import (
    Cruet, request, g, current_app,
    has_request_context, has_app_context, after_this_request,
)


class TestRequestContext:
    def test_request_proxy_in_view(self):
        app = Cruet(__name__)

        @app.route("/method")
        def show_method():
            return request.method

        resp = app.test_client().get("/method")
        assert resp.text == "GET"

    def test_request_path_in_view(self):
        app = Cruet(__name__)

        @app.route("/info")
        def info():
            return request.path

        resp = app.test_client().get("/info")
        assert resp.text == "/info"

    def test_request_args_in_view(self):
        app = Cruet(__name__)

        @app.route("/search")
        def search():
            q = request.args.get("q", "")
            return q

        resp = app.test_client().get("/search", query_string="q=hello")
        assert resp.text == "hello"


class TestAppContext:
    def test_current_app_in_view(self):
        app = Cruet("myapp")

        @app.route("/")
        def index():
            return current_app.import_name

        resp = app.test_client().get("/")
        assert resp.text == "myapp"

    def test_g_object(self):
        app = Cruet(__name__)

        @app.before_request
        def set_g():
            g.value = "from_before"

        @app.route("/")
        def index():
            return g.value

        resp = app.test_client().get("/")
        assert resp.text == "from_before"

    def test_g_isolated_between_requests(self):
        app = Cruet(__name__)
        call_count = [0]

        @app.before_request
        def set_g():
            call_count[0] += 1
            g.count = call_count[0]

        @app.route("/")
        def index():
            return str(g.count)

        client = app.test_client()
        assert client.get("/").text == "1"
        assert client.get("/").text == "2"


class TestContextOutsideRequest:
    def test_request_outside_context_raises(self):
        with pytest.raises(RuntimeError):
            _ = request.method

    def test_current_app_outside_context_raises(self):
        with pytest.raises(RuntimeError):
            _ = current_app.import_name

    def test_app_context_manual(self):
        app = Cruet("test")
        with app.app_context():
            assert current_app.import_name == "test"

    def test_test_request_context(self):
        app = Cruet("test")
        with app.test_request_context("/hello", method="POST"):
            assert request.method == "POST"
            assert request.path == "/hello"


class TestHasContext:
    def test_has_request_context_false_outside(self):
        assert has_request_context() is False

    def test_has_app_context_false_outside(self):
        assert has_app_context() is False

    def test_has_request_context_true_inside(self):
        app = Cruet("test")
        with app.test_request_context("/"):
            assert has_request_context() is True

    def test_has_app_context_true_inside(self):
        app = Cruet("test")
        with app.app_context():
            assert has_app_context() is True

    def test_has_app_context_true_in_request(self):
        """Request context also pushes an app context."""
        app = Cruet("test")
        with app.test_request_context("/"):
            assert has_app_context() is True

    def test_has_request_context_false_after_pop(self):
        app = Cruet("test")
        with app.test_request_context("/"):
            assert has_request_context() is True
        assert has_request_context() is False

    def test_has_context_in_view(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return f"{has_request_context()},{has_app_context()}"

        resp = app.test_client().get("/")
        assert resp.text == "True,True"


class TestRequestAttributes:
    def test_endpoint_set_during_dispatch(self):
        app = Cruet(__name__)

        @app.route("/hello")
        def hello():
            return request.endpoint

        resp = app.test_client().get("/hello")
        assert resp.text == "hello"

    def test_view_args_set_during_dispatch(self):
        app = Cruet(__name__)

        @app.route("/user/<name>")
        def user(name):
            return str(request.view_args)

        resp = app.test_client().get("/user/alice")
        assert resp.text == "{'name': 'alice'}"

    def test_view_args_with_converter(self):
        app = Cruet(__name__)

        @app.route("/item/<int:id>")
        def item(id):
            return str(request.view_args)

        resp = app.test_client().get("/item/42")
        assert resp.text == "{'id': 42}"

    def test_blueprint_set_during_dispatch(self):
        from cruet import Blueprint

        app = Cruet(__name__)
        bp = Blueprint("admin", __name__, url_prefix="/admin")

        @bp.route("/dashboard")
        def dashboard():
            return request.blueprint or "none"

        app.register_blueprint(bp)
        resp = app.test_client().get("/admin/dashboard")
        assert resp.text == "admin"

    def test_blueprint_none_for_app_route(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return str(request.blueprint)

        resp = app.test_client().get("/")
        assert resp.text == "None"

    def test_endpoint_with_blueprint(self):
        from cruet import Blueprint

        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.route("/data")
        def data():
            return request.endpoint

        app.register_blueprint(bp)
        resp = app.test_client().get("/api/data")
        assert resp.text == "api.data"


class TestAfterThisRequest:
    def test_adds_header_to_response(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            @after_this_request
            def add_header(response):
                response.headers.set("X-Custom", "hello")
                return response
            return "ok"

        resp = app.test_client().get("/")
        assert resp.status_code == 200
        assert resp.text == "ok"
        assert resp.get_header("X-Custom") == "hello"

    def test_multiple_callbacks(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            @after_this_request
            def add_a(response):
                response.headers.set("X-A", "1")
                return response

            @after_this_request
            def add_b(response):
                response.headers.set("X-B", "2")
                return response
            return "ok"

        resp = app.test_client().get("/")
        assert resp.get_header("X-A") == "1"
        assert resp.get_header("X-B") == "2"

    def test_runs_in_reverse_order(self):
        app = Cruet(__name__)
        order = []

        @app.route("/")
        def index():
            @after_this_request
            def first(response):
                order.append("first")
                return response

            @after_this_request
            def second(response):
                order.append("second")
                return response
            return "ok"

        app.test_client().get("/")
        assert order == ["second", "first"]

    def test_isolated_between_requests(self):
        app = Cruet(__name__)
        call_count = [0]

        @app.route("/")
        def index():
            @after_this_request
            def count(response):
                call_count[0] += 1
                return response
            return "ok"

        client = app.test_client()
        client.get("/")
        assert call_count[0] == 1
        client.get("/")
        assert call_count[0] == 2  # Each request registers its own

    def test_runs_before_app_after_request(self):
        app = Cruet(__name__)
        order = []

        @app.after_request
        def app_after(response):
            order.append("app_after")
            return response

        @app.route("/")
        def index():
            @after_this_request
            def per_request(response):
                order.append("per_request")
                return response
            return "ok"

        app.test_client().get("/")
        assert order == ["per_request", "app_after"]

    def test_outside_context_raises(self):
        with pytest.raises(RuntimeError):
            @after_this_request
            def nope(response):
                return response

    def test_does_not_affect_other_routes(self):
        app = Cruet(__name__)

        @app.route("/with")
        def with_callback():
            @after_this_request
            def add_header(response):
                response.headers.set("X-Special", "yes")
                return response
            return "with"

        @app.route("/without")
        def without_callback():
            return "without"

        client = app.test_client()
        resp1 = client.get("/with")
        assert resp1.get_header("X-Special") == "yes"
        resp2 = client.get("/without")
        assert resp2.get_header("X-Special") is None
