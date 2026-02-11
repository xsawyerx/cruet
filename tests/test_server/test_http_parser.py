"""Tests for the custom HTTP/1.1 request parser."""
import pytest
from cruet._cruet import parse_http_request


class TestParseBasicRequests:
    def test_simple_get(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["method"] == "GET"
        assert result["path"] == "/"
        assert result["version"] == "HTTP/1.1"
        assert result["headers"]["Host"] == "localhost"

    def test_get_with_path(self):
        raw = b"GET /hello/world HTTP/1.1\r\nHost: example.com\r\n\r\n"
        result = parse_http_request(raw)
        assert result["method"] == "GET"
        assert result["path"] == "/hello/world"

    def test_get_with_query_string(self):
        raw = b"GET /search?q=hello&page=1 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["path"] == "/search"
        assert result["query_string"] == "q=hello&page=1"

    def test_post_request(self):
        body = b"name=John&age=30"
        raw = (
            b"POST /submit HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"\r\n" + body
        )
        result = parse_http_request(raw)
        assert result["method"] == "POST"
        assert result["path"] == "/submit"
        assert result["body"] == body


class TestParseHeaders:
    def test_single_header(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["headers"]["Host"] == "localhost"

    def test_multiple_headers(self):
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: text/html\r\n"
            b"User-Agent: test/1.0\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result["headers"]["Host"] == "localhost"
        assert result["headers"]["Accept"] == "text/html"
        assert result["headers"]["User-Agent"] == "test/1.0"

    def test_header_with_spaces_in_value(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Custom: hello world\r\n\r\n"
        result = parse_http_request(raw)
        assert result["headers"]["X-Custom"] == "hello world"

    def test_content_length_body(self):
        body = b'{"key": "value"}'
        raw = (
            b"POST /api HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n" + body
        )
        result = parse_http_request(raw)
        assert result["body"] == body


class TestParseKeepAlive:
    def test_http11_keep_alive_default(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result.get("keep_alive", True) is True

    def test_connection_close(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        result = parse_http_request(raw)
        assert result["keep_alive"] is False


class TestParseMalformed:
    def test_incomplete_request_line(self):
        raw = b"GET / HTTP"
        result = parse_http_request(raw)
        assert result is None or result.get("error")

    def test_no_headers(self):
        raw = b"GET / HTTP/1.1\r\n\r\n"
        result = parse_http_request(raw)
        # Should still parse - Host is not strictly required for parsing
        assert result["method"] == "GET"

    def test_empty_input(self):
        result = parse_http_request(b"")
        assert result is None or result.get("error")


class TestParsePartialReads:
    def test_body_length_match(self):
        body = b"hello"
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n" + body
        )
        result = parse_http_request(raw)
        assert result["body"] == b"hello"
        assert len(result["body"]) == 5


class TestParseHTTPMethods:
    def test_put(self):
        raw = b"PUT /resource HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["method"] == "PUT"

    def test_delete(self):
        raw = b"DELETE /resource/42 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["method"] == "DELETE"

    def test_head(self):
        raw = b"HEAD / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["method"] == "HEAD"

    def test_options(self):
        raw = b"OPTIONS * HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result["method"] == "OPTIONS"

    def test_patch(self):
        raw = b"PATCH /resource HTTP/1.1\r\nHost: localhost\r\nContent-Length: 3\r\n\r\nabc"
        result = parse_http_request(raw)
        assert result["method"] == "PATCH"
        assert result["body"] == b"abc"
