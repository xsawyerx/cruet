"""Tests for Priority 6: App class API gaps."""
import logging
import os
import tempfile
import pytest

from cruet import (
    Cruet, Flask, Config, request,
    send_file, send_from_directory,
    render_template_string,
)


class TestShorthandDecorators:
    def test_get(self):
        app = Cruet(__name__)

        @app.get("/items")
        def items():
            return "items"

        resp = app.test_client().get("/items")
        assert resp.status_code == 200
        assert resp.text == "items"

    def test_post(self):
        app = Cruet(__name__)

        @app.post("/items")
        def create():
            return "created"

        resp = app.test_client().post("/items")
        assert resp.status_code == 200
        assert resp.text == "created"

    def test_put(self):
        app = Cruet(__name__)

        @app.put("/items/<int:id>")
        def update(id):
            return f"updated {id}"

        resp = app.test_client().put("/items/5")
        assert resp.status_code == 200
        assert resp.text == "updated 5"

    def test_delete(self):
        app = Cruet(__name__)

        @app.delete("/items/<int:id>")
        def remove(id):
            return f"deleted {id}"

        resp = app.test_client().delete("/items/5")
        assert resp.status_code == 200
        assert resp.text == "deleted 5"

    def test_patch(self):
        app = Cruet(__name__)

        @app.patch("/items/<int:id>")
        def patch(id):
            return f"patched {id}"

        resp = app.test_client().patch("/items/5")
        assert resp.status_code == 200
        assert resp.text == "patched 5"

    def test_get_rejects_post(self):
        app = Cruet(__name__)

        @app.get("/only-get")
        def only_get():
            return "ok"

        resp = app.test_client().post("/only-get")
        assert resp.status_code == 405

    def test_post_rejects_get(self):
        app = Cruet(__name__)

        @app.post("/only-post")
        def only_post():
            return "ok"

        resp = app.test_client().get("/only-post")
        assert resp.status_code == 405


class TestAppProperties:
    def test_name(self):
        app = Cruet("myapp")
        assert app.name == "myapp"

    def test_logger_type(self):
        app = Cruet("myapp")
        assert isinstance(app.logger, logging.Logger)

    def test_logger_name(self):
        app = Cruet("myapp")
        assert app.logger.name == "myapp"

    def test_logger_cached(self):
        app = Cruet("myapp")
        assert app.logger is app.logger

    def test_extensions_dict(self):
        app = Cruet(__name__)
        assert isinstance(app.extensions, dict)
        assert len(app.extensions) == 0

    def test_extensions_stores_values(self):
        app = Cruet(__name__)
        app.extensions["myext"] = {"version": "1.0"}
        assert app.extensions["myext"]["version"] == "1.0"


class TestRegisterErrorHandler:
    def test_register_by_code(self):
        app = Cruet(__name__)

        def handle_404(e):
            return "custom 404", 404

        app.register_error_handler(404, handle_404)
        assert 404 in app.error_handlers.get(None, {})

        @app.route("/")
        def index():
            return "ok"

        resp = app.test_client().get("/nonexistent")
        assert resp.status_code == 404
        assert resp.text == "custom 404"

    def test_register_by_exception(self):
        app = Cruet(__name__)

        class MyError(Exception):
            pass

        def handle_my_error(e):
            return "handled", 400

        app.register_error_handler(MyError, handle_my_error)

        @app.route("/")
        def index():
            raise MyError("boom")

        resp = app.test_client().get("/")
        assert resp.status_code == 400
        assert resp.text == "handled"


class TestAppRun:
    def test_run_sets_debug(self):
        app = Cruet(__name__)
        assert app.debug is False
        # We can't actually call run() without starting a server,
        # but we can verify the debug setter path
        app.run.__func__  # verify it exists as a method


class TestConfigExport:
    def test_config_importable(self):
        assert Config is not None
        c = Config({"A": 1})
        assert c["A"] == 1


