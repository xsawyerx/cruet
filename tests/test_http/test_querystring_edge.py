"""Adversarial edge case tests for parse_qs."""
import pytest
from cruet._cruet import parse_qs


class TestMalformedPercentEncoding:
    def test_percent_zz(self):
        """Invalid hex digits in percent encoding should not crash."""
        result = parse_qs("key=%ZZ")
        assert isinstance(result, dict)
        assert "key" in result

    def test_percent_only(self):
        """Bare percent sign should not crash."""
        result = parse_qs("key=%")
        assert isinstance(result, dict)

    def test_percent_single_digit(self):
        """Percent with single hex digit should not crash."""
        result = parse_qs("key=%2")
        assert isinstance(result, dict)

    def test_percent_at_end(self):
        """Percent at end of value."""
        result = parse_qs("key=abc%")
        assert isinstance(result, dict)

    def test_percent_single_at_end(self):
        """Percent followed by one char at end."""
        result = parse_qs("key=abc%2")
        assert isinstance(result, dict)

    def test_double_percent(self):
        """Double percent sign."""
        result = parse_qs("key=%%")
        assert isinstance(result, dict)

    def test_percent_with_non_hex(self):
        """Percent followed by non-hex characters."""
        result = parse_qs("key=%GH")
        assert isinstance(result, dict)


class TestNullBytesInQueryString:
    def test_null_in_key(self):
        """Null byte in key should not crash."""
        result = parse_qs("ke\x00y=value")
        assert isinstance(result, dict)

    def test_null_in_value(self):
        """Null byte in value should not crash."""
        result = parse_qs("key=val\x00ue")
        assert isinstance(result, dict)

    def test_encoded_null(self):
        """Percent-encoded null byte."""
        result = parse_qs("key=%00value")
        assert isinstance(result, dict)


class TestExtremelyLongQueryStrings:
    def test_very_long_value(self):
        """Value > 64KB should not crash."""
        long_val = "x" * 70000
        result = parse_qs(f"key={long_val}")
        assert isinstance(result, dict)
        assert "key" in result
        assert result["key"][0] == long_val

    def test_very_long_key(self):
        """Key > 64KB should not crash."""
        long_key = "k" * 70000
        result = parse_qs(f"{long_key}=value")
        assert isinstance(result, dict)
        assert long_key in result

    def test_very_long_query_string(self):
        """Overall string > 64KB should not crash."""
        qs = "&".join(f"k{i}=v{i}" for i in range(10000))
        result = parse_qs(qs)
        assert isinstance(result, dict)
        assert len(result) == 10000


class TestManyParameters:
    def test_1000_parameters(self):
        """1000+ unique parameters should not crash."""
        qs = "&".join(f"key{i}=val{i}" for i in range(1000))
        result = parse_qs(qs)
        assert isinstance(result, dict)
        assert len(result) == 1000
        assert result["key0"] == ["val0"]
        assert result["key999"] == ["val999"]

    def test_1000_same_key(self):
        """1000+ values for same key."""
        qs = "&".join(f"key=val{i}" for i in range(1000))
        result = parse_qs(qs)
        assert isinstance(result, dict)
        assert len(result["key"]) == 1000


class TestSpecialCharacters:
    def test_equals_in_key(self):
        """Equals sign in various positions."""
        result = parse_qs("a=b=c=d")
        assert isinstance(result, dict)
        assert "a" in result

    def test_only_equals(self):
        """Just equals signs."""
        result = parse_qs("===")
        assert isinstance(result, dict)

    def test_empty_key_with_value(self):
        """Empty key with a value."""
        result = parse_qs("=value")
        assert isinstance(result, dict)

    def test_multiple_empty_keys(self):
        """Multiple empty key-value pairs."""
        result = parse_qs("=a&=b&=c")
        assert isinstance(result, dict)

    def test_unicode_value(self):
        """Unicode characters in value."""
        result = parse_qs("name=%E4%B8%AD%E6%96%87")
        assert isinstance(result, dict)

    def test_plus_encoding(self):
        """Plus signs should be decoded as spaces."""
        result = parse_qs("msg=hello+world+foo")
        assert result["msg"] == ["hello world foo"]

    def test_mixed_encoding(self):
        """Mix of percent-encoding and plus-encoding."""
        result = parse_qs("msg=hello+world%21")
        assert result["msg"] == ["hello world!"]


# ---------------------------------------------------------------------------
# Empty / minimal inputs
# ---------------------------------------------------------------------------

class TestEmptyInputs:
    def test_empty_string(self):
        """Empty query string should return empty dict."""
        result = parse_qs("")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_only_ampersands(self):
        """Only delimiters — no actual key-value pairs."""
        result = parse_qs("&&&&&")
        assert isinstance(result, dict)

    def test_only_semicolons(self):
        """Semicolons as delimiters — should produce empty dict."""
        result = parse_qs(";;;")
        assert isinstance(result, dict)

    def test_single_ampersand(self):
        """Single ampersand."""
        result = parse_qs("&")
        assert isinstance(result, dict)

    def test_key_no_value_no_equals(self):
        """Key with no equals sign — should still have the key."""
        result = parse_qs("keyonly")
        assert isinstance(result, dict)
        assert "keyonly" in result
        assert result["keyonly"] == [""]

    def test_key_with_equals_no_value(self):
        """Key= with no value after equals."""
        result = parse_qs("key=")
        assert isinstance(result, dict)
        assert "key" in result
        assert result["key"] == [""]


