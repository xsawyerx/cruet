"""Tests for TestClient and TestResponse improvements."""

import pytest

from cruet import Cruet


def _make_app():
    app = Cruet(__name__)

    @app.route("/resource", methods=["PATCH", "TRACE"])
    def resource():
        return "ok"

    @app.route("/search")
    def search():
        from cruet import request
        q = request.args.get("q", "")
        return f"q={q}"

    @app.route("/page")
    def page():
        return "page"

    @app.route("/headers")
    def headers():
        from cruet import request
        return "hello", 200, {"X-Custom": "value123"}

    return app


class TestPatchMethod:
    def test_patch_method(self):
        app = _make_app()
        resp = app.test_client().patch("/resource")
        assert resp.status_code == 200
        assert resp.text == "ok"


class TestTraceMethod:
    def test_trace_method(self):
        app = _make_app()
        resp = app.test_client().trace("/resource")
        assert resp.status_code == 200
        assert resp.text == "ok"


class TestResponseHeaders:
    def test_response_headers_get(self):
        app = _make_app()
        resp = app.test_client().get("/headers")
        assert resp.headers.get("X-Custom") == "value123"

    def test_response_headers_case_insensitive(self):
        app = _make_app()
        resp = app.test_client().get("/headers")
        assert resp.headers.get("x-custom") == "value123"

    def test_response_headers_contains(self):
        app = _make_app()
        resp = app.test_client().get("/headers")
        assert "X-Custom" in resp.headers

    def test_response_headers_iteration(self):
        app = _make_app()
        resp = app.test_client().get("/headers")
        found = False
        for k, v in resp.headers:
            if k == "X-Custom" and v == "value123":
                found = True
        assert found

    def test_response_get_header_still_works(self):
        app = _make_app()
        resp = app.test_client().get("/headers")
        assert resp.get_header("X-Custom") == "value123"


class TestQueryStringInPath:
    def test_query_string_in_path(self):
        app = _make_app()
        resp = app.test_client().get("/search?q=test")
        assert resp.status_code == 200
        assert resp.text == "q=test"

    def test_query_string_in_path_empty(self):
        app = _make_app()
        resp = app.test_client().get("/page?")
        assert resp.status_code == 200
        assert resp.text == "page"

    def test_query_string_kwarg_still_works(self):
        app = _make_app()
        resp = app.test_client().get("/search", query_string="q=hello")
        assert resp.status_code == 200
        assert resp.text == "q=hello"

    def test_query_string_conflict_raises(self):
        app = _make_app()
        with pytest.raises(ValueError, match="Cannot provide query_string both"):
            app.test_client().get("/search?q=test", query_string="q=other")
