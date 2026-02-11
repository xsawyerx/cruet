"""Tests for cookie-based session support."""
import pytest
from cruet import Cruet, session
from cruet.sessions import Session, _encode_session, _decode_session


class TestSessionClass:
    def test_session_is_dict(self):
        s = Session()
        assert isinstance(s, dict)

    def test_session_new_flag(self):
        s = Session()
        assert s.new is True

    def test_session_from_data_not_new(self):
        s = Session({"user": "alice"})
        assert s.new is False
        assert s["user"] == "alice"

    def test_session_modified_on_setitem(self):
        s = Session()
        assert s.modified is False
        s["key"] = "value"
        assert s.modified is True

    def test_session_modified_on_delitem(self):
        s = Session({"key": "value"})
        s.modified = False
        del s["key"]
        assert s.modified is True

    def test_session_modified_on_pop(self):
        s = Session({"key": "value"})
        s.modified = False
        s.pop("key")
        assert s.modified is True

    def test_session_modified_on_update(self):
        s = Session()
        s.update({"a": 1})
        assert s.modified is True

    def test_session_modified_on_setdefault(self):
        s = Session()
        s.setdefault("x", 10)
        assert s.modified is True

    def test_session_setdefault_existing_not_modified(self):
        s = Session({"x": 10})
        s.modified = False
        s.setdefault("x", 20)
        assert s.modified is False
        assert s["x"] == 10

    def test_session_modified_on_clear(self):
        s = Session({"a": 1})
        s.modified = False
        s.clear()
        assert s.modified is True
        assert len(s) == 0

    def test_session_permanent_default_false(self):
        s = Session()
        assert s.permanent is False


class TestSessionEncoding:
    SECRET = "test-secret-key"

    def test_encode_decode_roundtrip(self):
        data = {"user": "alice", "role": "admin"}
        encoded = _encode_session(data, self.SECRET)
        decoded = _decode_session(encoded, self.SECRET)
        assert decoded == data

    def test_encode_produces_string(self):
        encoded = _encode_session({"x": 1}, self.SECRET)
        assert isinstance(encoded, str)
        assert "." in encoded

    def test_decode_tampered_signature(self):
        encoded = _encode_session({"x": 1}, self.SECRET)
        tampered = encoded[:-4] + "XXXX"
        assert _decode_session(tampered, self.SECRET) is None

    def test_decode_wrong_secret(self):
        encoded = _encode_session({"x": 1}, self.SECRET)
        assert _decode_session(encoded, "wrong-secret") is None

    def test_decode_garbage(self):
        assert _decode_session("not.valid.at.all", self.SECRET) is None
        assert _decode_session("", self.SECRET) is None
        assert _decode_session(None, self.SECRET) is None

    def test_decode_no_dot(self):
        assert _decode_session("nodothere", self.SECRET) is None

    def test_encode_empty_dict(self):
        encoded = _encode_session({}, self.SECRET)
        decoded = _decode_session(encoded, self.SECRET)
        assert decoded == {}

    def test_encode_nested_data(self):
        data = {"items": [1, 2, 3], "meta": {"count": 3}}
        encoded = _encode_session(data, self.SECRET)
        decoded = _decode_session(encoded, self.SECRET)
        assert decoded == data

    def test_encode_bytes_secret(self):
        data = {"key": "val"}
        encoded = _encode_session(data, b"bytes-secret")
        decoded = _decode_session(encoded, b"bytes-secret")
        assert decoded == data


