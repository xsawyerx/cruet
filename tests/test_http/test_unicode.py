"""Tests for Unicode/encoding safety in C parsers.

Verifies that non-UTF-8 and high-byte input never causes UnicodeDecodeError.
"""
import pytest
from cruet._cruet import parse_http_request, parse_qs, parse_cookies, parse_multipart


# ---------------------------------------------------------------------------
# HTTP parser
# ---------------------------------------------------------------------------

class TestHttpParserUnicode:
    def test_path_with_high_bytes(self):
        """Path containing raw 0x80-0xFF bytes should parse as Latin-1."""
        raw = b"GET /caf\xe9 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["path"] == "/caf\u00e9"

    def test_header_value_latin1(self):
        """Header value with Latin-1 chars should be preserved."""
        raw = b"GET / HTTP/1.1\r\nX-Custom: \xe9\xe8\xf1\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["headers"]["X-Custom"] == "\u00e9\u00e8\u00f1"

    def test_all_bytes_in_header_value(self):
        """Header value containing every byte 0x01-0xFF should not crash."""
        # Skip 0x00 (null), \r (0x0d), \n (0x0a) which terminate header lines
        header_val = bytes(b for b in range(1, 256) if b not in (0x0a, 0x0d))
        raw = b"GET / HTTP/1.1\r\nX-Bytes: " + header_val + b"\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert "X-Bytes" in result["headers"]

    def test_query_string_high_bytes(self):
        """Query string with raw high bytes should parse as Latin-1."""
        raw = b"GET /search?\xff=\xfe HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["query_string"] == "\u00ff=\u00fe"

    def test_method_and_version_high_bytes(self):
        """Exotic method/version bytes should not crash (Latin-1)."""
        raw = b"G\x80T /path HTTP/1.\x81\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert "\u0080" in result["method"]

    def test_header_name_high_bytes(self):
        """Header name with high byte should not crash."""
        raw = b"GET / HTTP/1.1\r\nX-H\xe9ader: value\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert "X-H\u00e9ader" in result["headers"]


# ---------------------------------------------------------------------------
# Query string parser
# ---------------------------------------------------------------------------

class TestQueryStringUnicode:
    def test_percent_encoded_utf8(self):
        """Percent-encoded UTF-8 (cafe with e-acute) should decode correctly."""
        result = parse_qs("name=caf%C3%A9")
        assert result["name"] == ["caf\u00e9"]

    def test_percent_encoded_invalid_utf8(self):
        """Single %80 is not valid UTF-8; should produce surrogate, not crash."""
        result = parse_qs("key=%80")
        vals = result["key"]
        assert len(vals) == 1
        # \x80 is not valid UTF-8 on its own -> surrogateescape produces \udcc0\udc80
        # or just check it doesn't crash and is a string
        assert isinstance(vals[0], str)

    def test_percent_encoded_latin1(self):
        """Single %E9 is Latin-1 e-acute but invalid as standalone UTF-8."""
        result = parse_qs("key=%E9")
        vals = result["key"]
        assert len(vals) == 1
        assert isinstance(vals[0], str)

    def test_mixed_valid_and_invalid_utf8(self):
        """Mix of valid UTF-8 and raw invalid bytes should not crash."""
        # valid UTF-8 (%C3%A9) followed by invalid standalone (%80)
        result = parse_qs("k=caf%C3%A9%80")
        assert isinstance(result["k"][0], str)

    def test_all_single_byte_percent_encoded(self):
        """Every possible percent-encoded single byte should not crash."""
        for byte_val in range(256):
            qs = "k=%{:02X}".format(byte_val)
            result = parse_qs(qs)
            assert isinstance(result["k"][0], str)


# ---------------------------------------------------------------------------
# Cookie parser
# ---------------------------------------------------------------------------

class TestCookieUnicode:
    def test_cookie_value_ascii(self):
        """Cookie with pure ASCII should parse normally."""
        result = parse_cookies("session=abc123")
        assert result["session"] == "abc123"

    def test_cookie_value_with_unicode_str(self):
        """Cookie value containing non-ASCII str chars should not crash.

        parse_cookies takes a Python str (s# format), so C receives UTF-8
        bytes.  Latin-1 decode of those UTF-8 bytes produces a different
        (but deterministic) string.  The key property: no crash.
        """
        cookie_str = "session=caf\u00e9"
        result = parse_cookies(cookie_str)
        assert "session" in result
        assert isinstance(result["session"], str)

    def test_cookie_all_printable_high_bytes(self):
        """Cookie with high Unicode chars should not crash."""
        val = "".join(chr(b) for b in range(0x80, 0x100))
        cookie_str = "data=" + val
        result = parse_cookies(cookie_str)
        assert "data" in result
        assert isinstance(result["data"], str)

    def test_cookie_name_with_unicode(self):
        """Cookie name with non-ASCII chars should not crash."""
        cookie_str = "n\u00e9me=value"
        result = parse_cookies(cookie_str)
        assert isinstance(result, dict)
        assert len(result) == 1
        # The value should be preserved correctly since it's ASCII
        assert list(result.values())[0] == "value"


