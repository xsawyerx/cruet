"""Tests for before_request, after_request, and error handlers."""
import pytest
from cruet import Cruet
from cruet._cruet import CResponse


class TestBeforeRequest:
    def test_before_request_runs(self):
        app = Cruet(__name__)
        called = [False]

        @app.before_request
        def before():
            called[0] = True

        @app.route("/")
        def index():
            return "ok"

        app.test_client().get("/")
        assert called[0] is True

    def test_before_request_short_circuit(self):
        app = Cruet(__name__)

        @app.before_request
        def before():
            return "intercepted", 403

        @app.route("/")
        def index():
            return "should not reach"

        resp = app.test_client().get("/")
        assert resp.status_code == 403
        assert resp.text == "intercepted"

    def test_before_request_ordering(self):
        app = Cruet(__name__)
        order = []

        @app.before_request
        def first():
            order.append("first")

        @app.before_request
        def second():
            order.append("second")

        @app.route("/")
        def index():
            return "ok"

        app.test_client().get("/")
        assert order == ["first", "second"]


class TestAfterRequest:
    def test_after_request_modifies_response(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "ok"

        @app.after_request
        def after(response):
            response.headers.set("X-After", "modified")
            return response

        resp = app.test_client().get("/")
        assert resp.get_header("X-After") == "modified"

    def test_after_request_reverse_order(self):
        app = Cruet(__name__)
        order = []

        @app.route("/")
        def index():
            return "ok"

        @app.after_request
        def first(response):
            order.append("first")
            return response

        @app.after_request
        def second(response):
            order.append("second")
            return response

        app.test_client().get("/")
        # after_request runs in reverse registration order
        assert order == ["second", "first"]


class TestErrorHandlers:
    def test_404_handler(self):
        app = Cruet(__name__)

        @app.errorhandler(404)
        def not_found(e):
            return "custom 404", 404

        resp = app.test_client().get("/nonexistent")
        assert resp.status_code == 404
        assert resp.text == "custom 404"

    def test_custom_exception_handler(self):
        app = Cruet(__name__)

        class MyError(Exception):
            pass

        @app.errorhandler(MyError)
        def handle_my_error(e):
            return "handled", 400

        @app.route("/")
        def index():
            raise MyError("test")

        resp = app.test_client().get("/")
        assert resp.status_code == 400
        assert resp.text == "handled"

    def test_unhandled_500(self):
        app = Cruet(__name__)

        @app.route("/")
        def index():
            raise ValueError("unexpected")

        resp = app.test_client().get("/")
        assert resp.status_code == 500
