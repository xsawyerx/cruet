"""Tests for CoW-friendly routing internals.

Verifies that the bitmask-based method dispatch, C hash table static index,
and C array dynamic rules all work correctly.
"""

import pytest
from cruet._cruet import Rule, Map


# ---------------------------------------------------------------------------
# TestMethodsBitmask
# ---------------------------------------------------------------------------


class TestMethodsBitmask:
    """Tests for the methods bitmask implementation in Rule."""

    def test_all_standard_methods(self):
        """All 8 standard methods should be representable."""
        methods = ["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"]
        rule = Rule("/test", endpoint="test", methods=methods)
        for m in methods:
            assert m in rule.methods, f"{m} should be in rule.methods"

    def test_nonstandard_methods_fallback(self):
        """Non-standard methods (PROPFIND, MKCOL) should work via fallback."""
        rule = Rule("/webdav", endpoint="webdav", methods=["PROPFIND", "MKCOL"])
        assert "PROPFIND" in rule.methods
        assert "MKCOL" in rule.methods
        # HEAD and OPTIONS are always added
        assert "HEAD" in rule.methods
        assert "OPTIONS" in rule.methods

    def test_nonstandard_method_matching(self):
        """Non-standard methods should be matchable through MapAdapter."""
        m = Map()
        m.add(Rule("/webdav", endpoint="webdav", methods=["PROPFIND", "GET"]))
        adapter = m.bind("localhost")

        endpoint, values = adapter.match("/webdav", method="PROPFIND")
        assert endpoint == "webdav"
        assert values == {}

    def test_nonstandard_method_405(self):
        """Non-standard method on a standard-only route should give 405."""
        m = Map()
        m.add(Rule("/api", endpoint="api", methods=["GET", "POST"]))
        adapter = m.bind("localhost")

        with pytest.raises(LookupError, match="405"):
            adapter.match("/api", method="PROPFIND")

    def test_case_insensitive_methods(self):
        """Methods should be case-insensitive."""
        rule = Rule("/test", endpoint="test", methods=["get", "post"])
        assert "GET" in rule.methods
        assert "POST" in rule.methods

    def test_methods_returns_frozenset(self):
        """rule.methods should return a frozenset."""
        rule = Rule("/test", endpoint="test", methods=["GET"])
        assert isinstance(rule.methods, frozenset)

    def test_default_methods(self):
        """Default methods should be {GET, HEAD, OPTIONS}."""
        rule = Rule("/test", endpoint="test")
        assert rule.methods == frozenset({"GET", "HEAD", "OPTIONS"})

    def test_mixed_standard_nonstandard(self):
        """Mix of standard and non-standard methods should all be present."""
        rule = Rule(
            "/mixed",
            endpoint="mixed",
            methods=["GET", "POST", "PROPFIND", "MKCOL", "DELETE"],
        )
        expected = {"GET", "POST", "PROPFIND", "MKCOL", "DELETE", "HEAD", "OPTIONS"}
        assert rule.methods == frozenset(expected)


# ---------------------------------------------------------------------------
# TestStaticIndexHashTable
# ---------------------------------------------------------------------------


class TestStaticIndexHashTable:
    """Tests for the C hash table static index."""

    def test_500_static_routes(self):
        """500 static routes should all be findable (exercises resize)."""
        m = Map()
        for i in range(500):
            m.add(Rule(f"/route/{i}", endpoint=f"ep_{i}"))
        adapter = m.bind("localhost")

        for i in range(500):
            endpoint, values = adapter.match(f"/route/{i}")
            assert endpoint == f"ep_{i}"
            assert values == {}

    def test_similar_prefix_paths(self):
        """Similar-prefix paths should not collide."""
        m = Map()
        paths = [
            "/api/users",
            "/api/user",
            "/api/users/list",
            "/api/users/new",
            "/api/use",
            "/api/usersettings",
        ]
        for i, p in enumerate(paths):
            m.add(Rule(p, endpoint=f"ep_{i}"))
        adapter = m.bind("localhost")

        for i, p in enumerate(paths):
            endpoint, values = adapter.match(p)
            assert endpoint == f"ep_{i}"

    def test_duplicate_path_first_wins(self):
        """Duplicate path should keep the first rule."""
        m = Map()
        m.add(Rule("/dup", endpoint="first"))
        m.add(Rule("/dup", endpoint="second"))
        adapter = m.bind("localhost")

        endpoint, values = adapter.match("/dup")
        assert endpoint == "first"

    def test_1000_routes_multiple_resizes(self):
        """1000 routes should work (multiple hash table resizes)."""
        m = Map()
        for i in range(1000):
            m.add(Rule(f"/r/{i}", endpoint=f"e_{i}"))
        adapter = m.bind("localhost")

        # Sample a few
        for i in [0, 1, 42, 100, 500, 999]:
            endpoint, values = adapter.match(f"/r/{i}")
            assert endpoint == f"e_{i}"


# ---------------------------------------------------------------------------
# TestDynamicRulesCArray
# ---------------------------------------------------------------------------


class TestDynamicRulesCArray:
    """Tests for the C array of dynamic rules."""

    def test_200_dynamic_routes(self):
        """200 dynamic routes should all match correctly."""
        m = Map()
        for i in range(200):
            m.add(Rule(f"/item/<name>/action{i}", endpoint=f"act_{i}"))
        adapter = m.bind("localhost")

        for i in range(200):
            endpoint, values = adapter.match(f"/item/foo/action{i}")
            assert endpoint == f"act_{i}"
            assert values == {"name": "foo"}

    def test_mixed_static_dynamic(self):
        """100 static + 100 dynamic routes, all should match correctly."""
        m = Map()
        for i in range(100):
            m.add(Rule(f"/static/{i}", endpoint=f"s_{i}"))
        for i in range(100):
            m.add(Rule(f"/dynamic/<int:id>/sub{i}", endpoint=f"d_{i}"))
        adapter = m.bind("localhost")

        # Check static routes
        for i in range(100):
            endpoint, values = adapter.match(f"/static/{i}")
            assert endpoint == f"s_{i}"
            assert values == {}

        # Check dynamic routes
        for i in range(100):
            endpoint, values = adapter.match(f"/dynamic/42/sub{i}")
            assert endpoint == f"d_{i}"
            assert values == {"id": 42}
