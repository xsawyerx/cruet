"""Tests for CResponse — WSGI response object."""
import io
import pytest
from cruet._cruet import CResponse
from tests.conftest import make_environ


class TestResponseCreation:
    def test_string_body(self):
        resp = CResponse("Hello, World!")
        assert resp.data == b"Hello, World!"

    def test_bytes_body(self):
        resp = CResponse(b"raw bytes")
        assert resp.data == b"raw bytes"

    def test_empty_body(self):
        resp = CResponse("")
        assert resp.data == b""

    def test_default_status(self):
        resp = CResponse("ok")
        assert resp.status_code == 200

    def test_default_content_type(self):
        resp = CResponse("hello")
        assert "text/html" in resp.content_type


class TestResponseStatusCodes:
    def test_status_200(self):
        resp = CResponse("ok", status=200)
        assert resp.status_code == 200

    def test_status_201(self):
        resp = CResponse("created", status=201)
        assert resp.status_code == 201

    def test_status_204(self):
        resp = CResponse("", status=204)
        assert resp.status_code == 204

    def test_status_301(self):
        resp = CResponse("", status=301)
        assert resp.status_code == 301

    def test_status_404(self):
        resp = CResponse("Not Found", status=404)
        assert resp.status_code == 404

    def test_status_500(self):
        resp = CResponse("Internal Server Error", status=500)
        assert resp.status_code == 500

    def test_status_string(self):
        """Status can also be provided as a string like '200 OK'."""
        resp = CResponse("ok", status="200 OK")
        assert resp.status_code == 200

    def test_status_property(self):
        resp = CResponse("ok", status=200)
        assert resp.status == "200 OK"


class TestResponseHeaders:
    def test_default_headers(self):
        resp = CResponse("hello")
        # Should at least have Content-Type
        assert resp.headers.get("Content-Type") is not None

    def test_custom_headers_dict(self):
        resp = CResponse("hello", headers={"X-Custom": "value"})
        assert resp.headers.get("X-Custom") == "value"

    def test_set_header(self):
        resp = CResponse("hello")
        resp.headers.set("X-Foo", "bar")
        assert resp.headers.get("X-Foo") == "bar"

    def test_content_type_header(self):
        resp = CResponse("hello", content_type="application/json")
        assert "application/json" in resp.content_type

    def test_content_type_setter(self):
        resp = CResponse("hello")
        resp.content_type = "application/json"
        assert "application/json" in resp.content_type


class TestResponseContentType:
    def test_text_html(self):
        resp = CResponse("hello", content_type="text/html")
        assert "text/html" in resp.content_type

    def test_application_json(self):
        resp = CResponse('{"key": "val"}', content_type="application/json")
        assert "application/json" in resp.content_type

    def test_text_plain(self):
        resp = CResponse("plain", content_type="text/plain")
        assert "text/plain" in resp.content_type


