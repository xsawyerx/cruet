"""Edge case tests for CResponse."""
import pytest
from cruet._cruet import CResponse
from tests.conftest import make_environ


def _call_wsgi(resp, environ=None):
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


class TestContentLengthMatchesBody:
    def test_content_length_auto_set(self):
        """Content-Length should automatically match body length."""
        resp = CResponse("Hello, World!")
        status, headers, body = _call_wsgi(resp)
        header_dict = dict(headers)
        assert "Content-Length" in header_dict
        assert int(header_dict["Content-Length"]) == len(body)

    def test_content_length_bytes_body(self):
        """Content-Length for bytes body."""
        resp = CResponse(b"\x00\x01\x02\x03\x04")
        status, headers, body = _call_wsgi(resp)
        header_dict = dict(headers)
        assert int(header_dict["Content-Length"]) == 5

    def test_content_length_empty_body(self):
        """Content-Length for empty body."""
        resp = CResponse("")
        status, headers, body = _call_wsgi(resp)
        header_dict = dict(headers)
        cl = header_dict.get("Content-Length")
        if cl is not None:
            assert int(cl) == 0


class TestHeadRequestResponse:
    def test_head_request_environ(self):
        """HEAD request should still get headers in response."""
        resp = CResponse("Hello, World!")
        environ = make_environ(method="HEAD")
        status, headers, body = _call_wsgi(resp, environ)
        assert status == "200 OK"
        header_dict = dict(headers)
        # Headers should be present
        assert "Content-Type" in header_dict


class TestNoContentResponse:
    def test_204_no_content(self):
        """204 No Content should have no body."""
        resp = CResponse("", status=204)
        status, headers, body = _call_wsgi(resp)
        assert status.startswith("204")
        assert body == b""

    def test_304_not_modified(self):
        """304 Not Modified should work."""
        resp = CResponse("", status=304)
        status, headers, body = _call_wsgi(resp)
        assert status.startswith("304")


class TestEmptySetCookie:
    def test_set_cookie_empty_value(self):
        """Setting a cookie with empty value."""
        resp = CResponse("ok")
        resp.set_cookie("session", "")
        header_vals = resp.headers.getlist("Set-Cookie")
        assert any("session=" in v for v in header_vals)

    def test_delete_cookie_sets_empty(self):
        """Deleting a cookie sets it to empty with Max-Age=0."""
        resp = CResponse("ok")
        resp.delete_cookie("session")
        header_vals = resp.headers.getlist("Set-Cookie")
        assert len(header_vals) >= 1


class TestManyHeaders:
    def test_100_custom_headers(self):
        """Response with 100+ custom headers."""
        resp = CResponse("ok")
        for i in range(100):
            resp.headers.add(f"X-Header-{i}", f"value-{i}")
        status, headers, body = _call_wsgi(resp)
        assert status == "200 OK"
        # Verify some headers came through
        header_dict = {}
        for k, v in headers:
            header_dict[k] = v
        assert header_dict.get("X-Header-0") == "value-0"
        assert header_dict.get("X-Header-99") == "value-99"


class TestLargeResponseBody:
    def test_large_string_body(self):
        """Response body > 1MB string."""
        big_body = "x" * 1_100_000
        resp = CResponse(big_body)
        assert resp.data == big_body.encode()
        assert len(resp.data) == 1_100_000

    def test_large_bytes_body(self):
        """Response body > 1MB bytes."""
        big_body = b"\x00" * 1_100_000
        resp = CResponse(big_body)
        assert len(resp.data) == 1_100_000


class TestStatusEdgeCases:
    def test_status_100(self):
        """Status 100 Continue."""
        resp = CResponse("", status=100)
        assert resp.status_code == 100

    def test_status_418(self):
        """Status 418 I'm a Teapot."""
        resp = CResponse("short and stout", status=418)
        assert resp.status_code == 418

    def test_status_599(self):
        """Unusual status code 599."""
        resp = CResponse("error", status=599)
        assert resp.status_code == 599


class TestResponseDataProperty:
    def test_data_is_bytes(self):
        """Response.data should always be bytes."""
        resp = CResponse("hello")
        assert isinstance(resp.data, bytes)

    def test_data_from_string(self):
        """String body should be encoded to bytes."""
        resp = CResponse("hello")
        assert resp.data == b"hello"

    def test_data_from_bytes(self):
        """Bytes body should be preserved."""
        resp = CResponse(b"hello")
        assert resp.data == b"hello"


class TestResponseContentType:
    def test_explicit_json_content_type(self):
        """Setting explicit application/json content type."""
        resp = CResponse('{"key": "val"}', content_type="application/json")
        assert "application/json" in resp.content_type

    def test_content_type_override(self):
        """Content type can be overridden after creation."""
        resp = CResponse("hello")
        resp.content_type = "application/xml"
        assert "application/xml" in resp.content_type

    def test_content_type_in_wsgi_output(self):
        """Content-Type should appear in WSGI response headers."""
        resp = CResponse("hello", content_type="text/plain")
        status, headers, body = _call_wsgi(resp)
        header_dict = dict(headers)
        assert "text/plain" in header_dict.get("Content-Type", "")
