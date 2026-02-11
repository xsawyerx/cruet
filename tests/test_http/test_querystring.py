"""Tests for parse_qs — query string parsing."""
import pytest
from cruet._cruet import parse_qs


class TestParseQsSimple:
    def test_single_key_value(self):
        result = parse_qs("key=value")
        assert result["key"] == ["value"]

    def test_multiple_keys(self):
        result = parse_qs("a=1&b=2&c=3")
        assert result["a"] == ["1"]
        assert result["b"] == ["2"]
        assert result["c"] == ["3"]

    def test_returns_dict_of_lists(self):
        result = parse_qs("x=hello")
        assert isinstance(result, dict)
        assert isinstance(result["x"], list)


class TestParseQsMultiValue:
    def test_duplicate_keys(self):
        result = parse_qs("a=1&a=2")
        assert result["a"] == ["1", "2"]

    def test_triple_values(self):
        result = parse_qs("color=red&color=green&color=blue")
        assert result["color"] == ["red", "green", "blue"]

    def test_mixed_single_and_multi(self):
        result = parse_qs("a=1&b=2&a=3")
        assert result["a"] == ["1", "3"]
        assert result["b"] == ["2"]


class TestParseQsUrlDecoding:
    def test_percent_encoded_space(self):
        result = parse_qs("name=hello%20world")
        assert result["name"] == ["hello world"]

    def test_plus_as_space(self):
        result = parse_qs("name=hello+world")
        assert result["name"] == ["hello world"]

    def test_percent_encoded_special_chars(self):
        result = parse_qs("q=%26%3D%3F")
        assert result["q"] == ["&=?"]

    def test_percent_encoded_key(self):
        result = parse_qs("my%20key=value")
        assert result["my key"] == ["value"]

    def test_unicode_percent_encoded(self):
        # %C3%A9 is UTF-8 for 'e' with acute accent
        result = parse_qs("name=caf%C3%A9")
        assert result["name"] == ["caf\u00e9"]


class TestParseQsEmptyValues:
    def test_empty_value(self):
        result = parse_qs("key=")
        assert result["key"] == [""]

    def test_key_without_equals(self):
        """A key with no '=' should still be captured."""
        result = parse_qs("flag")
        assert "flag" in result
        assert result["flag"] == [""]

    def test_mixed_empty_and_valued(self):
        result = parse_qs("a=1&b=&c=3")
        assert result["a"] == ["1"]
        assert result["b"] == [""]
        assert result["c"] == ["3"]


class TestParseQsEdgeCases:
    def test_empty_string(self):
        result = parse_qs("")
        assert result == {}

    def test_only_ampersands(self):
        result = parse_qs("&&&")
        assert result == {}

    def test_leading_ampersand(self):
        result = parse_qs("&a=1")
        assert result["a"] == ["1"]

    def test_trailing_ampersand(self):
        result = parse_qs("a=1&")
        assert result["a"] == ["1"]

    def test_double_ampersand(self):
        result = parse_qs("a=1&&b=2")
        assert result["a"] == ["1"]
        assert result["b"] == ["2"]

    def test_equals_in_value(self):
        result = parse_qs("equation=1+1=2")
        assert result["equation"] == ["1 1=2"]

    def test_semicolon_separator(self):
        """Some query strings use ; as separator."""
        result = parse_qs("a=1;b=2")
        # Implementation may or may not support ';' -- just ensure no crash
        assert isinstance(result, dict)
