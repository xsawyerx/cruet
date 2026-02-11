"""Tests for CRequest — WSGI request wrapper."""
import io
import json
import pytest
from cruet._cruet import CRequest
from tests.conftest import make_environ


class TestRequestBasicProperties:
    def test_method_get(self):
        req = CRequest(make_environ(method="GET"))
        assert req.method == "GET"

    def test_method_post(self):
        req = CRequest(make_environ(method="POST"))
        assert req.method == "POST"

    def test_method_put(self):
        req = CRequest(make_environ(method="PUT"))
        assert req.method == "PUT"

    def test_method_delete(self):
        req = CRequest(make_environ(method="DELETE"))
        assert req.method == "DELETE"

    def test_path(self):
        req = CRequest(make_environ(path="/hello/world"))
        assert req.path == "/hello/world"

    def test_path_root(self):
        req = CRequest(make_environ(path="/"))
        assert req.path == "/"

    def test_query_string(self):
        req = CRequest(make_environ(query_string="a=1&b=2"))
        assert req.query_string == "a=1&b=2"

    def test_query_string_empty(self):
        req = CRequest(make_environ(query_string=""))
        assert req.query_string == ""


class TestRequestHeaders:
    def test_host_header(self):
        req = CRequest(make_environ(host="example.com"))
        assert req.headers.get("Host") == "example.com"

    def test_custom_header(self):
        req = CRequest(make_environ(headers={"X-Request-Id": "abc123"}))
        assert req.headers.get("X-Request-Id") == "abc123"

    def test_content_type_header(self):
        req = CRequest(make_environ(content_type="application/json"))
        assert req.headers.get("Content-Type") == "application/json"

    def test_multiple_headers(self):
        hdrs = {"Accept": "text/html", "Accept-Language": "en-US"}
        req = CRequest(make_environ(headers=hdrs))
        assert req.headers.get("Accept") == "text/html"
        assert req.headers.get("Accept-Language") == "en-US"


class TestRequestContentType:
    def test_content_type(self):
        req = CRequest(make_environ(content_type="text/html"))
        assert req.content_type == "text/html"

    def test_content_type_with_charset(self):
        req = CRequest(make_environ(content_type="text/html; charset=utf-8"))
        assert "text/html" in req.content_type

    def test_content_type_empty(self):
        req = CRequest(make_environ())
        assert req.content_type == "" or req.content_type is None


class TestRequestArgs:
    def test_args_parsed(self):
        req = CRequest(make_environ(query_string="a=1&b=2"))
        args = req.args
        assert args["a"] == "1"
        assert args["b"] == "2"
        assert args.getlist("a") == ["1"]
        assert args.getlist("b") == ["2"]

    def test_args_multi_value(self):
        req = CRequest(make_environ(query_string="x=1&x=2&x=3"))
        args = req.args
        assert args["x"] == "1"  # first value
        assert args.getlist("x") == ["1", "2", "3"]

    def test_args_empty(self):
        req = CRequest(make_environ(query_string=""))
        args = req.args
        assert args == {}

    def test_args_lazy(self):
        """Accessing .args multiple times returns the same result."""
        req = CRequest(make_environ(query_string="key=val"))
        args1 = req.args
        args2 = req.args
        assert args1 == args2

    def test_args_url_decoded(self):
        req = CRequest(make_environ(query_string="name=hello%20world"))
        assert req.args["name"] == "hello world"
        assert req.args.getlist("name") == ["hello world"]


class TestRequestData:
    def test_data_bytes(self):
        body = b"raw body content"
        req = CRequest(make_environ(body=body, content_type="application/octet-stream"))
        assert req.data == body

    def test_data_empty(self):
        req = CRequest(make_environ())
        assert req.data == b""

    def test_data_post_body(self):
        body = b"some data here"
        req = CRequest(make_environ(method="POST", body=body,
                                    content_type="text/plain"))
        assert req.data == body


class TestRequestJson:
    def test_json_valid(self):
        payload = {"key": "value", "num": 42}
        body = json.dumps(payload).encode("utf-8")
        req = CRequest(make_environ(method="POST", body=body,
                                    content_type="application/json"))
        assert req.json == payload

    def test_json_nested(self):
        payload = {"users": [{"name": "alice"}, {"name": "bob"}]}
        body = json.dumps(payload).encode("utf-8")
        req = CRequest(make_environ(method="POST", body=body,
                                    content_type="application/json"))
        assert req.json == payload

    def test_json_none_when_not_json_content_type(self):
        body = b'{"key": "value"}'
        req = CRequest(make_environ(method="POST", body=body,
                                    content_type="text/plain"))
        assert req.json is None

    def test_json_none_when_empty_body(self):
        req = CRequest(make_environ(content_type="application/json"))
        assert req.json is None

    def test_json_invalid_raises(self):
        body = b"not valid json {"
        req = CRequest(make_environ(method="POST", body=body,
                                    content_type="application/json"))
        with pytest.raises((ValueError, Exception)):
            _ = req.json


