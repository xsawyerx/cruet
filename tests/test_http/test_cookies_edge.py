"""Adversarial edge case tests for parse_cookies."""
import pytest
from cruet._cruet import parse_cookies


class TestNullBytesInCookies:
    def test_null_in_value(self):
        """Null byte in cookie value should not crash."""
        result = parse_cookies("key=val\x00ue")
        assert isinstance(result, dict)

    def test_null_in_key(self):
        """Null byte in cookie name should not crash."""
        result = parse_cookies("ke\x00y=value")
        assert isinstance(result, dict)


class TestExtremelyLongCookies:
    def test_very_long_cookie_value(self):
        """Cookie value > 4KB should not crash."""
        long_val = "x" * 5000
        result = parse_cookies(f"session={long_val}")
        assert isinstance(result, dict)
        assert result["session"] == long_val

    def test_very_long_cookie_name(self):
        """Cookie name > 4KB should not crash."""
        long_key = "k" * 5000
        result = parse_cookies(f"{long_key}=value")
        assert isinstance(result, dict)
        assert result[long_key] == "value"


class TestManyCookies:
    def test_100_cookies(self):
        """100+ cookies in a single header should not crash."""
        cookie_str = "; ".join(f"cookie{i}=val{i}" for i in range(100))
        result = parse_cookies(cookie_str)
        assert isinstance(result, dict)
        assert len(result) >= 100
        assert result["cookie0"] == "val0"
        assert result["cookie99"] == "val99"

    def test_200_cookies(self):
        """200 cookies to stress-test the parser."""
        cookie_str = "; ".join(f"c{i}=v{i}" for i in range(200))
        result = parse_cookies(cookie_str)
        assert isinstance(result, dict)
        assert len(result) >= 200


class TestSpecialCharacters:
    def test_base64_encoded_value(self):
        """Base64-like value with equals signs."""
        result = parse_cookies("token=abc123def456==")
        assert isinstance(result, dict)
        assert result["token"] == "abc123def456=="

    def test_url_encoded_value(self):
        """URL-encoded characters in value."""
        result = parse_cookies("data=%7B%22key%22%3A%22val%22%7D")
        assert isinstance(result, dict)
        assert "data" in result

    def test_json_like_value(self):
        """JSON-like characters in value."""
        result = parse_cookies('data={"key":"val"}')
        assert isinstance(result, dict)
        assert "data" in result

    def test_comma_in_value(self):
        """Comma in cookie value."""
        result = parse_cookies("list=a,b,c; other=val")
        assert isinstance(result, dict)
        assert "list" in result

    def test_pipe_in_value(self):
        """Pipe character in value."""
        result = parse_cookies("flags=a|b|c")
        assert isinstance(result, dict)
        assert "flags" in result


class TestEdgeCaseFormats:
    def test_duplicate_cookie_names(self):
        """Duplicate cookie names -- last or first should win."""
        result = parse_cookies("key=first; key=second")
        assert isinstance(result, dict)
        assert result["key"] in ("first", "second")

    def test_cookie_with_no_value_no_equals(self):
        """Cookie with no value and no equals."""
        result = parse_cookies("flag; other=val")
        assert isinstance(result, dict)
        assert "other" in result

    def test_multiple_equals(self):
        """Multiple equals signs in cookie."""
        result = parse_cookies("token=abc=def=ghi")
        assert isinstance(result, dict)
        assert result["token"] == "abc=def=ghi"

    def test_whitespace_around_equals(self):
        """Whitespace around equals sign."""
        result = parse_cookies("key = value")
        assert isinstance(result, dict)

    def test_tab_separated(self):
        """Tab characters in cookie string."""
        result = parse_cookies("key=value\t; other=val")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Empty / minimal inputs
# ---------------------------------------------------------------------------

class TestEmptyInputs:
    def test_empty_string(self):
        """Empty cookie header should return empty dict."""
        result = parse_cookies("")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_only_semicolons(self):
        """Only semicolons — no actual cookies."""
        result = parse_cookies(";;;")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_only_whitespace(self):
        """Only whitespace characters."""
        result = parse_cookies("   \t  ")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_only_equals(self):
        """Just an equals sign."""
        result = parse_cookies("=")
        assert isinstance(result, dict)

    def test_semicolon_and_whitespace(self):
        """Semicolons with whitespace."""
        result = parse_cookies("; ; ; ")
        assert isinstance(result, dict)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Quoted values