class TestResponseSetCookie:
    def test_set_cookie_basic(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc123")
        header_vals = resp.headers.getlist("Set-Cookie")
        assert any("session=abc123" in v for v in header_vals)

    def test_set_cookie_with_path(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc", path="/app")
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=abc" in v][0]
        assert "Path=/app" in cookie_line

    def test_set_cookie_with_domain(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc", domain="example.com")
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=abc" in v][0]
        assert "Domain=example.com" in cookie_line

    def test_set_cookie_httponly(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc", httponly=True)
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=abc" in v][0]
        assert "HttpOnly" in cookie_line

    def test_set_cookie_secure(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc", secure=True)
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=abc" in v][0]
        assert "Secure" in cookie_line

    def test_set_cookie_max_age(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc", max_age=3600)
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=abc" in v][0]
        assert "Max-Age=3600" in cookie_line

    def test_set_cookie_samesite(self):
        resp = CResponse("ok")
        resp.set_cookie("session", "abc", samesite="Lax")
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=abc" in v][0]
        assert "SameSite=Lax" in cookie_line

    def test_set_multiple_cookies(self):
        resp = CResponse("ok")
        resp.set_cookie("a", "1")
        resp.set_cookie("b", "2")
        header_vals = resp.headers.getlist("Set-Cookie")
        assert len(header_vals) == 2


class TestResponseDeleteCookie:
    def test_delete_cookie(self):
        resp = CResponse("ok")
        resp.delete_cookie("session")
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=" in v][0]
        # Deleting sets Max-Age=0 or Expires in the past
        assert "Max-Age=0" in cookie_line or "expires=" in cookie_line.lower()

    def test_delete_cookie_with_path(self):
        resp = CResponse("ok")
        resp.delete_cookie("session", path="/app")
        header_vals = resp.headers.getlist("Set-Cookie")
        cookie_line = [v for v in header_vals if "session=" in v][0]
        assert "Path=/app" in cookie_line


class TestResponseWSGICallable:
    """CResponse should be a valid WSGI application."""

    def _call_wsgi(self, resp, environ=None):
        """Call the response as a WSGI app, capturing output."""
        if environ is None:
            environ = make_environ()
        status_holder = {}
        headers_holder = {}

        def start_response(status, response_headers, exc_info=None):
            status_holder["status"] = status
            headers_holder["headers"] = response_headers

        body_parts = resp(environ, start_response)
        body = b"".join(body_parts)
        return status_holder["status"], headers_holder["headers"], body

    def test_wsgi_callable(self):
        resp = CResponse("Hello")
        status, headers, body = self._call_wsgi(resp)
        assert status == "200 OK"
        assert body == b"Hello"

    def test_wsgi_status_404(self):
        resp = CResponse("Not Found", status=404)
        status, headers, body = self._call_wsgi(resp)
        assert status.startswith("404")

    def test_wsgi_headers_present(self):
        resp = CResponse("ok", headers={"X-Custom": "test"})
        status, headers, body = self._call_wsgi(resp)
        header_dict = dict(headers)
        assert header_dict.get("X-Custom") == "test"

    def test_wsgi_content_type_in_headers(self):
        resp = CResponse("ok", content_type="text/plain")
        status, headers, body = self._call_wsgi(resp)
        header_dict = dict(headers)
        assert "text/plain" in header_dict.get("Content-Type", "")

    def test_wsgi_bytes_body(self):
        resp = CResponse(b"\x00\x01\x02")
        status, headers, body = self._call_wsgi(resp)
        assert body == b"\x00\x01\x02"

    def test_wsgi_empty_body(self):
        resp = CResponse("", status=204)
        status, headers, body = self._call_wsgi(resp)
        assert status.startswith("204")
        assert body == b""

    def test_wsgi_iterable_body(self):
        """Response body parts should all be bytes."""
        resp = CResponse("Hello")
        environ = make_environ()
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status

        parts = resp(environ, start_response)
        for part in parts:
            assert isinstance(part, bytes)


class TestResponseWSGIValidation:
    """Validate response with wsgiref.validate."""

    def test_wsgiref_validate(self):
        from wsgiref.validate import validator

        resp = CResponse("Hello, World!", content_type="text/plain")

        # Wrap the response WSGI app in wsgiref's validator
        validated_app = validator(resp)

        environ = make_environ()
        # wsgiref.validate requires these to be present
        environ.setdefault("SERVER_PROTOCOL", "HTTP/1.1")

        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers

        body_parts = validated_app(environ, start_response)
        body = b"".join(body_parts)
        body_parts.close()

        assert captured["status"] == "200 OK"
        assert body == b"Hello, World!"

    def test_wsgiref_validate_404(self):
        from wsgiref.validate import validator

        resp = CResponse("Not Found", status=404, content_type="text/plain")
        validated_app = validator(resp)

        environ = make_environ()
        environ.setdefault("SERVER_PROTOCOL", "HTTP/1.1")

        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status

        body_parts = validated_app(environ, start_response)
        body = b"".join(body_parts)
        body_parts.close()

        assert captured["status"].startswith("404")
        assert body == b"Not Found"
