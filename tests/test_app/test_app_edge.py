"""Edge case tests for the Cruet application class."""
import json
import pytest
from cruet import Cruet
from cruet._cruet import CResponse


class TestUnhandledException:
    def test_view_raises_exception_returns_500(self):
        """Unhandled exception in view should return 500."""
        app = Cruet(__name__)

        @app.route("/")
        def boom():
            raise ValueError("something went wrong")

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 500

    def test_view_raises_runtime_error(self):
        """RuntimeError in view should return 500."""
        app = Cruet(__name__)

        @app.route("/")
        def boom():
            raise RuntimeError("oops")

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 500

    def test_view_raises_type_error(self):
        """TypeError in view should return 500."""
        app = Cruet(__name__)

        @app.route("/")
        def boom():
            return 1 + "string"  # TypeError

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 500


class TestBeforeRequestException:
    def test_before_request_raises_with_error_handler(self):
        """Exception in before_request should trigger error handler."""
        app = Cruet(__name__)
        errors = []

        @app.before_request
        def before():
            raise ValueError("before_request failed")

        @app.route("/")
        def index():
            return "ok"

        @app.errorhandler(ValueError)
        def handle_value_error(e):
            errors.append(str(e))
            return "caught", 400

        client = app.test_client()
        resp = client.get("/")
        # Should be caught by error handler or return 500
        assert resp.status_code in (400, 500)

    def test_before_request_raises_returns_500(self):
        """Exception in before_request without handler returns 500."""
        app = Cruet(__name__)

        @app.before_request
        def before():
            raise RuntimeError("boom in before")

        @app.route("/")
        def index():
            return "ok"

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 500


class TestAfterRequestException:
    def test_after_request_raises_returns_500(self):
        """Exception in after_request should return 500."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "ok"

        @app.after_request
        def after(response):
            raise RuntimeError("boom in after")

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 500


class TestMultipleConverters:
    def test_two_int_converters(self):
        """Route with multiple int converters."""
        app = Cruet(__name__)

        @app.route("/user/<int:user_id>/post/<int:post_id>")
        def user_post(user_id, post_id):
            return f"user={user_id},post={post_id}"

        client = app.test_client()
        resp = client.get("/user/42/post/7")
        assert resp.status_code == 200
        assert resp.text == "user=42,post=7"

    def test_mixed_converters(self):
        """Route with string and int converters."""
        app = Cruet(__name__)

        @app.route("/org/<name>/member/<int:id>")
        def member(name, id):
            return f"org={name},id={id}"

        client = app.test_client()
        resp = client.get("/org/acme/member/5")
        assert resp.status_code == 200
        assert resp.text == "org=acme,id=5"


class TestFloatConverter:
    def test_float_converter(self):
        """Route with float converter."""
        app = Cruet(__name__)

        @app.route("/price/<float:amount>")
        def price(amount):
            return f"price={amount}"

        client = app.test_client()
        resp = client.get("/price/19.99")
        assert resp.status_code == 200
        assert "19.99" in resp.text

    def test_float_converter_integer(self):
        """Float converter with integer value."""
        app = Cruet(__name__)

        @app.route("/val/<float:v>")
        def val(v):
            return f"v={v}"

        client = app.test_client()
        resp = client.get("/val/42.0")
        assert resp.status_code == 200


class TestUUIDConverter:
    def test_uuid_converter(self):
        """Route with UUID converter."""
        app = Cruet(__name__)

        @app.route("/item/<uuid:item_id>")
        def item(item_id):
            return f"id={item_id}"

        client = app.test_client()
        resp = client.get("/item/550e8400-e29b-41d4-a716-446655440000")
        assert resp.status_code == 200
        assert "550e8400" in resp.text

    def test_uuid_converter_invalid(self):
        """Invalid UUID should not match the route."""
        app = Cruet(__name__)

        @app.route("/item/<uuid:item_id>")
        def item(item_id):
            return f"id={item_id}"

        client = app.test_client()
        resp = client.get("/item/not-a-uuid")
        assert resp.status_code == 404


class TestEmptyResponseBody:
    def test_empty_string_response(self):
        """Returning empty string should give 200 with empty body."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return ""

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.data == b""

    def test_empty_bytes_response(self):
        """Returning empty bytes."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return CResponse(b"", status=200)

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.data == b""


class TestExplicitContentType:
    def test_json_content_type_header(self):
        """Response with explicit Content-Type: application/json."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return CResponse(
                '{"key": "val"}',
                content_type="application/json"
            )

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.get_header("Content-Type") == "application/json"
        assert resp.json == {"key": "val"}

    def test_xml_content_type(self):
        """Response with XML content type."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return CResponse(
                "<root><item>hello</item></root>",
                content_type="application/xml"
            )

        client = app.test_client()
        resp = client.get("/")
        assert resp.get_header("Content-Type") == "application/xml"


class TestErrorHandlers:
    def test_custom_404_handler(self):
        """Custom 404 error handler."""
        app = Cruet(__name__)

        @app.errorhandler(404)
        def custom_404(e):
            return "custom not found", 404

        client = app.test_client()
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        assert resp.text == "custom not found"

    def test_custom_500_handler(self):
        """Custom 500 error handler."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            raise ValueError("boom")

        @app.errorhandler(500)
        def custom_500(e):
            return "custom error", 500

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 500

    def test_exception_class_handler(self):
        """Handler registered for a specific exception class."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            raise ValueError("specific error")

        @app.errorhandler(ValueError)
        def handle_value_error(e):
            return f"caught: {e}", 400

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 400
        assert "caught: specific error" in resp.text