# ---------------------------------------------------------------------------

class TestQuotedValues:
    def test_quoted_value(self):
        """Basic quoted cookie value."""
        result = parse_cookies('key="hello world"')
        assert isinstance(result, dict)
        assert result["key"] == "hello world"

    def test_quoted_value_with_semicolon(self):
        """Quoted value containing semicolon."""
        result = parse_cookies('key="a;b"; other=val')
        assert isinstance(result, dict)
        assert result["key"] == "a;b"

    def test_quoted_empty_value(self):
        """Quoted empty value."""
        result = parse_cookies('key=""')
        assert isinstance(result, dict)
        assert result["key"] == ""

    def test_unclosed_quote(self):
        """Unclosed quote — should not crash."""
        result = parse_cookies('key="unclosed')
        assert isinstance(result, dict)
        # Should extract what's there

    def test_quote_at_end(self):
        """Quote at very end of string."""
        result = parse_cookies('key="')
        assert isinstance(result, dict)

    def test_quoted_with_equals(self):
        """Quoted value containing equals."""
        result = parse_cookies('key="a=b=c"')
        assert isinstance(result, dict)
        assert result["key"] == "a=b=c"

    def test_quoted_with_spaces(self):
        """Quoted value with internal spaces."""
        result = parse_cookies('key="hello world foo"')
        assert isinstance(result, dict)
        assert result["key"] == "hello world foo"


# ---------------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------------

class TestCookieStress:
    def test_500_cookies(self):
        """500 cookies to stress test."""
        cookie_str = "; ".join(f"c{i}=v{i}" for i in range(500))
        result = parse_cookies(cookie_str)
        assert isinstance(result, dict)
        assert len(result) >= 500

    def test_cookie_value_with_all_printable_chars(self):
        """Cookie value with all printable ASCII chars."""
        import string
        val = string.printable.replace(";", "").replace('"', "")
        result = parse_cookies(f"key={val}")
        assert isinstance(result, dict)
        assert "key" in result

    def test_many_duplicate_names(self):
        """Many cookies with the same name — last wins."""
        cookie_str = "; ".join(f"key=val{i}" for i in range(100))
        result = parse_cookies(cookie_str)
        assert isinstance(result, dict)
        assert result["key"] == "val99"

    def test_very_long_cookie_header(self):
        """Cookie header > 100KB."""
        # 1000 cookies with 100-char values
        cookie_str = "; ".join(f"c{i}={'x'*100}" for i in range(1000))
        result = parse_cookies(cookie_str)
        assert isinstance(result, dict)
        assert len(result) == 1000


# ---------------------------------------------------------------------------
# Malformed cookies
# ---------------------------------------------------------------------------

class TestMalformedCookies:
    def test_missing_value(self):
        """Cookie with name and = but no value."""
        result = parse_cookies("key=; other=val")
        assert isinstance(result, dict)
        assert result["key"] == ""
        assert result["other"] == "val"

    def test_leading_semicolon(self):
        """Leading semicolon before first cookie."""
        result = parse_cookies("; key=val")
        assert isinstance(result, dict)
        assert result["key"] == "val"

    def test_trailing_semicolon(self):
        """Trailing semicolon after last cookie."""
        result = parse_cookies("key=val;")
        assert isinstance(result, dict)
        assert result["key"] == "val"

    def test_double_semicolons(self):
        """Double semicolons between cookies."""
        result = parse_cookies("a=1;; b=2")
        assert isinstance(result, dict)
        assert result["a"] == "1"
        assert result["b"] == "2"

    def test_no_value_no_equals_multiple(self):
        """Multiple malformed entries without values."""
        result = parse_cookies("flag1; flag2; key=val")
        assert isinstance(result, dict)
        assert result["key"] == "val"

    def test_spaces_everywhere(self):
        """Extra spaces in cookie string."""
        result = parse_cookies("  key  =  value  ;  other  =  val  ")
        assert isinstance(result, dict)