class TestRequestForm:
    def test_form_urlencoded(self):
        body = b"username=alice&password=secret"
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/x-www-form-urlencoded"))
        form = req.form
        assert form["username"] == "alice"
        assert form["password"] == "secret"
        assert form.getlist("username") == ["alice"]

    def test_form_urlencoded_multi_value(self):
        body = b"item=a&item=b&item=c"
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/x-www-form-urlencoded"))
        form = req.form
        assert form["item"] == "a"  # first value
        assert form.getlist("item") == ["a", "b", "c"]

    def test_form_empty_when_not_urlencoded(self):
        body = b"username=alice"
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="text/plain"))
        form = req.form
        assert form == {}

    def test_form_url_decoded_values(self):
        body = b"name=hello%20world"
        req = CRequest(make_environ(
            method="POST", body=body,
            content_type="application/x-www-form-urlencoded"))
        form = req.form
        assert form["name"] == "hello world"
        assert form.getlist("name") == ["hello world"]


class TestRequestHost:
    def test_host_default(self):
        req = CRequest(make_environ(host="localhost"))
        assert req.host == "localhost"

    def test_host_with_port(self):
        req = CRequest(make_environ(host="example.com", port=8080))
        assert "example.com" in req.host

    def test_host_from_header(self):
        req = CRequest(make_environ(host="example.com"))
        assert "example.com" in req.host


class TestRequestUrl:
    def test_url(self):
        req = CRequest(make_environ(
            host="example.com", path="/hello", query_string="a=1"))
        url = req.url
        assert "example.com" in url
        assert "/hello" in url
        assert "a=1" in url

    def test_url_scheme(self):
        req = CRequest(make_environ(scheme="https", host="example.com",
                                    path="/secure"))
        assert req.url.startswith("https://")

    def test_base_url(self):
        req = CRequest(make_environ(
            host="example.com", path="/hello", query_string="a=1"))
        base = req.base_url
        assert "example.com" in base
        assert "/hello" in base
        assert "a=1" not in base

    def test_url_no_query_string(self):
        req = CRequest(make_environ(host="example.com", path="/page"))
        url = req.url
        assert "?" not in url or url.endswith("?") is False


class TestRequestIsJson:
    def test_is_json_true(self):
        req = CRequest(make_environ(content_type="application/json"))
        assert req.is_json is True

    def test_is_json_with_charset(self):
        req = CRequest(make_environ(
            content_type="application/json; charset=utf-8"))
        assert req.is_json is True

    def test_is_json_false(self):
        req = CRequest(make_environ(content_type="text/html"))
        assert req.is_json is False

    def test_is_json_no_content_type(self):
        req = CRequest(make_environ())
        assert req.is_json is False

    def test_is_json_vendor_type(self):
        """application/vnd.api+json should also be considered JSON."""
        req = CRequest(make_environ(
            content_type="application/vnd.api+json"))
        assert req.is_json is True


class TestRequestFromRawEnviron:
    """Test with manually constructed environ dicts to cover edge cases."""

    def test_minimal_environ(self):
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/",
            "QUERY_STRING": "",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "80",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(b""),
            "wsgi.errors": io.BytesIO(),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "SCRIPT_NAME": "",
        }
        req = CRequest(environ)
        assert req.method == "GET"
        assert req.path == "/"

    def test_script_name_prefix(self):
        environ = make_environ(path="/app/hello")
        environ["SCRIPT_NAME"] = "/app"
        environ["PATH_INFO"] = "/hello"
        req = CRequest(environ)
        assert req.path == "/hello"


class TestRequestCookies:
    def test_cookies_parsed(self):
        req = CRequest(make_environ(headers={"Cookie": "session=abc123; theme=dark"}))
        assert req.cookies["session"] == "abc123"
        assert req.cookies["theme"] == "dark"

    def test_cookies_single(self):
        req = CRequest(make_environ(headers={"Cookie": "token=xyz"}))
        assert req.cookies["token"] == "xyz"

    def test_cookies_empty(self):
        req = CRequest(make_environ())
        assert req.cookies == {}

    def test_cookies_no_cookie_header(self):
        req = CRequest(make_environ())
        cookies = req.cookies
        assert isinstance(cookies, dict)
        assert len(cookies) == 0

    def test_cookies_lazy_cached(self):
        req = CRequest(make_environ(headers={"Cookie": "a=1"}))
        c1 = req.cookies
        c2 = req.cookies
        assert c1 is c2

    def test_cookies_with_spaces(self):
        req = CRequest(make_environ(headers={"Cookie": "name=hello world"}))
        assert req.cookies["name"] == "hello world"

    def test_cookies_quoted_value(self):
        req = CRequest(make_environ(headers={"Cookie": 'val="quoted"'}))
        assert "quoted" in req.cookies["val"]


