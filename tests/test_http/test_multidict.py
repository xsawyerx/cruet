"""Tests for the MultiDict class in wrappers.py."""
import pytest
from cruet.wrappers import MultiDict


class TestMultiDictGet:
    def test_get_returns_first_value(self):
        """get() should return the first value from a list."""
        md = MultiDict({"key": ["first", "second", "third"]})
        assert md.get("key") == "first"

    def test_get_with_default(self):
        """get() with default when key is missing."""
        md = MultiDict({"key": ["value"]})
        assert md.get("missing") is None
        assert md.get("missing", "default") == "default"

    def test_get_non_list_value(self):
        """get() with a non-list value should return it directly."""
        md = MultiDict({"key": "single"})
        assert md.get("key") == "single"

    def test_get_empty_list(self):
        """get() with empty list should return default."""
        md = MultiDict({"key": []})
        assert md.get("key") is None
        assert md.get("key", "default") == "default"


class TestMultiDictGetlist:
    def test_getlist_returns_full_list(self):
        """getlist() should return the full list."""
        md = MultiDict({"key": ["a", "b", "c"]})
        assert md.getlist("key") == ["a", "b", "c"]

    def test_getlist_missing_key(self):
        """getlist() for missing key returns empty list."""
        md = MultiDict({"key": ["value"]})
        assert md.getlist("missing") == []

    def test_getlist_single_value(self):
        """getlist() with non-list value wraps it."""
        md = MultiDict({"key": "single"})
        assert md.getlist("key") == ["single"]

    def test_getlist_returns_copy(self):
        """getlist() should return a copy, not the original list."""
        original = ["a", "b"]
        md = MultiDict({"key": original})
        result = md.getlist("key")
        assert result == original
        assert result is not original  # Should be a copy

    def test_getlist_empty_list(self):
        """getlist() with empty list stored."""
        md = MultiDict({"key": []})
        assert md.getlist("key") == []


class TestMultiDictSubscript:
    def test_subscript_returns_first(self):
        """[] subscript should return the first value from a list."""
        md = MultiDict({"key": ["first", "second"]})
        assert md["key"] == "first"

    def test_subscript_non_list(self):
        """[] subscript with non-list value returns it directly."""
        md = MultiDict({"key": "value"})
        assert md["key"] == "value"

    def test_subscript_missing_key_raises(self):
        """[] subscript for missing key should raise KeyError."""
        md = MultiDict({"key": ["value"]})
        with pytest.raises(KeyError):
            _ = md["missing"]

    def test_subscript_empty_list(self):
        """[] subscript with empty list returns None."""
        md = MultiDict({"key": []})
        assert md["key"] is None


class TestMultiDictDictBehavior:
    def test_in_operator(self):
        """'in' operator should work."""
        md = MultiDict({"key": ["value"]})
        assert "key" in md
        assert "missing" not in md

    def test_len(self):
        """len() should work."""
        md = MultiDict({"a": ["1"], "b": ["2"], "c": ["3"]})
        assert len(md) == 3

    def test_iteration(self):
        """Iterating should yield keys."""
        md = MultiDict({"a": ["1"], "b": ["2"]})
        keys = set(md)
        assert keys == {"a", "b"}

    def test_dict_keys(self):
        """keys() should return dict keys."""
        md = MultiDict({"a": ["1"], "b": ["2"]})
        assert set(md.keys()) == {"a", "b"}

    def test_is_subclass_of_dict(self):
        """MultiDict should be a subclass of dict."""
        md = MultiDict()
        assert isinstance(md, dict)

    def test_dict_get_method(self):
        """dict.get() should work through MultiDict.get()."""
        md = MultiDict({"key": ["first", "second"]})
        # MultiDict.get overrides dict.get
        assert md.get("key") == "first"
        assert md.get("missing", "default") == "default"


class TestMultiDictEmpty:
    def test_empty_multidict(self):
        """Empty MultiDict should work."""
        md = MultiDict()
        assert len(md) == 0
        assert md.get("key") is None
        assert md.getlist("key") == []
        assert "key" not in md

    def test_empty_multidict_from_empty_dict(self):
        """MultiDict from empty dict."""
        md = MultiDict({})
        assert len(md) == 0


class TestMultiDictFromParseQs:
    def test_typical_parse_qs_output(self):
        """MultiDict should work with typical parse_qs output format."""
        # parse_qs returns dict[str, list[str]]
        raw = {"name": ["John"], "colors": ["red", "blue", "green"]}
        md = MultiDict(raw)
        assert md.get("name") == "John"
        assert md["name"] == "John"
        assert md.getlist("name") == ["John"]
        assert md.get("colors") == "red"
        assert md["colors"] == "red"
        assert md.getlist("colors") == ["red", "blue", "green"]

    def test_modification(self):
        """MultiDict should support modification like a dict."""
        md = MultiDict({"key": ["value"]})
        md["new_key"] = ["new_value"]
        assert md.get("new_key") == "new_value"
