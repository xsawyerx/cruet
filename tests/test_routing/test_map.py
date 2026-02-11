"""Tests for the URL Map (rule container + bind + match)."""
import pytest
from cruet._cruet import Rule, Map, MapAdapter


class TestMapBasic:
    def test_create_map(self):
        m = Map()
        assert m is not None

    def test_add_rule(self):
        m = Map()
        r = Rule("/hello", endpoint="hello")
        m.add(r)

    def test_add_multiple_rules(self):
        m = Map()
        m.add(Rule("/", endpoint="index"))
        m.add(Rule("/about", endpoint="about"))
        m.add(Rule("/contact", endpoint="contact"))

    def test_bind(self):
        m = Map()
        m.add(Rule("/hello", endpoint="hello"))
        adapter = m.bind("localhost")
        assert isinstance(adapter, MapAdapter)


class TestMapAdapterMatch:
    def setup_method(self):
        self.map = Map()
        self.map.add(Rule("/", endpoint="index"))
        self.map.add(Rule("/hello", endpoint="hello"))
        self.map.add(Rule("/user/<name>", endpoint="user_profile"))
        self.map.add(Rule("/user/<name>/post/<int:post_id>", endpoint="user_post"))
        self.map.add(Rule("/submit", endpoint="submit", methods=["POST"]))
        self.adapter = self.map.bind("localhost")

    def test_match_index(self):
        endpoint, values = self.adapter.match("/")
        assert endpoint == "index"
        assert values == {}

    def test_match_static(self):
        endpoint, values = self.adapter.match("/hello")
        assert endpoint == "hello"
        assert values == {}

    def test_match_dynamic_string(self):
        endpoint, values = self.adapter.match("/user/john")
        assert endpoint == "user_profile"
        assert values == {"name": "john"}

    def test_match_dynamic_multi(self):
        endpoint, values = self.adapter.match("/user/john/post/42")
        assert endpoint == "user_post"
        assert values == {"name": "john", "post_id": 42}

    def test_not_found(self):
        with pytest.raises(LookupError):
            self.adapter.match("/nonexistent")

    def test_method_not_allowed(self):
        """GET to POST-only route raises MethodNotAllowed-like error."""
        with pytest.raises(LookupError) as exc_info:
            self.adapter.match("/submit", method="GET")
        assert "405" in str(exc_info.value) or "Method" in str(exc_info.value)

    def test_method_match_post(self):
        endpoint, values = self.adapter.match("/submit", method="POST")
        assert endpoint == "submit"

    def test_method_head_implicit(self):
        """HEAD is always allowed if GET is allowed."""
        endpoint, values = self.adapter.match("/hello", method="HEAD")
        assert endpoint == "hello"

    def test_method_options_implicit(self):
        """OPTIONS is always allowed."""
        endpoint, values = self.adapter.match("/hello", method="OPTIONS")
        assert endpoint == "hello"


class TestMapAdapterBuild:
    def setup_method(self):
        self.map = Map()
        self.map.add(Rule("/", endpoint="index"))
        self.map.add(Rule("/user/<name>", endpoint="user_profile"))
        self.map.add(Rule("/user/<name>/post/<int:post_id>", endpoint="user_post"))
        self.adapter = self.map.bind("localhost")

    def test_build_static(self):
        url = self.adapter.build("index", {})
        assert url == "/"

    def test_build_dynamic(self):
        url = self.adapter.build("user_profile", {"name": "john"})
        assert url == "/user/john"

    def test_build_multi_dynamic(self):
        url = self.adapter.build("user_post", {"name": "john", "post_id": 5})
        assert url == "/user/john/post/5"

    def test_build_unknown_endpoint(self):
        with pytest.raises((KeyError, LookupError)):
            self.adapter.build("nonexistent", {})


class TestMapManyRoutes:
    def test_100_static_routes(self):
        m = Map()
        for i in range(100):
            m.add(Rule(f"/route{i}", endpoint=f"route{i}"))
        adapter = m.bind("localhost")
        for i in range(100):
            endpoint, values = adapter.match(f"/route{i}")
            assert endpoint == f"route{i}"

    def test_mixed_static_and_dynamic(self):
        m = Map()
        m.add(Rule("/users", endpoint="user_list"))
        m.add(Rule("/users/<name>", endpoint="user_detail"))
        m.add(Rule("/users/<name>/posts", endpoint="user_posts"))
        m.add(Rule("/users/<name>/posts/<int:id>", endpoint="user_post"))
        adapter = m.bind("localhost")

        ep, vals = adapter.match("/users")
        assert ep == "user_list"

        ep, vals = adapter.match("/users/john")
        assert ep == "user_detail"
        assert vals == {"name": "john"}

        ep, vals = adapter.match("/users/john/posts")
        assert ep == "user_posts"

        ep, vals = adapter.match("/users/john/posts/42")
        assert ep == "user_post"
        assert vals == {"name": "john", "id": 42}
