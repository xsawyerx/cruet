"""Tests for Priority 7: Request/Response API completeness."""
import io
import json
import pytest

from cruet import Cruet, request
from cruet._cruet import CRequest, CResponse


def _make_request(**overrides):
    """Helper to build a CRequest with a test environ."""
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "HTTP_HOST": "localhost",
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(b""),
    }
    environ.update(overrides)
    return CRequest(environ)


class TestRequestGetJson:
    def test_get_json_basic(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_TYPE="application/json",
            CONTENT_LENGTH="13",
            **{"wsgi.input": io.BytesIO(b'{"a": "b"}'[:13])}
        )
        # Use raw body
        r2 = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_TYPE="application/json",
            **{"wsgi.input": io.BytesIO(b'{"a": "b"}'),
               "CONTENT_LENGTH": "11"}
        )
        result = r2.get_json()
        assert result == {"a": "b"}

    def test_get_json_force(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_TYPE="text/plain",
            CONTENT_LENGTH="11",
            **{"wsgi.input": io.BytesIO(b'{"a": "b"}')}
        )
        assert r.json is None  # no json content type
        result = r.get_json(force=True)
        assert result == {"a": "b"}

    def test_get_json_silent(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_TYPE="application/json",
            CONTENT_LENGTH="7",
            **{"wsgi.input": io.BytesIO(b"invalid")}
        )
        result = r.get_json(silent=True)
        assert result is None

    def test_get_json_silent_false_raises(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_TYPE="application/json",
            CONTENT_LENGTH="7",
            **{"wsgi.input": io.BytesIO(b"invalid")}
        )
        with pytest.raises(Exception):
            r.get_json(silent=False)


class TestRequestGetData:
    def test_get_data_bytes(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_LENGTH="5",
            **{"wsgi.input": io.BytesIO(b"hello")}
        )
        assert r.get_data() == b"hello"

    def test_get_data_as_text(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_LENGTH="5",
            **{"wsgi.input": io.BytesIO(b"hello")}
        )
        assert r.get_data(as_text=True) == "hello"


class TestRequestValues:
    def test_values_from_args(self):
        r = _make_request(QUERY_STRING="a=1&b=2")
        assert r.values.get("a") == "1"
        assert r.values.get("b") == "2"

    def test_values_from_form(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            CONTENT_TYPE="application/x-www-form-urlencoded",
            CONTENT_LENGTH="7",
            **{"wsgi.input": io.BytesIO(b"c=3&d=4")}
        )
        assert r.values.get("c") == "3"
        assert r.values.get("d") == "4"

    def test_values_combined(self):
        r = _make_request(
            REQUEST_METHOD="POST",
            QUERY_STRING="a=1",
            CONTENT_TYPE="application/x-www-form-urlencoded",
            CONTENT_LENGTH="3",
            **{"wsgi.input": io.BytesIO(b"b=2")}
        )
        assert r.values.get("a") == "1"
        assert r.values.get("b") == "2"


class TestRequestFullPath:
    def test_full_path_with_query(self):
        r = _make_request(PATH_INFO="/search", QUERY_STRING="q=hello")
        assert r.full_path == "/search?q=hello"

    def test_full_path_without_query(self):
        r = _make_request(PATH_INFO="/index")
        # Flask includes trailing ? even with empty query string
        assert r.full_path == "/index?"


class TestRequestScheme:
    def test_scheme_http(self):
        r = _make_request()
        assert r.scheme == "http"

    def test_scheme_https(self):
        r = _make_request(**{"wsgi.url_scheme": "https"})
        assert r.scheme == "https"

    def test_is_secure_false(self):
        r = _make_request()
        assert r.is_secure is False

    def test_is_secure_true(self):
        r = _make_request(**{"wsgi.url_scheme": "https"})
        assert r.is_secure is True


class TestRequestAccessRoute:
    def test_access_route_single(self):
        r = _make_request(REMOTE_ADDR="10.0.0.1")
        assert r.access_route == ["10.0.0.1"]

    def test_access_route_xff(self):
        r = _make_request(
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8"
        )
        assert r.access_route == ["1.2.3.4", "5.6.7.8", "10.0.0.1"]

    def test_access_route_empty(self):
        r = _make_request()
        # No REMOTE_ADDR set, but default is ""
        assert isinstance(r.access_route, list)


