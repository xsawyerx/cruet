"""Tests for matcher performance baseline and edge cases."""
import time
import pytest
from cruet._cruet import Rule, Map


class TestMatcherEdgeCases:
    def test_empty_map(self):
        m = Map()
        adapter = m.bind("localhost")
        with pytest.raises(LookupError):
            adapter.match("/anything")

    def test_root_only(self):
        m = Map()
        m.add(Rule("/", endpoint="index"))
        adapter = m.bind("localhost")
        ep, vals = adapter.match("/")
        assert ep == "index"

    def test_similar_prefixes(self):
        m = Map()
        m.add(Rule("/api", endpoint="api"))
        m.add(Rule("/api/v1", endpoint="api_v1"))
        m.add(Rule("/api/v2", endpoint="api_v2"))
        adapter = m.bind("localhost")
        assert adapter.match("/api")[0] == "api"
        assert adapter.match("/api/v1")[0] == "api_v1"
        assert adapter.match("/api/v2")[0] == "api_v2"

    def test_dynamic_before_static(self):
        """Static route takes priority over dynamic at the same position."""
        m = Map()
        m.add(Rule("/user/admin", endpoint="admin"))
        m.add(Rule("/user/<name>", endpoint="user"))
        adapter = m.bind("localhost")
        # Static match should win
        ep, vals = adapter.match("/user/admin")
        assert ep == "admin"
        # Dynamic should still work for others
        ep, vals = adapter.match("/user/john")
        assert ep == "user"
        assert vals == {"name": "john"}

    def test_uuid_route(self):
        m = Map()
        m.add(Rule("/item/<uuid:item_id>", endpoint="item"))
        adapter = m.bind("localhost")
        ep, vals = adapter.match("/item/12345678-1234-5678-1234-567812345678")
        assert ep == "item"
        import uuid
        assert isinstance(vals["item_id"], uuid.UUID)

    def test_path_converter_greedy(self):
        m = Map()
        m.add(Rule("/files/<path:filepath>", endpoint="files"))
        adapter = m.bind("localhost")
        ep, vals = adapter.match("/files/a/b/c/d.txt")
        assert vals["filepath"] == "a/b/c/d.txt"

    def test_any_converter(self):
        m = Map()
        m.add(Rule("/lang/<any(en,fr,de):lang>", endpoint="lang"))
        adapter = m.bind("localhost")
        ep, vals = adapter.match("/lang/en")
        assert vals["lang"] == "en"
        with pytest.raises(LookupError):
            adapter.match("/lang/es")


class TestMatcherPerformance:
    def test_100_static_routes_fast(self):
        """100 static routes should match very quickly."""
        m = Map()
        for i in range(100):
            m.add(Rule(f"/route/{i}", endpoint=f"route_{i}"))
        adapter = m.bind("localhost")

        # Warm up
        adapter.match("/route/50")

        start = time.perf_counter()
        iterations = 10000
        for _ in range(iterations):
            adapter.match("/route/50")
        elapsed = time.perf_counter() - start

        per_match_us = (elapsed / iterations) * 1_000_000
        # Should be well under 10 microseconds per match
        assert per_match_us < 50, f"Too slow: {per_match_us:.2f} us/match"

    def test_dynamic_routes_fast(self):
        """Dynamic route matching should also be fast."""
        m = Map()
        for i in range(50):
            m.add(Rule(f"/api/v{i}/<name>", endpoint=f"api_{i}"))
        adapter = m.bind("localhost")

        adapter.match("/api/v25/hello")

        start = time.perf_counter()
        iterations = 10000
        for _ in range(iterations):
            adapter.match("/api/v25/hello")
        elapsed = time.perf_counter() - start

        per_match_us = (elapsed / iterations) * 1_000_000
        assert per_match_us < 100, f"Too slow: {per_match_us:.2f} us/match"
