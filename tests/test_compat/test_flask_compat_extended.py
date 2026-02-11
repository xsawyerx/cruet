"""Extended Flask compatibility tests.

Covers API surface added in Priorities 6-9: shorthand decorators, request/response
mutability, flash messaging, config loading, blueprints, static files, template
hooks.  Every test runs identically against both Flask and cruet.
"""

import io
import json
import os
import tempfile
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_header(resp, name):
    """Get a response header from either Flask or cruet test response."""
    if hasattr(resp, "headers") and hasattr(resp.headers, "get"):
        return resp.headers.get(name)
    if hasattr(resp, "get_header"):
        return resp.get_header(name)
    return None


def _import(framework, *names):
    """Import names from the given framework."""
    mod = __import__(framework)
    return tuple(getattr(mod, n) for n in names)


# ---------------------------------------------------------------------------
# Fixture: parametrized app
# ---------------------------------------------------------------------------

@pytest.fixture(params=["flask", "cruet"])
def framework(request):
    if request.param == "flask":
        pytest.importorskip("flask")
    return request.param


@pytest.fixture
def app_factory(framework):
    """Return a factory that creates a bare app for the framework."""
    def factory(**kwargs):
        if framework == "flask":
            import flask
            return flask.Flask(__name__, **kwargs)
        else:
            import cruet
            return cruet.Flask(__name__, **kwargs)
    return factory


@pytest.fixture
def fw(framework):
    """Return the framework module itself."""
    if framework == "flask":
        import flask
        return flask
    else:
        import cruet
        return cruet


# ---------------------------------------------------------------------------
# Shorthand route decorators
# ---------------------------------------------------------------------------

class TestShorthandDecorators:
    def test_get_decorator(self, app_factory, fw):
        app = app_factory()

        @app.get("/items")
        def items():
            return "items"

        client = app.test_client()
        resp = client.get("/items")
        assert resp.status_code == 200
        assert b"items" in resp.data

    def test_post_decorator(self, app_factory, fw):
        app = app_factory()

        @app.post("/items")
        def create():
            return "created"

        resp = app.test_client().post("/items")
        assert resp.status_code == 200
        assert b"created" in resp.data

    def test_put_decorator(self, app_factory, fw):
        app = app_factory()

        @app.put("/items/<int:id>")
        def update(id):
            return f"updated {id}"

        resp = app.test_client().put("/items/5")
        assert resp.status_code == 200
        assert b"updated 5" in resp.data

    def test_delete_decorator(self, app_factory, fw):
        app = app_factory()

        @app.delete("/items/<int:id>")
        def remove(id):
            return f"deleted {id}"

        resp = app.test_client().delete("/items/5")
        assert resp.status_code == 200
        assert b"deleted 5" in resp.data

    def test_get_rejects_post(self, app_factory, fw):
        app = app_factory()

        @app.get("/only-get")
        def only_get():
            return "ok"

        resp = app.test_client().post("/only-get")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Request: get_json, get_data, values, full_path, scheme
# ---------------------------------------------------------------------------

