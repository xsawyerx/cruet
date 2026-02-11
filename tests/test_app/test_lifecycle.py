"""Tests for request lifecycle: before -> view -> after -> teardown."""
import pytest
from cruet import Cruet


class TestLifecycleOrder:
    def test_before_view_after_order(self):
        app = Cruet(__name__)
        order = []

        @app.before_request
        def before():
            order.append("before")

        @app.route("/")
        def index():
            order.append("view")
            return "ok"

        @app.after_request
        def after(response):
            order.append("after")
            return response

        app.test_client().get("/")
        assert order == ["before", "view", "after"]

    def test_teardown_runs(self):
        app = Cruet(__name__)
        teardown_called = [False]

        @app.route("/")
        def index():
            return "ok"

        @app.teardown_request
        def teardown(error):
            teardown_called[0] = True

        app.test_client().get("/")
        assert teardown_called[0] is True

    def test_teardown_runs_on_error(self):
        app = Cruet(__name__)
        teardown_called = [False]

        @app.route("/")
        def index():
            raise ValueError("boom")

        @app.teardown_request
        def teardown(error):
            teardown_called[0] = True

        app.test_client().get("/")
        assert teardown_called[0] is True

    def test_full_lifecycle_order(self):
        app = Cruet(__name__)
        order = []

        @app.before_request
        def before():
            order.append("before")

        @app.route("/")
        def index():
            order.append("view")
            return "ok"

        @app.after_request
        def after(response):
            order.append("after")
            return response

        @app.teardown_request
        def teardown(error):
            order.append("teardown")

        app.test_client().get("/")
        assert order == ["before", "view", "after", "teardown"]