class TestRequestReferrerUserAgent:
    def test_referrer(self):
        r = _make_request(HTTP_REFERER="http://example.com/page")
        assert r.referrer == "http://example.com/page"

    def test_referrer_none(self):
        r = _make_request()
        assert r.referrer is None

    def test_user_agent(self):
        r = _make_request(HTTP_USER_AGENT="Mozilla/5.0")
        assert r.user_agent == "Mozilla/5.0"

    def test_user_agent_empty(self):
        r = _make_request()
        assert r.user_agent == ""


class TestRequestInView:
    def test_full_path_in_view(self):
        app = Cruet(__name__)

        @app.route("/search")
        def search():
            return request.full_path

        resp = app.test_client().get("/search", query_string="q=test")
        assert resp.text == "/search?q=test"

    def test_values_in_view(self):
        app = Cruet(__name__)

        @app.route("/form")
        def form():
            return request.values.get("x", "missing")

        resp = app.test_client().get("/form", query_string="x=found")
        assert resp.text == "found"

    def test_get_json_in_view(self):
        app = Cruet(__name__)

        @app.post("/api")
        def api():
            data = request.get_json(force=True)
            return str(data.get("key"))

        resp = app.test_client().post(
            "/api",
            data=b'{"key": "val"}',
            content_type="application/json",
        )
        assert resp.text == "val"


class TestResponseStatusCodeSetter:
    def test_set_status_code(self):
        r = CResponse("ok")
        assert r.status_code == 200
        r.status_code = 404
        assert r.status_code == 404
        assert "404" in r.status

    def test_set_status_string(self):
        r = CResponse("ok")
        r.status = "418 I'm a Teapot"
        assert r.status_code == 418
        assert r.status == "418 I'm a Teapot"


class TestResponseDataSetter:
    def test_set_data_bytes(self):
        r = CResponse("original")
        r.data = b"new body"
        assert r.data == b"new body"
        assert r.content_length == 8

    def test_set_data_str(self):
        r = CResponse("original")
        r.data = "string body"
        assert r.data == b"string body"

    def test_content_length_updates(self):
        r = CResponse("short")
        original_len = r.content_length
        r.data = b"a much longer body than before"
        assert r.content_length == len(b"a much longer body than before")
        assert r.content_length != original_len


class TestResponseGetData:
    def test_get_data_bytes(self):
        r = CResponse("hello")
        assert r.get_data() == b"hello"

    def test_get_data_as_text(self):
        r = CResponse("hello")
        assert r.get_data(as_text=True) == "hello"


class TestResponseJson:
    def test_json_property(self):
        r = CResponse('{"a": 1}', content_type="application/json")
        assert r.json == {"a": 1}

    def test_get_json_method(self):
        r = CResponse('{"b": 2}', content_type="application/json")
        assert r.get_json() == {"b": 2}

    def test_is_json_true(self):
        r = CResponse("{}", content_type="application/json")
        assert r.is_json is True

    def test_is_json_false(self):
        r = CResponse("text", content_type="text/plain")
        assert r.is_json is False


class TestResponseMimetype:
    def test_mimetype_simple(self):
        r = CResponse("ok", content_type="text/html")
        assert r.mimetype == "text/html"

    def test_mimetype_with_charset(self):
        r = CResponse("ok", content_type="text/html; charset=utf-8")
        assert r.mimetype == "text/html"


class TestResponseLocation:
    def test_location_get_set(self):
        r = CResponse("redirect", status=302)
        r.location = "/new-url"
        assert r.location == "/new-url"

    def test_location_none_by_default(self):
        r = CResponse("ok")
        assert r.location is None

    def test_location_in_after_request(self):
        app = Cruet(__name__)

        @app.after_request
        def add_location(response):
            response.status_code = 302
            response.location = "/moved"
            return response

        @app.route("/")
        def index():
            return "ok"

        resp = app.test_client().get("/")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/moved"


class TestResponseMutabilityInMiddleware:
    def test_modify_status_in_after_request(self):
        app = Cruet(__name__)

        @app.after_request
        def force_200(response):
            response.status_code = 200
            return response

        @app.route("/")
        def index():
            return "ok", 201

        resp = app.test_client().get("/")
        assert resp.status_code == 200

    def test_modify_body_in_after_request(self):
        app = Cruet(__name__)

        @app.after_request
        def wrap_body(response):
            response.data = b"[" + response.data + b"]"
            return response

        @app.route("/")
        def index():
            return "content"

        resp = app.test_client().get("/")
        assert resp.text == "[content]"
