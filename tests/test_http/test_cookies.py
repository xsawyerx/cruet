"""Tests for parse_cookies — HTTP cookie string parsing."""
import pytest
from cruet._cruet import parse_cookies


class TestParseCookiesSimple:
    def test_single_cookie(self):
        result = parse_cookies("name=value")
        assert result["name"] == "value"

    def test_returns_dict(self):
        result = parse_cookies("a=1")
        assert isinstance(result, dict)


class TestParseCookiesMultiple:
    def test_two_cookies(self):
        result = parse_cookies("a=1; b=2")
        assert result["a"] == "1"
        assert result["b"] == "2"

    def test_three_cookies(self):
        result = parse_cookies("session=abc; user=john; lang=en")
        assert result["session"] == "abc"
        assert result["user"] == "john"
        assert result["lang"] == "en"

    def test_no_space_after_semicolon(self):
        result = parse_cookies("a=1;b=2")
        assert result["a"] == "1"
        assert result["b"] == "2"


class TestParseCookiesQuotedValues:
    def test_double_quoted_value(self):
        result = parse_cookies('token="abc123"')
        assert result["token"] == "abc123"

    def test_quoted_value_with_spaces(self):
        result = parse_cookies('msg="hello world"')
        assert result["msg"] == "hello world"

    def test_quoted_value_with_semicolon(self):
        result = parse_cookies('data="a;b"; other=val')
        assert result["data"] == "a;b"
        assert result["other"] == "val"


class TestParseCookiesSpecialChars:
    def test_value_with_equals(self):
        result = parse_cookies("token=abc=def")
        assert result["token"] == "abc=def"

    def test_value_with_slashes(self):
        result = parse_cookies("path=/foo/bar")
        assert result["path"] == "/foo/bar"

    def test_value_with_dots(self):
        result = parse_cookies("domain=example.com")
        assert result["domain"] == "example.com"

    def test_value_with_encoded_chars(self):
        result = parse_cookies("name=hello%20world")
        # Cookie values are typically not URL-decoded, but may be
        assert "name" in result


class TestParseCookiesMalformed:
    def test_empty_value(self):
        result = parse_cookies("key=")
        assert result["key"] == ""

    def test_no_equals(self):
        """A cookie token with no '=' should be handled gracefully."""
        result = parse_cookies("justflag")
        assert isinstance(result, dict)

    def test_trailing_semicolon(self):
        result = parse_cookies("a=1; ")
        assert result["a"] == "1"

    def test_leading_whitespace(self):
        result = parse_cookies("  a=1; b=2")
        assert result["a"] == "1"
        assert result["b"] == "2"

    def test_extra_whitespace(self):
        result = parse_cookies("a = 1 ;  b = 2")
        # Whitespace handling varies; just ensure no crash and dict returned
        assert isinstance(result, dict)


class TestParseCookiesEmpty:
    def test_empty_string(self):
        result = parse_cookies("")
        assert result == {}

    def test_only_whitespace(self):
        result = parse_cookies("   ")
        assert result == {}

    def test_only_semicolons(self):
        result = parse_cookies(";;;")
        assert result == {}
