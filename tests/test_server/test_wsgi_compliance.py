"""Tests for WSGI server compliance and environ construction."""
import pytest
from cruet._cruet import parse_http_request
from cruet.serving import build_environ


class TestBuildEnviron:
    def _parse_and_build(self, raw, client=("127.0.0.1", 9999),
                         server=("127.0.0.1", 8000)):
        parsed = parse_http_request(raw)
        assert parsed is not None
        return build_environ(parsed, client, server)

    def test_required_wsgi_keys(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        env = self._parse_and_build(raw)
        # PEP 3333 required keys
        assert env["REQUEST_METHOD"] == "GET"
        assert "PATH_INFO" in env
        assert "QUERY_STRING" in env
        assert "SERVER_NAME" in env
        assert "SERVER_PORT" in env
        assert "SERVER_PROTOCOL" in env
        assert "wsgi.version" in env
        assert "wsgi.url_scheme" in env
        assert "wsgi.input" in env
        assert "wsgi.errors" in env
        assert "wsgi.multithread" in env
        assert "wsgi.multiprocess" in env
        assert "wsgi.run_once" in env

    def test_method_and_path(self):
        raw = b"GET /hello/world HTTP/1.1\r\nHost: localhost\r\n\r\n"
        env = self._parse_and_build(raw)
        assert env["REQUEST_METHOD"] == "GET"
        assert env["PATH_INFO"] == "/hello/world"

    def test_query_string(self):
        raw = b"GET /search?q=test&page=2 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        env = self._parse_and_build(raw)
        assert env["QUERY_STRING"] == "q=test&page=2"

    def test_content_type(self):
        raw = (
            b"POST /api HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 2\r\n"
            b"\r\n{}"
        )
        env = self._parse_and_build(raw)
        assert env["CONTENT_TYPE"] == "application/json"

    def test_content_length(self):
        body = b"hello"
        raw = (
            b"POST /data HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n" + body
        )
        env = self._parse_and_build(raw)
        assert env["CONTENT_LENGTH"] == "5"

    def test_http_host(self):
        raw = b"GET / HTTP/1.1\r\nHost: example.com:8080\r\n\r\n"
        env = self._parse_and_build(raw)
        assert env["HTTP_HOST"] == "example.com:8080"

    def test_custom_headers(self):
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Request-Id: abc123\r\n"
            b"Accept-Language: en-US\r\n"
            b"\r\n"
        )
        env = self._parse_and_build(raw)
        assert env["HTTP_X_REQUEST_ID"] == "abc123"
        assert env["HTTP_ACCEPT_LANGUAGE"] == "en-US"

    def test_server_info(self):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        env = self._parse_and_build(raw, server=("0.0.0.0", 9000))
        assert env["SERVER_NAME"] == "0.0.0.0"
        assert env["SERVER_PORT"] == "9000"

    def test_wsgi_input_readable(self):
        body = b"some body data"
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 14\r\n"
            b"\r\n" + body
        )
        env = self._parse_and_build(raw)
        assert env["wsgi.input"].read() == body

    def test_post_with_body(self):
        body = b'{"key": "value"}'
        raw = (
            b"POST /api HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n" + body
        )
        env = self._parse_and_build(raw)
        assert env["REQUEST_METHOD"] == "POST"
        data = env["wsgi.input"].read()
        assert data == body

    def test_head_request(self):
        raw = b"HEAD / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        env = self._parse_and_build(raw)
        assert env["REQUEST_METHOD"] == "HEAD"
