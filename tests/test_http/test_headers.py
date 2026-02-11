"""Tests for CHeaders — case-insensitive multi-value header container."""
import pytest
from cruet._cruet import CHeaders


class TestCHeadersCreation:
    def test_create_empty(self):
        h = CHeaders()
        assert len(h) == 0

    def test_create_from_dict(self):
        h = CHeaders({"Content-Type": "text/html", "X-Custom": "val"})
        assert h.get("Content-Type") == "text/html"
        assert h.get("X-Custom") == "val"

    def test_create_from_list_of_tuples(self):
        h = CHeaders([("Content-Type", "text/html"), ("Accept", "application/json")])
        assert h.get("Content-Type") == "text/html"
        assert h.get("Accept") == "application/json"

    def test_create_from_list_multi_value(self):
        h = CHeaders([("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
        assert h.getlist("Set-Cookie") == ["a=1", "b=2"]


class TestCHeadersCaseInsensitive:
    def test_get_case_insensitive(self):
        h = CHeaders({"Content-Type": "text/html"})
        assert h.get("content-type") == "text/html"
        assert h.get("CONTENT-TYPE") == "text/html"
        assert h.get("Content-Type") == "text/html"
        assert h.get("cOnTeNt-TyPe") == "text/html"

    def test_contains_case_insensitive(self):
        h = CHeaders({"X-Request-Id": "abc123"})
        assert "X-Request-Id" in h
        assert "x-request-id" in h
        assert "X-REQUEST-ID" in h

    def test_set_case_insensitive(self):
        h = CHeaders()
        h.set("Content-Type", "text/html")
        assert h.get("content-type") == "text/html"

    def test_set_overwrites_existing(self):
        h = CHeaders({"Content-Type": "text/html"})
        h.set("content-type", "application/json")
        assert h.get("Content-Type") == "application/json"
        assert len(h.getlist("Content-Type")) == 1


class TestCHeadersGet:
    def test_get_existing(self):
        h = CHeaders({"Host": "example.com"})
        assert h.get("Host") == "example.com"

    def test_get_missing_returns_none(self):
        h = CHeaders()
        assert h.get("Host") is None

    def test_get_missing_with_default(self):
        h = CHeaders()
        assert h.get("Host", "fallback") == "fallback"

    def test_getlist_single(self):
        h = CHeaders({"Accept": "text/html"})
        assert h.getlist("Accept") == ["text/html"]

    def test_getlist_multiple(self):
        h = CHeaders([("Accept", "text/html"), ("Accept", "application/json")])
        result = h.getlist("Accept")
        assert "text/html" in result
        assert "application/json" in result
        assert len(result) == 2

    def test_getlist_missing(self):
        h = CHeaders()
        assert h.getlist("Accept") == []


class TestCHeadersSet:
    def test_set_new_key(self):
        h = CHeaders()
        h.set("X-Foo", "bar")
        assert h.get("X-Foo") == "bar"

    def test_set_replaces_all_values(self):
        h = CHeaders([("X-Foo", "a"), ("X-Foo", "b")])
        h.set("X-Foo", "c")
        assert h.getlist("X-Foo") == ["c"]

    def test_add_appends(self):
        h = CHeaders({"Accept": "text/html"})
        h.add("Accept", "application/json")
        assert h.getlist("Accept") == ["text/html", "application/json"]


class TestCHeadersLen:
    def test_len_empty(self):
        h = CHeaders()
        assert len(h) == 0

    def test_len_single(self):
        h = CHeaders({"Host": "example.com"})
        assert len(h) == 1

    def test_len_multiple_keys(self):
        h = CHeaders({"Host": "example.com", "Accept": "text/html"})
        assert len(h) == 2

    def test_len_multi_value_counts_each(self):
        """Each header line counts as one entry."""
        h = CHeaders([("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
        assert len(h) == 2


class TestCHeadersContains:
    def test_contains_true(self):
        h = CHeaders({"Host": "example.com"})
        assert "Host" in h

    def test_contains_false(self):
        h = CHeaders({"Host": "example.com"})
        assert "Accept" not in h


class TestCHeadersIter:
    def test_iter_empty(self):
        h = CHeaders()
        assert list(h) == []

    def test_iter_returns_tuples(self):
        h = CHeaders([("Host", "example.com"), ("Accept", "text/html")])
        items = list(h)
        assert len(items) == 2
        assert all(isinstance(item, tuple) and len(item) == 2 for item in items)

    def test_iter_preserves_multi_values(self):
        h = CHeaders([("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
        items = list(h)
        assert len(items) == 2
        values = [v for k, v in items if k.lower() == "set-cookie"]
        assert "a=1" in values
        assert "b=2" in values

    def test_iter_order(self):
        """Iteration should preserve insertion order."""
        pairs = [("Host", "example.com"), ("Accept", "text/html"),
                 ("Content-Type", "application/json")]
        h = CHeaders(pairs)
        items = list(h)
        for i, (k, v) in enumerate(pairs):
            assert items[i][0].lower() == k.lower()
            assert items[i][1] == v
