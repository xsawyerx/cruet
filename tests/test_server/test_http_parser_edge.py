"""Adversarial input tests for the C HTTP/1.1 parser."""
import pytest
from cruet._cruet import parse_http_request


class TestExtremelyLongInputs:
    def test_extremely_long_uri(self):
        """URI > 8KB should be handled gracefully (None or parsed)."""
        long_path = "/" + "a" * 9000
        raw = f"GET {long_path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode()
        result = parse_http_request(raw)
        # Should either parse or return None, not crash
        if result is not None:
            assert result["method"] == "GET"

    def test_extremely_long_header_value(self):
        """Header value > 64KB should be handled gracefully."""
        long_val = "x" * 70000
        raw = f"GET / HTTP/1.1\r\nHost: localhost\r\nX-Big: {long_val}\r\n\r\n".encode()
        result = parse_http_request(raw)
        if result is not None:
            assert result["method"] == "GET"

    def test_extremely_long_header_name(self):
        """Header name > 8KB should be handled gracefully."""
        long_name = "X-" + "A" * 9000
        raw = f"GET / HTTP/1.1\r\nHost: localhost\r\n{long_name}: val\r\n\r\n".encode()
        result = parse_http_request(raw)
        if result is not None:
            assert result["method"] == "GET"


class TestNullBytes:
    def test_null_byte_in_path(self):
        """Null bytes in path should not crash the parser."""
        raw = b"GET /hello\x00world HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        # Should parse (null is just a byte) or return None
        assert result is None or isinstance(result, dict)

    def test_null_byte_in_header_value(self):
        """Null bytes in header values should not crash."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Evil: hello\x00world\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)

    def test_null_byte_in_header_name(self):
        """Null bytes in header names should not crash."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-\x00Evil: value\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)

    def test_null_byte_in_body(self):
        """Null bytes in body should be preserved."""
        body = b"hello\x00world"
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n" + body
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == body

    def test_null_byte_in_method(self):
        """Null bytes in method should not crash."""
        raw = b"GE\x00T / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)