class TestSessionIntegration:
    def _make_app(self):
        app = Cruet(__name__)
        app.secret_key = "integration-test-secret"
        return app

    def test_session_available_in_view(self):
        app = self._make_app()

        @app.route("/set")
        def set_session():
            session["user"] = "alice"
            return "ok"

        client = app.test_client()
        resp = client.get("/set")
        assert resp.status_code == 200
        # Response should have a Set-Cookie header
        cookie = resp.get_header("Set-Cookie")
        assert cookie is not None
        assert "session=" in cookie

    def test_session_read_after_write(self):
        app = self._make_app()

        @app.route("/set")
        def set_val():
            session["color"] = "blue"
            return "set"

        @app.route("/get")
        def get_val():
            return session.get("color", "none")

        client = app.test_client()

        # Set session
        resp1 = client.get("/set")
        cookie_header = resp1.get_header("Set-Cookie")
        assert cookie_header is not None

        # Extract cookie value
        cookie_val = cookie_header.split(";")[0]  # "session=..."

        # Read session back
        resp2 = client.get("/get", headers={"Cookie": cookie_val})
        assert resp2.text == "blue"

    def test_session_empty_without_secret(self):
        app = Cruet(__name__)
        # No secret_key set — NullSession raises on mutation

        @app.route("/check")
        def check():
            # NullSession allows reads but not writes
            val = session.get("x")
            return f"val={val}"

        client = app.test_client()
        resp = client.get("/check")
        assert resp.status_code == 200
        # No Set-Cookie header since no secret key
        cookie = resp.get_header("Set-Cookie")
        assert cookie is None

    def test_session_tampered_cookie_ignored(self):
        app = self._make_app()

        @app.route("/read")
        def read():
            return session.get("user", "anonymous")

        client = app.test_client()
        resp = client.get("/read", headers={"Cookie": "session=tampered.garbage"})
        assert resp.text == "anonymous"

    def test_session_multiple_values(self):
        app = self._make_app()

        @app.route("/set")
        def set_multi():
            session["a"] = 1
            session["b"] = "two"
            session["c"] = [3, 4, 5]
            return "ok"

        @app.route("/get")
        def get_multi():
            import json
            return json.dumps({
                "a": session.get("a"),
                "b": session.get("b"),
                "c": session.get("c"),
            })

        client = app.test_client()
        resp1 = client.get("/set")
        cookie_val = resp1.get_header("Set-Cookie").split(";")[0]

        resp2 = client.get("/get", headers={"Cookie": cookie_val})
        data = resp2.json
        assert data["a"] == 1
        assert data["b"] == "two"
        assert data["c"] == [3, 4, 5]

    def test_session_not_modified_no_cookie(self):
        app = self._make_app()

        @app.route("/noop")
        def noop():
            # Access session but don't modify it
            _ = session.get("nonexistent", "default")
            return "ok"

        client = app.test_client()
        resp = client.get("/noop")
        # Should not set a cookie since session wasn't modified
        assert resp.get_header("Set-Cookie") is None

    def test_session_delete_value(self):
        app = self._make_app()

        @app.route("/set")
        def set_val():
            session["user"] = "alice"
            return "ok"

        @app.route("/delete")
        def del_val():
            session.pop("user", None)
            return "deleted"

        @app.route("/check")
        def check():
            return session.get("user", "gone")

        client = app.test_client()

        # Set
        resp1 = client.get("/set")
        cookie_val = resp1.get_header("Set-Cookie").split(";")[0]

        # Delete
        resp2 = client.get("/delete", headers={"Cookie": cookie_val})
        cookie_val2 = resp2.get_header("Set-Cookie").split(";")[0]

        # Check
        resp3 = client.get("/check", headers={"Cookie": cookie_val2})
        assert resp3.text == "gone"

    def test_session_clear_deletes_cookie(self):
        app = self._make_app()

        @app.route("/clear")
        def clear_session():
            session.clear()
            return "cleared"

        client = app.test_client()
        # Send a request with a session cookie, then clear it
        resp = client.get("/clear", headers={"Cookie": "session=something.fake"})
        cookie = resp.get_header("Set-Cookie")
        # Session was cleared (modified=True, but empty) — should delete cookie
        if cookie:
            assert "Max-Age=0" in cookie or "expires=" in cookie.lower()

    def test_session_permanent_sets_max_age(self):
        app = self._make_app()
        app.config["PERMANENT_SESSION_LIFETIME"] = 3600

        @app.route("/perm")
        def perm():
            session.permanent = True
            session["logged_in"] = True
            return "ok"

        client = app.test_client()
        resp = client.get("/perm")
        cookie = resp.get_header("Set-Cookie")
        assert cookie is not None
        assert "Max-Age=3600" in cookie

    def test_session_httponly_default(self):
        app = self._make_app()

        @app.route("/set")
        def set_val():
            session["x"] = 1
            return "ok"

        client = app.test_client()
        resp = client.get("/set")
        cookie = resp.get_header("Set-Cookie")
        assert "HttpOnly" in cookie

    def test_session_custom_cookie_name(self):
        app = self._make_app()
        app.config["SESSION_COOKIE_NAME"] = "my_sess"

        @app.route("/set")
        def set_val():
            session["x"] = 1
            return "ok"

        @app.route("/get")
        def get_val():
            return str(session.get("x", "none"))

        client = app.test_client()
        resp1 = client.get("/set")
        cookie = resp1.get_header("Set-Cookie")
        assert "my_sess=" in cookie

        cookie_val = cookie.split(";")[0]  # "my_sess=..."
        resp2 = client.get("/get", headers={"Cookie": cookie_val})
        assert resp2.text == "1"

    def test_session_proxy_getitem(self):
        app = self._make_app()

        @app.route("/test")
        def test_view():
            session["key"] = "value"
            return session["key"]

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "value"

    def test_session_proxy_contains(self):
        app = self._make_app()

        @app.route("/test")
        def test_view():
            session["present"] = True
            result = "present" in session and "absent" not in session
            return str(result)

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "True"

    def test_session_proxy_len(self):
        app = self._make_app()

        @app.route("/test")
        def test_view():
            session["a"] = 1
            session["b"] = 2
            return str(len(session))

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "2"