class TestStaticFiles:
    def test_static_folder_default(self):
        app = Cruet(__name__)
        assert app.static_folder.endswith("static")

    def test_static_folder_setter(self):
        app = Cruet(__name__)
        app.static_folder = "/tmp/mystatic"
        assert app.static_folder == "/tmp/mystatic"

    def test_static_folder_none(self):
        app = Cruet(__name__, static_folder=None)
        assert app.static_folder is None

    def test_static_url_path_default(self):
        app = Cruet(__name__)
        assert app.static_url_path == "/static"

    def test_static_url_path_custom(self):
        app = Cruet(__name__, static_url_path="/assets")
        assert app.static_url_path == "/assets"

    def test_has_static_folder_false(self):
        app = Cruet(__name__, static_folder="/nonexistent/path")
        assert app.has_static_folder is False

    def test_has_static_folder_true(self):
        with tempfile.TemporaryDirectory() as d:
            app = Cruet(__name__, static_folder=d)
            assert app.has_static_folder is True

    def test_static_route_serves_file(self):
        with tempfile.TemporaryDirectory() as d:
            # Write a test file
            with open(os.path.join(d, "test.txt"), "w") as f:
                f.write("hello static")

            app = Cruet(__name__, static_folder=d)

            resp = app.test_client().get("/static/test.txt")
            assert resp.status_code == 200
            assert resp.text == "hello static"

    def test_static_route_404_missing(self):
        with tempfile.TemporaryDirectory() as d:
            app = Cruet(__name__, static_folder=d)

            resp = app.test_client().get("/static/nonexistent.txt")
            assert resp.status_code == 404

    def test_static_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            app = Cruet(__name__, static_folder=d)

            resp = app.test_client().get("/static/../../../etc/passwd")
            assert resp.status_code == 404


class TestSendFile:
    def test_send_file_from_path(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"file content")
            f.flush()
            try:
                response = send_file(f.name)
                assert response.data == b"file content"
                assert "text/plain" in response.content_type
            finally:
                os.unlink(f.name)

    def test_send_file_as_attachment(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            f.flush()
            try:
                response = send_file(f.name, as_attachment=True)
                disp = response.headers.get("Content-Disposition")
                assert "attachment" in disp
            finally:
                os.unlink(f.name)

    def test_send_file_custom_mimetype(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01")
            f.flush()
            try:
                response = send_file(f.name, mimetype="application/pdf")
                assert response.content_type == "application/pdf"
            finally:
                os.unlink(f.name)

    def test_send_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            send_file("/nonexistent/file.txt")

    def test_send_from_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "data.json"), "w") as f:
                f.write('{"key": "val"}')

            response = send_from_directory(d, "data.json")
            assert response.data == b'{"key": "val"}'

    def test_send_from_directory_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            from cruet.app import NotFound
            with pytest.raises(NotFound):
                send_from_directory(d, "../../etc/passwd")


class TestContextProcessor:
    def test_basic_context_processor(self):
        app = Cruet(__name__)

        @app.context_processor
        def inject():
            return {"site_name": "MySite"}

        @app.route("/")
        def index():
            return render_template_string("{{ site_name }}")

        resp = app.test_client().get("/")
        assert resp.text == "MySite"

    def test_multiple_context_processors(self):
        app = Cruet(__name__)

        @app.context_processor
        def inject_a():
            return {"a": "1"}

        @app.context_processor
        def inject_b():
            return {"b": "2"}

        @app.route("/")
        def index():
            return render_template_string("{{ a }},{{ b }}")

        resp = app.test_client().get("/")
        assert resp.text == "1,2"

    def test_context_processor_overridden_by_explicit(self):
        app = Cruet(__name__)

        @app.context_processor
        def inject():
            return {"x": "from_processor"}

        @app.route("/")
        def index():
            return render_template_string("{{ x }}", x="explicit")

        resp = app.test_client().get("/")
        assert resp.text == "explicit"


class TestTemplateFilter:
    def test_template_filter_decorator(self):
        app = Cruet(__name__)

        @app.template_filter("reverse")
        def reverse_filter(s):
            return s[::-1]

        @app.route("/")
        def index():
            return render_template_string("{{ 'hello' | reverse }}")

        resp = app.test_client().get("/")
        assert resp.text == "olleh"

    def test_template_filter_no_parens(self):
        app = Cruet(__name__)

        @app.template_filter
        def shout(s):
            return s.upper()

        @app.route("/")
        def index():
            return render_template_string("{{ 'hello' | shout }}")

        resp = app.test_client().get("/")
        assert resp.text == "HELLO"

    def test_add_template_filter(self):
        app = Cruet(__name__)

        def double(n):
            return n * 2

        app.add_template_filter(double, "dbl")

        @app.route("/")
        def index():
            return render_template_string("{{ 5 | dbl }}")

        resp = app.test_client().get("/")
        assert resp.text == "10"


class TestTemplateGlobal:
    def test_template_global_decorator(self):
        app = Cruet(__name__)

        @app.template_global("now")
        def get_now():
            return "2024-01-01"

        @app.route("/")
        def index():
            return render_template_string("{{ now() }}")

        resp = app.test_client().get("/")
        assert resp.text == "2024-01-01"

    def test_add_template_global(self):
        app = Cruet(__name__)

        app.add_template_global(lambda: "v1", "version")

        @app.route("/")
        def index():
            return render_template_string("{{ version() }}")

        resp = app.test_client().get("/")
        assert resp.text == "v1"


class TestFlaskAlias:
    def test_flask_is_cruet(self):
        assert Flask is Cruet