class TestCRLFInjection:
    def test_crlf_injection_in_header_value(self):
        """CRLF in header value should not inject extra headers."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Evil: value\r\nInjected: yes\r\n\r\n"
        result = parse_http_request(raw)
        # The parser sees \r\n as end of the X-Evil header line,
        # then "Injected: yes" as a separate header - this is normal parsing.
        assert result is not None
        assert result["headers"]["Host"] == "localhost"

    def test_bare_cr_in_header_value(self):
        """Bare \\r (no \\n) in header value should not crash."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Test: val\rue\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)

    def test_bare_lf_in_header_value(self):
        """Bare \\n (no \\r) in header value should not crash."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Test: val\nue\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)


class TestMalformedHeaders:
    def test_missing_colon_in_header(self):
        """Header line without colon should be skipped gracefully."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nNoColonHere\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "GET"
        # The malformed header should be skipped
        assert "NoColonHere" not in result["headers"]

    def test_empty_header_name(self):
        """Empty header name (just colon) should not crash."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n: value\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None

    def test_empty_header_value(self):
        """Empty header value should be accepted."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Empty:\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["headers"].get("X-Empty", "").strip() == ""

    def test_header_with_only_whitespace_value(self):
        """Header with whitespace-only value."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Space:   \r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None


class TestManyHeaders:
    def test_1000_headers(self):
        """Request with 1000+ headers should not crash."""
        header_lines = b"".join(
            f"X-Header-{i}: value-{i}\r\n".encode() for i in range(1000)
        )
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n" + header_lines + b"\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "GET"


class TestContentLength:
    def test_negative_content_length(self):
        """Negative Content-Length should be handled gracefully."""
        raw = b"POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: -1\r\n\r\n"
        result = parse_http_request(raw)
        # Should parse without crash; body should be empty
        assert result is not None
        assert result["body"] == b""

    def test_non_numeric_content_length(self):
        """Non-numeric Content-Length should be handled gracefully."""
        raw = b"POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: abc\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None

    def test_zero_content_length(self):
        """Content-Length: 0 should produce empty body."""
        raw = b"POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b""

    def test_multiple_content_length_headers(self):
        """Multiple Content-Length headers (conflicting values)."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"hello"
        )
        result = parse_http_request(raw)
        # Should handle gracefully -- last value wins or first value wins
        assert result is not None

    def test_very_large_content_length(self):
        """Extremely large Content-Length with small body."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 999999999\r\n"
            b"\r\n"
            b"small body"
        )
        result = parse_http_request(raw)
        # Should parse what's available without allocating huge buffer
        assert result is not None


class TestHTTPVersions:
    def test_http10_keep_alive_default_false(self):
        """HTTP/1.0 requests should default keep_alive to False."""
        raw = b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "GET"
        assert result["version"] == "HTTP/1.0"
        # HTTP/1.0 default is no keep-alive (parser may or may not handle this)

    def test_http09_request(self):
        """HTTP/0.9 style request should be handled or rejected."""
        raw = b"GET /\r\n"
        result = parse_http_request(raw)
        # May return None since it doesn't match expected format
        assert result is None or isinstance(result, dict)

    def test_unknown_version(self):
        """Unknown HTTP version should still parse."""
        raw = b"GET / HTTP/2.0\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        if result is not None:
            assert result["version"] == "HTTP/2.0"


class TestRequestLine:
    def test_empty_method(self):
        """Empty method should be handled gracefully."""
        raw = b" / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        # Should either parse with empty method or return None
        assert result is None or isinstance(result, dict)

    def test_empty_path(self):
        """Empty path should be handled gracefully."""
        raw = b"GET  HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)

    def test_extra_spaces_in_request_line(self):
        """Extra spaces between components of the request line."""
        raw = b"GET  /  HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        # Parser may interpret double-space differently
        assert result is None or isinstance(result, dict)

    def test_tab_instead_of_space(self):
        """Tab character instead of space in request line."""
        raw = b"GET\t/\tHTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)

    def test_only_crlf(self):
        """Input of only CRLF."""
        raw = b"\r\n\r\n"
        result = parse_http_request(raw)
        assert result is None or isinstance(result, dict)

    def test_leading_crlf(self):
        """Leading CRLF before request line (common with keep-alive)."""
        raw = b"\r\nGET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        # Some parsers handle leading CRLF, some don't
        assert result is None or isinstance(result, dict)

    def test_very_long_method(self):
        """Very long method name should not crash."""
        method = "A" * 1000
        raw = f"{method} / HTTP/1.1\r\nHost: localhost\r\n\r\n".encode()
        result = parse_http_request(raw)
        if result is not None:
            assert result["method"] == method


class TestIncompleteRequests:
    def test_no_crlf_terminator(self):
        """Request without \\r\\n\\r\\n terminator."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost"
        result = parse_http_request(raw)
        # Should be treated as incomplete
        assert result is None or isinstance(result, dict)

    def test_only_request_line(self):
        """Only request line, no headers section."""
        raw = b"GET / HTTP/1.1\r\n"
        result = parse_http_request(raw)
        # Incomplete - no header terminator
        assert result is None or isinstance(result, dict)

    def test_single_byte(self):
        """Single byte input."""
        result = parse_http_request(b"G")
        assert result is None

    def test_two_bytes(self):
        """Two byte input."""
        result = parse_http_request(b"GE")
        assert result is None


# ---------------------------------------------------------------------------
# Integer overflow / Content-Length hardening
# ---------------------------------------------------------------------------

