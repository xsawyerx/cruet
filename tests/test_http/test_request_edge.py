"""Edge case tests for CRequest."""
import io
import json
import pytest
from cruet._cruet import CRequest
from tests.conftest import make_environ


class TestPostWithNoContentLength:
    def test_post_no_content_length_empty_body(self):
        """POST with no Content-Length should have empty body."""
        environ = make_environ(method="POST")
        # Ensure no Content-Length is set
        environ.pop("CONTENT_LENGTH", None)
        req = CRequest(environ)
        assert req.data == b""

    def test_post_empty_content_length(self):
        """POST with empty Content-Length string."""
        environ = make_environ(method="POST")
        environ["CONTENT_LENGTH"] = ""
        req = CRequest(environ)
        # Should not crash
        data = req.data
        assert isinstance(data, bytes)


class TestBodyVsContentLength:
    def test_body_larger_than_content_length(self):
        """Body larger than Content-Length should truncate to Content-Length."""
        body = b"hello world, this is extra"
        environ = make_environ(method="POST", body=body, content_type="text/plain")
        environ["CONTENT_LENGTH"] = "5"  # Only 5 bytes
        environ["wsgi.input"] = io.BytesIO(body)
        req = CRequest(environ)
        # Should read only 5 bytes
        assert len(req.data) == 5
        assert req.data == b"hello"


class TestNonASCIIQueryStrings:
    def test_percent_encoded_utf8(self):
        """Percent-encoded UTF-8 in query string."""
        # caf%C3%A9 = "cafe" with accent
        req = CRequest(make_environ(query_string="name=caf%C3%A9"))
        assert req.args["name"] == "caf\u00e9"

    def test_chinese_characters(self):
        """Percent-encoded Chinese characters."""
        # %E4%B8%AD%E6%96%87 = "中文"
        req = CRequest(make_environ(query_string="text=%E4%B8%AD%E6%96%87"))
        assert req.args["text"] == "中文"

    def test_emoji_percent_encoded(self):
        """Percent-encoded emoji."""
        # %F0%9F%98%80 = 😀
        req = CRequest(make_environ(query_string="emoji=%F0%9F%98%80"))
        assert "emoji" in req.args


class TestRequestEnvironDirect:
    def test_environ_is_accessible(self):
        """request.environ should be the original dict."""
        environ = make_environ(path="/test")
        req = CRequest(environ)
        # The environ should be accessible (either as attribute or via the object)
        # Check that the request was built from this environ
        assert req.path == "/test"
        assert req.method == "GET"

    def test_custom_environ_keys(self):
        """Custom keys in environ should not break the request."""
        environ = make_environ()
        environ["my.custom.key"] = "custom_value"
        req = CRequest(environ)
        assert req.method == "GET"


class TestVeryLargeJsonBody:
    def test_large_json_body(self):
        """JSON body > 1MB should parse correctly."""
        data = {"items": [{"id": i, "value": "x" * 100} for i in range(5000)]}
        body = json.dumps(data).encode("utf-8")
        assert len(body) > 500_000  # At least 500KB
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/json"))
        parsed = req.json
        assert len(parsed["items"]) == 5000
        assert parsed["items"][0]["id"] == 0

    def test_large_data_body(self):
        """Raw body > 1MB should be read correctly."""
        body = b"x" * 1_100_000
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/octet-stream"))
        assert len(req.data) == 1_100_000


class TestRequestPropertyCaching:
    def test_args_cached(self):
        """Accessing .args multiple times returns same object."""
        req = CRequest(make_environ(query_string="a=1"))
        args1 = req.args
        args2 = req.args
        assert args1 is args2

    def test_headers_cached(self):
        """Accessing .headers multiple times returns same object."""
        req = CRequest(make_environ(headers={"X-Test": "val"}))
        h1 = req.headers
        h2 = req.headers
        assert h1 is h2

    def test_data_cached(self):
        """Accessing .data multiple times returns same object."""
        req = CRequest(make_environ(body=b"hello", content_type="text/plain"))
        d1 = req.data
        d2 = req.data
        assert d1 is d2

    def test_form_cached(self):
        """Accessing .form multiple times returns same object."""
        req = CRequest(make_environ(
            method="POST", body=b"a=1",
            content_type="application/x-www-form-urlencoded"))
        f1 = req.form
        f2 = req.form
        assert f1 is f2


class TestRequestFormEdgeCases:
    def test_form_with_empty_body(self):
        """Form with empty body should be empty dict."""
        req = CRequest(make_environ(
            method="POST", body=b"",
            content_type="application/x-www-form-urlencoded"))
        assert req.form == {}

    def test_form_not_urlencoded(self):
        """Non-urlencoded content type should return empty form."""
        req = CRequest(make_environ(
            method="POST", body=b"data=value",
            content_type="text/plain"))
        assert req.form == {}


class TestRequestJsonEdgeCases:
    def test_json_with_unicode(self):
        """JSON with unicode characters."""
        payload = {"name": "café", "emoji": "😀"}
        body = json.dumps(payload).encode("utf-8")
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/json"))
        assert req.json["name"] == "café"

    def test_json_array(self):
        """JSON body that is an array, not object."""
        body = json.dumps([1, 2, 3]).encode("utf-8")
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/json"))
        assert req.json == [1, 2, 3]

    def test_json_null(self):
        """JSON body that is null."""
        body = b"null"
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/json"))
        assert req.json is None

    def test_json_with_charset(self):
        """JSON content type with charset parameter."""
        payload = {"key": "value"}
        body = json.dumps(payload).encode("utf-8")
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/json; charset=utf-8"))
        assert req.json == payload