# ---------------------------------------------------------------------------
# Multipart parser
# ---------------------------------------------------------------------------

def _make_multipart_bytes(fields=None, files=None, boundary=b"----TestBoundary"):
    """Build multipart body using raw bytes for full control."""
    parts = []
    if fields:
        for name, value in fields:
            parts.append(
                b"--" + boundary + b"\r\n"
                b"Content-Disposition: form-data; name=\"" + name + b"\"\r\n"
                b"\r\n"
                + value + b"\r\n"
            )
    if files:
        for name, filename, content_type, data in files:
            parts.append(
                b"--" + boundary + b"\r\n"
                b"Content-Disposition: form-data; name=\"" + name
                + b"\"; filename=\"" + filename + b"\"\r\n"
                b"Content-Type: " + content_type + b"\r\n"
                b"\r\n"
                + data + b"\r\n"
            )
    parts.append(b"--" + boundary + b"--\r\n")
    return b"".join(parts), boundary.decode("ascii")


class TestMultipartUnicode:
    def test_utf8_form_field_value(self):
        """UTF-8 encoded form field value should decode correctly."""
        body, boundary = _make_multipart_bytes(
            fields=[(b"greeting", "caf\u00e9".encode("utf-8"))]
        )
        result = parse_multipart(body, boundary)
        assert result["fields"]["greeting"] == "caf\u00e9"

    def test_non_utf8_form_field_value(self):
        """Non-UTF-8 bytes in form field value should use surrogateescape, not crash."""
        body, boundary = _make_multipart_bytes(
            fields=[(b"data", b"\x80\x81\xff")]
        )
        result = parse_multipart(body, boundary)
        val = result["fields"]["data"]
        assert isinstance(val, str)
        # Surrogates should round-trip back to original bytes
        assert val.encode("utf-8", "surrogateescape") == b"\x80\x81\xff"

    def test_filename_with_high_bytes(self):
        """Filename with high bytes in Content-Disposition should not crash."""
        body, boundary = _make_multipart_bytes(
            files=[(b"file", b"caf\xe9.txt", b"text/plain", b"hello")]
        )
        result = parse_multipart(body, boundary)
        f = result["files"]["file"]
        assert f["filename"] == "caf\u00e9.txt"  # Latin-1 decode of \xe9

    def test_filename_all_high_bytes(self):
        """Filename composed entirely of high bytes should not crash."""
        fn = bytes(range(0x80, 0x90))  # 16 high bytes
        body, boundary = _make_multipart_bytes(
            files=[(b"file", fn, b"application/octet-stream", b"data")]
        )
        result = parse_multipart(body, boundary)
        f = result["files"]["file"]
        assert isinstance(f["filename"], str)
        assert len(f["filename"]) == 16

    def test_field_name_high_bytes(self):
        """Field name with high bytes should not crash (Latin-1 from header)."""
        body, boundary = _make_multipart_bytes(
            fields=[(b"caf\xe9", b"value")]
        )
        result = parse_multipart(body, boundary)
        assert "caf\u00e9" in result["fields"]


# ---------------------------------------------------------------------------
# End-to-end via test client
# ---------------------------------------------------------------------------

class TestEndToEndUnicode:
    def test_post_json_unicode(self):
        """POST JSON with Unicode should round-trip correctly."""
        from cruet import Cruet, request

        app = Cruet(__name__)

        @app.post("/api")
        def api():
            data = request.get_json(force=True)
            return data.get("msg", "")

        resp = app.test_client().post(
            "/api",
            data='{"msg": "caf\u00e9"}'.encode("utf-8"),
            content_type="application/json",
        )
        assert resp.text == "caf\u00e9"

    def test_get_percent_encoded_query(self):
        """GET with percent-encoded UTF-8 in query string should work."""
        from cruet import Cruet, request

        app = Cruet(__name__)

        @app.route("/search")
        def search():
            return request.args.get("q", "")

        resp = app.test_client().get("/search", query_string="q=caf%C3%A9")
        assert resp.text == "caf\u00e9"