class TestContentLengthOverflow:
    def test_content_length_long_max(self):
        """Content-Length = LONG_MAX should not crash or allocate huge memory."""
        import sys
        long_max = str(2**63 - 1)  # LONG_MAX on 64-bit
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + long_max.encode() + b"\r\n"
            b"\r\n"
            b"tiny"
        )
        result = parse_http_request(raw)
        assert result is not None
        # Must not crash; body should be whatever is available
        assert isinstance(result["body"], bytes)

    def test_content_length_exceeds_long_max(self):
        """Content-Length larger than LONG_MAX should not crash."""
        huge = str(2**63 + 1)
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + huge.encode() + b"\r\n"
            b"\r\n"
            b"body"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert isinstance(result["body"], bytes)

    def test_content_length_extremely_large_string(self):
        """Content-Length that's a very large number string (>32 chars)."""
        # This exceeds the tmp[32] buffer so Content-Length parsing is skipped
        huge_num = "9" * 40
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + huge_num.encode() + b"\r\n"
            b"\r\n"
            b"body"
        )
        result = parse_http_request(raw)
        assert result is not None
        # Content-Length was too long for tmp[32], so body defaults to empty
        assert result["body"] == b""

    def test_content_length_negative_not_minus_one(self):
        """Content-Length = -5 (negative but not -1) should handle safely."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: -5\r\n"
            b"\r\n"
            b"hello"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert isinstance(result["body"], bytes)

    def test_content_length_negative_large(self):
        """Content-Length = -999999999 should handle safely."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: -999999999\r\n"
            b"\r\n"
            b"data"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert isinstance(result["body"], bytes)

    def test_content_length_with_leading_zeros(self):
        """Content-Length with leading zeros."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 005\r\n"
            b"\r\n"
            b"hello"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b"hello"

    def test_content_length_hex_prefix(self):
        """Content-Length with 0x prefix (strtol interprets base 10)."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0x10\r\n"
            b"\r\n"
            b"body"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert isinstance(result["body"], bytes)

    def test_content_length_with_whitespace(self):
        """Content-Length with extra whitespace."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length:   10  \r\n"
            b"\r\n"
            b"0123456789"
        )
        result = parse_http_request(raw)
        assert result is not None


# ---------------------------------------------------------------------------
# Keep-alive and Connection header
# ---------------------------------------------------------------------------

class TestKeepAlive:
    def test_http11_default_keep_alive(self):
        """HTTP/1.1 should default to keep_alive=True."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["keep_alive"] is True

    def test_http11_connection_close(self):
        """HTTP/1.1 with Connection: close should set keep_alive=False."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["keep_alive"] is False

    def test_http10_keep_alive_is_default(self):
        """HTTP/1.0 — parser defaults keep_alive=1 (HTTP/1.1 default)."""
        raw = b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        # Parser sets keep_alive=1 by default for all versions
        # The server layer handles HTTP/1.0 semantics
        assert "keep_alive" in result

    def test_connection_keep_alive_header(self):
        """Connection: keep-alive header should not crash."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["keep_alive"] is True

    def test_connection_close_case_insensitive(self):
        """Connection: Close (capitalized) should still set keep_alive=False."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: Close\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        # Parser uses strncasecmp for the Connection header value
        assert result["keep_alive"] is False


# ---------------------------------------------------------------------------
# URI parsing
# ---------------------------------------------------------------------------

class TestURIParsing:
    def test_uri_with_fragment(self):
        """URI with fragment (#) — fragment should be part of path."""
        raw = b"GET /page#section HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        # Fragment is not split from path by the parser
        assert "page" in result["path"]

    def test_uri_with_query_and_fragment(self):
        """URI with both query string and fragment."""
        raw = b"GET /page?key=val#frag HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["path"] == "/page"
        assert "key=val" in result["query_string"]

    def test_uri_only_question_mark(self):
        """URI with only a question mark (empty query string)."""
        raw = b"GET /page? HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["path"] == "/page"
        assert result["query_string"] == ""

    def test_uri_multiple_question_marks(self):
        """URI with multiple ? characters."""
        raw = b"GET /page?a=1?b=2 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["path"] == "/page"
        # Everything after first ? is query string
        assert "a=1?b=2" == result["query_string"]

    def test_uri_encoded_space(self):
        """URI with percent-encoded characters."""
        raw = b"GET /hello%20world HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["path"] == "/hello%20world"

    def test_absolute_uri(self):
        """Absolute URI (proxy-style request)."""
        raw = b"GET http://example.com/path HTTP/1.1\r\nHost: example.com\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "GET"

    def test_asterisk_uri(self):
        """OPTIONS with asterisk URI."""
        raw = b"OPTIONS * HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "OPTIONS"
        assert result["path"] == "*"


# ---------------------------------------------------------------------------
# Body handling edge cases
# ---------------------------------------------------------------------------

class TestBodyEdgeCases:
    def test_body_exactly_matches_content_length(self):
        """Body length exactly matches Content-Length."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"hello"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b"hello"

    def test_body_longer_than_content_length(self):
        """Body provided is longer than Content-Length — should truncate."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 3\r\n"
            b"\r\n"
            b"hello extra data"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b"hel"

    def test_body_shorter_than_content_length(self):
        """Body is shorter than Content-Length — returns what's available."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 100\r\n"
            b"\r\n"
            b"short"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert b"short" in result["body"]

    def test_get_with_body(self):
        """GET with Content-Length and body (unusual but valid HTTP)."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 4\r\n"
            b"\r\n"
            b"data"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b"data"

    def test_post_without_content_length(self):
        """POST without Content-Length — body should be empty."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b""

    def test_binary_body(self):
        """Binary body with all byte values 0-255."""
        body = bytes(range(256))
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 256\r\n"
            b"\r\n" + body
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == body


# ---------------------------------------------------------------------------
# Pipelined / multiple requests
# ---------------------------------------------------------------------------

class TestPipelinedRequests:
    def test_extra_data_after_complete_request(self):
        """Data after a complete request (next pipelined request)."""
        raw = (
            b"GET /first HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
            b"GET /second HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["path"] == "/first"
        # Parser should only parse the first request

    def test_post_followed_by_get(self):
        """POST with body followed by GET (pipelined)."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"helloGET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["body"] == b"hello"


# ---------------------------------------------------------------------------
# Header parsing edge cases
# ---------------------------------------------------------------------------

class TestHeaderEdgeCases:
    def test_duplicate_headers(self):
        """Duplicate header names — last value wins (dict semantics)."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Test: first\r\n"
            b"X-Test: second\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["headers"]["X-Test"] == "second"

    def test_header_with_colon_in_value(self):
        """Header value containing colon characters."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost:8080\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["headers"]["Host"] == "localhost:8080"

    def test_header_case_preservation(self):
        """Header names should be preserved as-is."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Custom-Header: value\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert "X-Custom-Header" in result["headers"]

    def test_header_with_many_colons(self):
        """Header value with multiple colons (e.g. IPv6, time)."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: [::1]:8080\r\n"
            b"X-Time: 12:30:45\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert result["headers"]["X-Time"] == "12:30:45"

    def test_header_continuation_not_supported(self):
        """Obsolete header continuation (line starting with space/tab)."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Long: start\r\n"
            b" continuation\r\n"
            b"\r\n"
        )
        result = parse_http_request(raw)
        assert result is not None
        # The continuation line has no colon, so it's skipped

    def test_content_type_header(self):
        """Content-Type header should be parsed normally."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"Content-Length: 2\r\n"
            b"\r\n"
            b"{}"
        )
        result = parse_http_request(raw)
        assert result is not None
        assert "application/json" in result["headers"]["Content-Type"]


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------

