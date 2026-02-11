"""Tests for URL Rule parsing and compilation."""
import pytest
from cruet._cruet import Rule


class TestRuleCreation:
    def test_static_rule(self):
        r = Rule("/hello")
        assert r.rule == "/hello"

    def test_dynamic_rule_string(self):
        r = Rule("/user/<name>")
        assert r.rule == "/user/<name>"

    def test_dynamic_rule_int(self):
        r = Rule("/user/<int:id>")
        assert r.rule == "/user/<int:id>"

    def test_dynamic_rule_float(self):
        r = Rule("/price/<float:amount>")
        assert r.rule == "/price/<float:amount>"

    def test_dynamic_rule_uuid(self):
        r = Rule("/item/<uuid:item_id>")
        assert r.rule == "/item/<uuid:item_id>"

    def test_dynamic_rule_path(self):
        r = Rule("/files/<path:filepath>")
        assert r.rule == "/files/<path:filepath>"

    def test_multiple_converters(self):
        r = Rule("/user/<name>/post/<int:post_id>")
        assert r.rule == "/user/<name>/post/<int:post_id>"

    def test_endpoint(self):
        r = Rule("/hello", endpoint="hello_endpoint")
        assert r.endpoint == "hello_endpoint"

    def test_methods_default(self):
        r = Rule("/hello")
        methods = r.methods
        assert "GET" in methods
        assert "HEAD" in methods
        assert "OPTIONS" in methods

    def test_methods_custom(self):
        r = Rule("/submit", methods=["POST"])
        methods = r.methods
        assert "POST" in methods
        assert "HEAD" in methods
        assert "OPTIONS" in methods

    def test_methods_multiple(self):
        r = Rule("/resource", methods=["GET", "POST", "PUT", "DELETE"])
        methods = r.methods
        for m in ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]:
            assert m in methods

    def test_strict_slashes_default(self):
        r = Rule("/hello")
        assert r.strict_slashes is True

    def test_strict_slashes_false(self):
        r = Rule("/hello", strict_slashes=False)
        assert r.strict_slashes is False

    def test_trailing_slash(self):
        r = Rule("/hello/")
        assert r.rule == "/hello/"


class TestRuleBuild:
    def test_build_static(self):
        r = Rule("/hello", endpoint="hello")
        assert r.build({}) == "/hello"

    def test_build_string(self):
        r = Rule("/user/<name>", endpoint="user")
        assert r.build({"name": "john"}) == "/user/john"

    def test_build_int(self):
        r = Rule("/user/<int:id>", endpoint="user")
        assert r.build({"id": 42}) == "/user/42"

    def test_build_multiple(self):
        r = Rule("/user/<name>/post/<int:post_id>", endpoint="post")
        assert r.build({"name": "john", "post_id": 5}) == "/user/john/post/5"

    def test_build_missing_arg_raises(self):
        r = Rule("/user/<name>", endpoint="user")
        with pytest.raises((KeyError, ValueError)):
            r.build({})


class TestRuleMatch:
    def test_match_static(self):
        r = Rule("/hello", endpoint="hello")
        result = r.match("/hello")
        assert result == {}

    def test_match_string(self):
        r = Rule("/user/<name>", endpoint="user")
        result = r.match("/user/john")
        assert result == {"name": "john"}

    def test_match_int(self):
        r = Rule("/user/<int:id>", endpoint="user")
        result = r.match("/user/42")
        assert result == {"id": 42}

    def test_match_float(self):
        r = Rule("/price/<float:amount>", endpoint="price")
        result = r.match("/price/3.14")
        assert result["amount"] == pytest.approx(3.14)

    def test_match_multiple(self):
        r = Rule("/user/<name>/post/<int:post_id>", endpoint="post")
        result = r.match("/user/john/post/5")
        assert result == {"name": "john", "post_id": 5}

    def test_match_no_match(self):
        r = Rule("/hello", endpoint="hello")
        result = r.match("/goodbye")
        assert result is None

    def test_match_path(self):
        r = Rule("/files/<path:filepath>", endpoint="files")
        result = r.match("/files/a/b/c.txt")
        assert result == {"filepath": "a/b/c.txt"}

    def test_match_static_no_partial(self):
        r = Rule("/hello", endpoint="hello")
        assert r.match("/hello/world") is None

    def test_match_trailing_slash_strict(self):
        r = Rule("/hello", endpoint="hello", strict_slashes=True)
        assert r.match("/hello") == {}
        assert r.match("/hello/") is None

    def test_match_trailing_slash_lax(self):
        r = Rule("/hello", endpoint="hello", strict_slashes=False)
        assert r.match("/hello") == {}
        assert r.match("/hello/") == {}