# ---------------------------------------------------------------------------
# Percent encoding edge cases
# ---------------------------------------------------------------------------

class TestPercentEncodingEdge:
    def test_consecutive_percent_encoded(self):
        """Multiple consecutive percent-encoded chars."""
        result = parse_qs("key=%48%45%4C%4C%4F")
        assert isinstance(result, dict)
        assert result["key"] == ["HELLO"]

    def test_percent_encoded_ampersand(self):
        """Percent-encoded ampersand should NOT split."""
        result = parse_qs("key=a%26b")
        assert isinstance(result, dict)
        assert result["key"] == ["a&b"]

    def test_percent_encoded_equals(self):
        """Percent-encoded equals in value."""
        result = parse_qs("key=a%3Db")
        assert isinstance(result, dict)
        assert result["key"] == ["a=b"]

    def test_percent_encoded_percent(self):
        """Percent-encoded percent sign (%25)."""
        result = parse_qs("key=%25")
        assert isinstance(result, dict)
        assert result["key"] == ["%"]

    def test_double_encoded_percent(self):
        """Double-encoded percent (%2525)."""
        result = parse_qs("key=%2525")
        assert isinstance(result, dict)
        assert result["key"] == ["%25"]

    def test_null_byte_percent_encoded(self):
        """Percent-encoded null byte (%00) in value."""
        result = parse_qs("key=%00")
        assert isinstance(result, dict)
        # Should parse without crash

    def test_all_ascii_hex_values(self):
        """All single-byte ASCII hex values %00-%7F."""
        for i in range(128):
            qs = f"k=%{i:02X}"
            result = parse_qs(qs)
            assert isinstance(result, dict)

    def test_high_byte_percent_encoding(self):
        """High byte percent-encoding (%80+) may raise UnicodeDecodeError."""
        # Bytes 0x80-0xFF aren't valid single-byte UTF-8, so PyUnicode
        # may reject them. Just verify no crash/segfault.
        for i in range(0x80, 0x100):
            qs = f"k=%{i:02X}"
            try:
                result = parse_qs(qs)
                assert isinstance(result, dict)
            except UnicodeDecodeError:
                pass  # expected for non-UTF-8 byte sequences

    def test_lowercase_hex(self):
        """Lowercase hex digits in percent encoding."""
        result = parse_qs("key=%2f%3a")
        assert isinstance(result, dict)
        assert result["key"] == ["/:" ]

    def test_mixed_case_hex(self):
        """Mixed case hex digits."""
        result = parse_qs("key=%2F%3a")
        assert isinstance(result, dict)
        assert result["key"] == ["/:" ]


# ---------------------------------------------------------------------------
# Duplicate keys
# ---------------------------------------------------------------------------

class TestDuplicateKeys:
    def test_duplicate_keys_are_list(self):
        """Same key multiple times should create a list."""
        result = parse_qs("k=1&k=2&k=3")
        assert isinstance(result, dict)
        assert result["k"] == ["1", "2", "3"]

    def test_duplicate_and_unique_mixed(self):
        """Mix of duplicate and unique keys."""
        result = parse_qs("a=1&b=2&a=3&c=4")
        assert isinstance(result, dict)
        assert result["a"] == ["1", "3"]
        assert result["b"] == ["2"]
        assert result["c"] == ["4"]


# ---------------------------------------------------------------------------
# Semicolon as delimiter
# ---------------------------------------------------------------------------

class TestSemicolonDelimiter:
    def test_semicolon_separated(self):
        """Semicolons as pair delimiters (common in cookies/HTML forms)."""
        result = parse_qs("a=1;b=2;c=3")
        assert isinstance(result, dict)
        assert result["a"] == ["1"]
        assert result["b"] == ["2"]
        assert result["c"] == ["3"]

    def test_mixed_delimiters(self):
        """Mix of & and ; delimiters."""
        result = parse_qs("a=1&b=2;c=3")
        assert isinstance(result, dict)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------------

class TestStress:
    def test_deeply_nested_encoding(self):
        """Triple percent-encoded value."""
        # %25 -> %, so %2525 -> %25, %252525 -> %2525
        result = parse_qs("key=%252525")
        assert isinstance(result, dict)
        assert result["key"] == ["%2525"]

    def test_very_many_equals(self):
        """Key=val with many = in value."""
        result = parse_qs("key=" + "=" * 1000)
        assert isinstance(result, dict)
        assert "key" in result

    def test_alternating_delimiters(self):
        """Alternating & and ; with empty values."""
        result = parse_qs("&;".join(f"k{i}=v{i}" for i in range(500)))
        assert isinstance(result, dict)
