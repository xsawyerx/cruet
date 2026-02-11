"""Tests for URL converters (string, int, float, uuid, path, any)."""
import uuid as uuid_mod
import pytest
from cruet._cruet import (
    StringConverter, IntConverter, FloatConverter,
    UUIDConverter, PathConverter, AnyConverter,
)


class TestStringConverter:
    def test_convert_simple(self):
        c = StringConverter()
        assert c.convert("hello") == "hello"

    def test_convert_minlength(self):
        c = StringConverter(minlength=3)
        assert c.convert("abc") == "abc"
        with pytest.raises(ValueError):
            c.convert("ab")

    def test_convert_maxlength(self):
        c = StringConverter(maxlength=5)
        assert c.convert("abcde") == "abcde"
        with pytest.raises(ValueError):
            c.convert("abcdef")

    def test_convert_length(self):
        c = StringConverter(length=4)
        assert c.convert("abcd") == "abcd"
        with pytest.raises(ValueError):
            c.convert("abc")
        with pytest.raises(ValueError):
            c.convert("abcde")

    def test_to_url(self):
        c = StringConverter()
        assert c.to_url("hello") == "hello"

    def test_regex_default(self):
        c = StringConverter()
        assert c.regex == "[^/]+"

    def test_regex_with_length(self):
        c = StringConverter(length=4)
        assert c.regex == "[^/]{4}"

    def test_regex_with_minmax(self):
        c = StringConverter(minlength=2, maxlength=5)
        assert c.regex == "[^/]{2,5}"


class TestIntConverter:
    def test_convert_simple(self):
        c = IntConverter()
        assert c.convert("42") == 42
        assert isinstance(c.convert("42"), int)

    def test_convert_zero(self):
        c = IntConverter()
        assert c.convert("0") == 0

    def test_convert_negative_fails(self):
        c = IntConverter()
        with pytest.raises(ValueError):
            c.convert("-1")

    def test_convert_non_numeric_fails(self):
        c = IntConverter()
        with pytest.raises(ValueError):
            c.convert("abc")

    def test_convert_fixed_digits(self):
        c = IntConverter(fixed_digits=3)
        assert c.convert("042") == 42
        with pytest.raises(ValueError):
            c.convert("42")
        with pytest.raises(ValueError):
            c.convert("0042")

    def test_convert_min(self):
        c = IntConverter(min=10)
        assert c.convert("10") == 10
        with pytest.raises(ValueError):
            c.convert("9")

    def test_convert_max(self):
        c = IntConverter(max=100)
        assert c.convert("100") == 100
        with pytest.raises(ValueError):
            c.convert("101")

    def test_to_url(self):
        c = IntConverter()
        assert c.to_url(42) == "42"

    def test_regex(self):
        c = IntConverter()
        assert c.regex == "\\d+"


class TestFloatConverter:
    def test_convert_simple(self):
        c = FloatConverter()
        assert c.convert("3.14") == pytest.approx(3.14)
        assert isinstance(c.convert("3.14"), float)

    def test_convert_integer_form(self):
        c = FloatConverter()
        assert c.convert("42.0") == 42.0

    def test_convert_non_numeric_fails(self):
        c = FloatConverter()
        with pytest.raises(ValueError):
            c.convert("abc")

    def test_convert_min(self):
        c = FloatConverter(min=0.0)
        assert c.convert("0.0") == 0.0
        with pytest.raises(ValueError):
            c.convert("-1.0")

    def test_convert_max(self):
        c = FloatConverter(max=10.0)
        assert c.convert("10.0") == 10.0
        with pytest.raises(ValueError):
            c.convert("10.1")

    def test_to_url(self):
        c = FloatConverter()
        assert c.to_url(3.14) == "3.14"

    def test_regex(self):
        c = FloatConverter()
        assert c.regex == "\\d+\\.\\d+"


class TestUUIDConverter:
    def test_convert_simple(self):
        val = "12345678-1234-5678-1234-567812345678"
        c = UUIDConverter()
        result = c.convert(val)
        assert isinstance(result, uuid_mod.UUID)
        assert str(result) == val

    def test_convert_invalid(self):
        c = UUIDConverter()
        with pytest.raises(ValueError):
            c.convert("not-a-uuid")

    def test_to_url(self):
        c = UUIDConverter()
        u = uuid_mod.UUID("12345678-1234-5678-1234-567812345678")
        assert c.to_url(u) == "12345678-1234-5678-1234-567812345678"

    def test_regex(self):
        c = UUIDConverter()
        assert "[0-9a-f]" in c.regex.lower()


class TestPathConverter:
    def test_convert_simple(self):
        c = PathConverter()
        assert c.convert("foo/bar/baz") == "foo/bar/baz"

    def test_convert_single_segment(self):
        c = PathConverter()
        assert c.convert("file.txt") == "file.txt"

    def test_to_url(self):
        c = PathConverter()
        assert c.to_url("foo/bar") == "foo/bar"

    def test_regex(self):
        c = PathConverter()
        assert c.regex == "[^/].*?"


class TestAnyConverter:
    def test_convert_valid(self):
        c = AnyConverter(items=["foo", "bar", "baz"])
        assert c.convert("foo") == "foo"
        assert c.convert("bar") == "bar"

    def test_convert_invalid(self):
        c = AnyConverter(items=["foo", "bar"])
        with pytest.raises(ValueError):
            c.convert("qux")

    def test_to_url(self):
        c = AnyConverter(items=["foo", "bar"])
        assert c.to_url("foo") == "foo"

    def test_regex(self):
        c = AnyConverter(items=["foo", "bar", "baz"])
        # Should be alternation like "foo|bar|baz"
        assert "foo" in c.regex
        assert "bar" in c.regex