class TestRequestFiles:
    def _multipart_environ(self, boundary, body):
        return make_environ(
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def test_files_single_upload(self):
        boundary = "----TestBoundary"
        body = (
            f"------TestBoundary\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"test.txt\"\r\n"
            f"Content-Type: text/plain\r\n"
            f"\r\n"
            f"file content here\r\n"
            f"------TestBoundary--\r\n"
        ).encode()
        req = CRequest(self._multipart_environ(boundary, body))
        files = req.files
        assert "file" in files
        assert files["file"]["filename"] == "test.txt"
        assert files["file"]["content_type"] == "text/plain"
        assert files["file"]["data"] == b"file content here"

    def test_files_empty_when_not_multipart(self):
        req = CRequest(make_environ(
            method="POST", body=b"data",
            content_type="application/x-www-form-urlencoded"))
        assert req.files == {}

    def test_files_empty_when_no_body(self):
        req = CRequest(make_environ(content_type="multipart/form-data; boundary=xxx"))
        assert req.files == {}

    def test_files_lazy_cached(self):
        req = CRequest(make_environ(content_type="text/plain"))
        f1 = req.files
        f2 = req.files
        assert f1 is f2

    def test_files_multiple_uploads(self):
        boundary = "----Multi"
        body = (
            f"------Multi\r\n"
            f"Content-Disposition: form-data; name=\"a\"; filename=\"a.txt\"\r\n"
            f"Content-Type: text/plain\r\n"
            f"\r\n"
            f"aaa\r\n"
            f"------Multi\r\n"
            f"Content-Disposition: form-data; name=\"b\"; filename=\"b.bin\"\r\n"
            f"Content-Type: application/octet-stream\r\n"
            f"\r\n"
            f"bbb\r\n"
            f"------Multi--\r\n"
        ).encode()
        req = CRequest(self._multipart_environ(boundary, body))
        assert "a" in req.files
        assert "b" in req.files
        assert req.files["a"]["filename"] == "a.txt"
        assert req.files["b"]["filename"] == "b.bin"


class TestRequestRemoteAddr:
    def test_remote_addr(self):
        env = make_environ()
        env["REMOTE_ADDR"] = "192.168.1.100"
        req = CRequest(env)
        assert req.remote_addr == "192.168.1.100"

    def test_remote_addr_missing(self):
        req = CRequest(make_environ())
        assert req.remote_addr == ""

    def test_remote_addr_ipv6(self):
        env = make_environ()
        env["REMOTE_ADDR"] = "::1"
        req = CRequest(env)
        assert req.remote_addr == "::1"


class TestRequestEnviron:
    def test_environ_exposed(self):
        env = make_environ(method="POST", path="/test")
        req = CRequest(env)
        assert req.environ is env

    def test_environ_has_wsgi_keys(self):
        req = CRequest(make_environ())
        assert "wsgi.version" in req.environ
        assert "REQUEST_METHOD" in req.environ

    def test_environ_is_dict(self):
        req = CRequest(make_environ())
        assert isinstance(req.environ, dict)


class TestRequestContentLength:
    def test_content_length_present(self):
        env = make_environ(body=b"hello")
        req = CRequest(env)
        assert req.content_length == 5

    def test_content_length_missing(self):
        req = CRequest(make_environ())
        assert req.content_length is None

    def test_content_length_zero(self):
        env = make_environ()
        env["CONTENT_LENGTH"] = "0"
        req = CRequest(env)
        assert req.content_length == 0

    def test_content_length_invalid(self):
        env = make_environ()
        env["CONTENT_LENGTH"] = "not-a-number"
        req = CRequest(env)
        assert req.content_length is None

    def test_content_length_large(self):
        env = make_environ()
        env["CONTENT_LENGTH"] = "1048576"
        req = CRequest(env)
        assert req.content_length == 1048576


class TestRequestMimetype:
    def test_mimetype_simple(self):
        req = CRequest(make_environ(content_type="application/json"))
        assert req.mimetype == "application/json"

    def test_mimetype_with_charset(self):
        req = CRequest(make_environ(content_type="text/html; charset=utf-8"))
        assert req.mimetype == "text/html"

    def test_mimetype_with_multiple_params(self):
        req = CRequest(make_environ(
            content_type="multipart/form-data; boundary=abc; charset=utf-8"))
        assert req.mimetype == "multipart/form-data"

    def test_mimetype_empty(self):
        req = CRequest(make_environ())
        assert req.mimetype == ""

    def test_mimetype_no_params(self):
        req = CRequest(make_environ(content_type="text/plain"))
        assert req.mimetype == "text/plain"