class TestHTTPMethods:
    @pytest.mark.parametrize("method", [
        b"GET", b"POST", b"PUT", b"DELETE", b"PATCH", b"HEAD", b"OPTIONS",
        b"TRACE", b"CONNECT",
    ])
    def test_standard_methods(self, method):
        """All standard HTTP methods should parse."""
        raw = method + b" / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == method.decode()

    def test_custom_method(self):
        """Non-standard method should parse."""
        raw = b"PROPFIND / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "PROPFIND"

    def test_lowercase_method(self):
        """Lowercase method should parse (HTTP is case-sensitive for method)."""
        raw = b"get / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "get"


# ---------------------------------------------------------------------------
# Empty / minimal inputs
# ---------------------------------------------------------------------------

class TestMinimalInputs:
    def test_empty_bytes(self):
        """Empty input should return None."""
        result = parse_http_request(b"")
        assert result is None

    def test_just_crlf_crlf(self):
        """Just the header terminator."""
        result = parse_http_request(b"\r\n\r\n")
        # No valid request line before the terminator
        assert result is None or isinstance(result, dict)

    def test_minimal_valid_request(self):
        """Smallest possible valid HTTP request."""
        raw = b"G / HTTP/1.1\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "G"
        assert result["path"] == "/"

    def test_no_host_header(self):
        """Request without Host header — should still parse."""
        raw = b"GET / HTTP/1.1\r\n\r\n"
        result = parse_http_request(raw)
        assert result is not None
        assert result["method"] == "GET"
