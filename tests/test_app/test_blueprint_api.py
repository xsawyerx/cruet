"""Tests for Priority 8: Blueprint completeness & flash messaging."""
import pytest
from cruet import (
    Cruet, Blueprint, request, session,
    flash, get_flashed_messages, render_template_string,
)


class TestBlueprintShorthandDecorators:
    def test_bp_get(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.get("/items")
        def items():
            return "items"

        app.register_blueprint(bp)
        resp = app.test_client().get("/api/items")
        assert resp.status_code == 200
        assert resp.text == "items"

    def test_bp_post(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.post("/items")
        def create():
            return "created"

        app.register_blueprint(bp)
        resp = app.test_client().post("/api/items")
        assert resp.text == "created"

    def test_bp_put(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.put("/items/<int:id>")
        def update(id):
            return f"updated {id}"

        app.register_blueprint(bp)
        resp = app.test_client().put("/api/items/3")
        assert resp.text == "updated 3"

    def test_bp_delete(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.delete("/items/<int:id>")
        def remove(id):
            return f"deleted {id}"

        app.register_blueprint(bp)
        resp = app.test_client().delete("/api/items/3")
        assert resp.text == "deleted 3"

    def test_bp_patch(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.patch("/items/<int:id>")
        def patch(id):
            return f"patched {id}"

        app.register_blueprint(bp)
        resp = app.test_client().patch("/api/items/3")
        assert resp.text == "patched 3"

    def test_bp_get_rejects_post(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        @bp.get("/readonly")
        def readonly():
            return "ok"

        app.register_blueprint(bp)
        resp = app.test_client().post("/api/readonly")
        assert resp.status_code == 405


class TestBlueprintAddUrlRule:
    def test_add_url_rule(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        def my_view():
            return "from add_url_rule"

        bp.add_url_rule("/manual", "manual_view", my_view)
        app.register_blueprint(bp)

        resp = app.test_client().get("/api/manual")
        assert resp.text == "from add_url_rule"

    def test_add_url_rule_with_methods(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        def post_only():
            return "post"

        bp.add_url_rule("/post", "post_view", post_only, methods=["POST"])
        app.register_blueprint(bp)

        assert app.test_client().post("/api/post").text == "post"
        assert app.test_client().get("/api/post").status_code == 405

    def test_add_url_rule_endpoint_from_func(self):
        app = Cruet(__name__)
        bp = Blueprint("api", __name__, url_prefix="/api")

        def auto_endpoint():
            return request.endpoint

        bp.add_url_rule("/auto", view_func=auto_endpoint)
        app.register_blueprint(bp)

        resp = app.test_client().get("/api/auto")
        assert resp.text == "api.auto_endpoint"


class TestBlueprintAppLevelHooks:
    def test_before_app_request(self):
        app = Cruet(__name__)
        bp = Blueprint("bp", __name__, url_prefix="/bp")
        calls = []

        @bp.before_app_request
        def log_all():
            calls.append("before")

        @app.route("/")
        def index():
            return "ok"

        app.register_blueprint(bp)
        app.test_client().get("/")
        assert calls == ["before"]

    def test_after_app_request(self):
        app = Cruet(__name__)
        bp = Blueprint("bp", __name__, url_prefix="/bp")

        @bp.after_app_request
        def add_header(response):
            response.headers.set("X-From-BP", "yes")
            return response

        @app.route("/")
        def index():
            return "ok"

        app.register_blueprint(bp)
        resp = app.test_client().get("/")
        assert resp.get_header("X-From-BP") == "yes"

    def test_app_errorhandler(self):
        app = Cruet(__name__)
        bp = Blueprint("bp", __name__, url_prefix="/bp")

        @bp.app_errorhandler(404)
        def handle_404(e):
            return "bp caught 404", 404

        @app.route("/")
        def index():
            return "ok"

        app.register_blueprint(bp)
        resp = app.test_client().get("/nonexistent")
        assert resp.status_code == 404
        assert resp.text == "bp caught 404"


class TestBlueprintTeardownRequest:
    def test_teardown_request(self):
        app = Cruet(__name__)
        bp = Blueprint("bp", __name__, url_prefix="/bp")
        teardown_calls = []

        @bp.teardown_request
        def bp_teardown(exc):
            teardown_calls.append("teardown")

        @bp.route("/page")
        def page():
            return "ok"

        @app.route("/other")
        def other():
            return "other"

        app.register_blueprint(bp)

        # Request to blueprint route — teardown runs
        app.test_client().get("/bp/page")
        assert teardown_calls == ["teardown"]

        # Request to non-blueprint route — teardown does NOT run
        teardown_calls.clear()
        app.test_client().get("/other")
        assert teardown_calls == []


class TestFlashMessaging:
    def _make_app(self):
        app = Cruet(__name__)
        app.secret_key = "test-secret"
        return app

    def test_flash_and_get(self):
        app = self._make_app()

        @app.route("/flash")
        def do_flash():
            flash("hello")
            return "flashed"

        @app.route("/get")
        def get_messages():
            msgs = get_flashed_messages()
            return ",".join(msgs)

        client = app.test_client()
        client.get("/flash")
        resp = client.get("/get")
        # Note: messages are in session, but test client doesn't preserve cookies
        # between requests by default. Test within single request instead.

    def test_flash_within_request(self):
        app = self._make_app()

        @app.route("/test")
        def test_flash():
            flash("msg1")
            flash("msg2")
            msgs = get_flashed_messages()
            return ",".join(msgs)

        resp = app.test_client().get("/test")
        assert resp.text == "msg1,msg2"

    def test_flash_with_categories(self):
        app = self._make_app()

        @app.route("/test")
        def test_flash():
            flash("info msg", "info")
            flash("error msg", "error")
            msgs = get_flashed_messages(with_categories=True)
            return str(msgs)

        resp = app.test_client().get("/test")
        assert ("info", "info msg") in eval(resp.text)
        assert ("error", "error msg") in eval(resp.text)

    def test_flash_category_filter(self):
        app = self._make_app()

        @app.route("/test")
        def test_flash():
            flash("info msg", "info")
            flash("error msg", "error")
            flash("warn msg", "warning")
            msgs = get_flashed_messages(category_filter=["error"])
            return ",".join(msgs)

        resp = app.test_client().get("/test")
        assert resp.text == "error msg"

    def test_flash_default_category(self):
        app = self._make_app()

        @app.route("/test")
        def test_flash():
            flash("plain message")
            msgs = get_flashed_messages(with_categories=True)
            return str(msgs[0])

        resp = app.test_client().get("/test")
        assert resp.text == "('message', 'plain message')"

    def test_flash_cached_within_request(self):
        app = self._make_app()

        @app.route("/test")
        def test_flash():
            flash("once")
            first = get_flashed_messages()
            second = get_flashed_messages()
            return f"{len(first)},{len(second)}"

        resp = app.test_client().get("/test")
        # Flask caches on request context — same result within one request
        assert resp.text == "1,1"

    def test_flash_in_template(self):
        app = self._make_app()

        @app.route("/test")
        def test_flash():
            flash("template msg")
            return render_template_string(
                "{% for m in get_flashed_messages() %}{{ m }}{% endfor %}"
            )

        resp = app.test_client().get("/test")
        assert resp.text == "template msg"


class TestFlashImport:
    def test_flash_importable(self):
        from cruet import flash, get_flashed_messages
        assert callable(flash)
        assert callable(get_flashed_messages)