class TestRequestMethods:
    def test_get_json_basic(self, app_factory, fw):
        app = app_factory()

        @app.post("/api")
        def api():
            data = fw.request.get_json()
            return {"got": data["key"]}

        resp = app.test_client().post(
            "/api", data=json.dumps({"key": "val"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        result = json.loads(resp.data)
        assert result["got"] == "val"

    def test_get_json_force(self, app_factory, fw):
        app = app_factory()

        @app.post("/api")
        def api():
            data = fw.request.get_json(force=True)
            return {"got": data["key"]}

        resp = app.test_client().post(
            "/api", data=json.dumps({"key": "forced"}),
            content_type="text/plain",
        )
        result = json.loads(resp.data)
        assert result["got"] == "forced"

    def test_get_json_silent(self, app_factory, fw):
        app = app_factory()

        @app.post("/api")
        def api():
            data = fw.request.get_json(silent=True)
            return {"result": data is None}

        resp = app.test_client().post(
            "/api", data=b"not-json",
            content_type="application/json",
        )
        result = json.loads(resp.data)
        assert result["result"] is True

    def test_get_data_as_text(self, app_factory, fw):
        app = app_factory()

        @app.post("/echo")
        def echo():
            text = fw.request.get_data(as_text=True)
            return text

        resp = app.test_client().post("/echo", data=b"hello text")
        assert resp.status_code == 200
        assert b"hello text" in resp.data

    def test_values_from_query(self, app_factory, fw):
        app = app_factory()

        @app.route("/search")
        def search():
            return fw.request.values.get("q", "none")

        resp = app.test_client().get("/search", query_string="q=test")
        assert b"test" in resp.data

    def test_full_path(self, app_factory, fw):
        app = app_factory()

        @app.route("/page")
        def page():
            return fw.request.full_path

        resp = app.test_client().get("/page", query_string="x=1")
        assert b"/page?x=1" in resp.data

    def test_full_path_no_query(self, app_factory, fw):
        app = app_factory()

        @app.route("/page")
        def page():
            return fw.request.full_path

        resp = app.test_client().get("/page")
        # Both Flask and cruet include trailing ? with empty query string
        assert b"/page?" in resp.data

    def test_scheme(self, app_factory, fw):
        app = app_factory()

        @app.route("/scheme")
        def scheme():
            return fw.request.scheme

        resp = app.test_client().get("/scheme")
        assert b"http" in resp.data

    def test_is_secure_http(self, app_factory, fw):
        app = app_factory()

        @app.route("/secure")
        def secure():
            return str(fw.request.is_secure)

        resp = app.test_client().get("/secure")
        assert b"False" in resp.data

    def test_user_agent(self, app_factory, fw):
        app = app_factory()

        @app.route("/ua")
        def ua():
            ua_val = fw.request.user_agent
            # Flask returns a UserAgent object, cruet returns a string
            return str(ua_val)

        resp = app.test_client().get("/ua")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response mutability
# ---------------------------------------------------------------------------

class TestResponseMutability:
    def test_set_status_code_in_after_request(self, app_factory, fw):
        app = app_factory()

        @app.after_request
        def force_201(response):
            response.status_code = 201
            return response

        @app.route("/")
        def index():
            return "ok"

        resp = app.test_client().get("/")
        assert resp.status_code == 201

    def test_set_data_in_after_request(self, app_factory, fw):
        app = app_factory()

        @app.after_request
        def wrap(response):
            response.data = b"wrapped"
            return response

        @app.route("/")
        def index():
            return "original"

        resp = app.test_client().get("/")
        assert resp.data == b"wrapped"

    def test_response_get_data_as_text(self, app_factory, fw):
        app = app_factory()

        @app.after_request
        def check(response):
            text = response.get_data(as_text=True)
            response.data = text.upper().encode()
            return response

        @app.route("/")
        def index():
            return "hello"

        resp = app.test_client().get("/")
        assert resp.data == b"HELLO"

    def test_response_location_set(self, app_factory, fw):
        app = app_factory()

        @app.route("/redir")
        def redir():
            resp = fw.make_response("", 302)
            resp.location = "/target"
            return resp

        resp = app.test_client().get("/redir")
        assert resp.status_code == 302
        assert _get_header(resp, "Location") == "/target"


# ---------------------------------------------------------------------------
# Flash messaging
# ---------------------------------------------------------------------------

class TestFlashMessaging:
    def test_flash_and_retrieve_in_same_request(self, app_factory, fw):
        app = app_factory()
        app.secret_key = "test-secret"

        @app.route("/test")
        def test_flash():
            fw.flash("hello")
            msgs = fw.get_flashed_messages()
            return ",".join(msgs)

        resp = app.test_client().get("/test")
        assert b"hello" in resp.data

    def test_flash_with_categories(self, app_factory, fw):
        app = app_factory()
        app.secret_key = "test-secret"

        @app.route("/test")
        def test_flash():
            fw.flash("info msg", "info")
            fw.flash("error msg", "error")
            msgs = fw.get_flashed_messages(with_categories=True)
            return str(msgs)

        resp = app.test_client().get("/test")
        assert b"info" in resp.data
        assert b"error" in resp.data

    def test_flash_consumed(self, app_factory, fw):
        app = app_factory()
        app.secret_key = "test-secret"

        @app.route("/test")
        def test_flash():
            fw.flash("once")
            first = fw.get_flashed_messages()
            second = fw.get_flashed_messages()
            return f"{len(first)},{len(second)}"

        resp = app.test_client().get("/test")
        # Flask caches messages on the request context — multiple calls
        # within the same request return the same list.
        assert b"1,1" in resp.data


# ---------------------------------------------------------------------------
# Context processor and template rendering
# ---------------------------------------------------------------------------

class TestTemplateHooks:
    def test_context_processor(self, app_factory, fw):
        app = app_factory()

        @app.context_processor
        def inject():
            return {"site": "TestSite"}

        @app.route("/")
        def index():
            return fw.render_template_string("{{ site }}")

        resp = app.test_client().get("/")
        assert b"TestSite" in resp.data

    def test_template_filter(self, app_factory, fw):
        app = app_factory()

        @app.template_filter("rev")
        def reverse_filter(s):
            return s[::-1]

        @app.route("/")
        def index():
            return fw.render_template_string("{{ 'hello' | rev }}")

        resp = app.test_client().get("/")
        assert b"olleh" in resp.data

    def test_template_global(self, app_factory, fw):
        app = app_factory()

        @app.template_global("version")
        def get_version():
            return "1.0"

        @app.route("/")
        def index():
            return fw.render_template_string("v{{ version() }}")

        resp = app.test_client().get("/")
        assert b"v1.0" in resp.data


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_register_error_handler(self, app_factory, fw):
        app = app_factory()

        def handle_404(e):
            return "not here", 404

        app.register_error_handler(404, handle_404)

        @app.route("/")
        def index():
            return "ok"

        resp = app.test_client().get("/nope")
        assert resp.status_code == 404
        assert b"not here" in resp.data


# ---------------------------------------------------------------------------
# App properties
# ---------------------------------------------------------------------------

class TestAppProperties:
    def test_app_name(self, app_factory, fw):
        app = app_factory()
        assert app.name == __name__

    def test_app_logger(self, app_factory, fw):
        import logging
        app = app_factory()
        assert isinstance(app.logger, logging.Logger)

    def test_app_extensions(self, app_factory, fw):
        app = app_factory()
        assert isinstance(app.extensions, dict)


# ---------------------------------------------------------------------------
# Blueprint: shorthand decorators and add_url_rule
# ---------------------------------------------------------------------------

class TestBlueprintCompat:
    def test_blueprint_get_decorator(self, app_factory, fw):
        app = app_factory()
        bp = fw.Blueprint("api", __name__, url_prefix="/api")

        @bp.get("/items")
        def items():
            return "items"

        app.register_blueprint(bp)
        resp = app.test_client().get("/api/items")
        assert resp.status_code == 200
        assert b"items" in resp.data

    def test_blueprint_add_url_rule(self, app_factory, fw):
        app = app_factory()
        bp = fw.Blueprint("api", __name__, url_prefix="/api")

        def my_view():
            return "manual"

        bp.add_url_rule("/manual", "manual_view", my_view)
        app.register_blueprint(bp)

        resp = app.test_client().get("/api/manual")
        assert b"manual" in resp.data


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestConfigCompat:
    def test_from_mapping(self, app_factory, fw):
        app = app_factory()
        app.config.from_mapping(MY_KEY="my_value")
        assert app.config["MY_KEY"] == "my_value"

    def test_from_pyfile(self, app_factory, fw, tmp_path):
        f = tmp_path / "settings.py"
        f.write_text("TESTING = True\nMY_VAR = 42\n")
        app = app_factory()
        app.config.from_pyfile(str(f))
        assert app.config["MY_VAR"] == 42
        assert app.testing is True

    def test_from_file_json(self, app_factory, fw, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"DEBUG": True, "PORT": 9000}))
        app = app_factory()
        app.config.from_file(str(f), load=json.load)
        assert app.config["PORT"] == 9000

    def test_from_pyfile_silent(self, app_factory, fw):
        app = app_factory()
        result = app.config.from_pyfile("/nonexistent.py", silent=True)
        assert result is False


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

class TestStaticFilesCompat:
    def test_static_folder_default(self, app_factory, fw):
        app = app_factory()
        assert app.static_folder is not None
        assert app.static_folder.endswith("static")

    def test_serve_static_file(self, app_factory, fw):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test.txt"), "w") as f:
                f.write("static content")

            app = app_factory(static_folder=d, static_url_path="/static")
            resp = app.test_client().get("/static/test.txt")
            assert resp.status_code == 200
            assert b"static content" in resp.data


# ---------------------------------------------------------------------------
# send_file / send_from_directory
# ---------------------------------------------------------------------------

class TestSendFileCompat:
    def test_send_file(self, app_factory, fw):
        app = app_factory()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"file data")
            f.flush()
            path = f.name

        try:
            @app.route("/dl")
            def download():
                return fw.send_file(path)

            resp = app.test_client().get("/dl")
            assert resp.status_code == 200
            assert b"file data" in resp.data
        finally:
            os.unlink(path)

    def test_send_from_directory(self, app_factory, fw):
        app = app_factory()

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "data.txt"), "w") as f:
                f.write("dir data")

            @app.route("/file")
            def serve():
                return fw.send_from_directory(d, "data.txt")

            resp = app.test_client().get("/file")
            assert resp.status_code == 200
            assert b"dir data" in resp.data


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

class TestLifecycleCompat:
    def test_before_request(self, app_factory, fw):
        app = app_factory()
        calls = []

        @app.before_request
        def track():
            calls.append("before")

        @app.route("/")
        def index():
            return "ok"

        app.test_client().get("/")
        assert calls == ["before"]

    def test_after_request(self, app_factory, fw):
        app = app_factory()

        @app.after_request
        def add_header(response):
            response.headers["X-After"] = "yes"
            return response

        @app.route("/")
        def index():
            return "ok"

        resp = app.test_client().get("/")
        assert _get_header(resp, "X-After") == "yes"

    def test_teardown_request(self, app_factory, fw):
        app = app_factory()
        calls = []

        @app.teardown_request
        def track(exc):
            calls.append("teardown")

        @app.route("/")
        def index():
            return "ok"

        app.test_client().get("/")
        assert calls == ["teardown"]
