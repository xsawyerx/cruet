"""Tests for the libevent2-based async WSGI server."""
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import pytest
from cruet import Cruet

# Check if libevent is available
try:
    from cruet._cruet import run_event_loop
    HAS_LIBEVENT = True
except ImportError:
    HAS_LIBEVENT = False

pytestmark = pytest.mark.skipif(
    not HAS_LIBEVENT, reason="libevent2 not available"
)


@pytest.fixture
def app():
    app = Cruet(__name__)

    @app.route("/")
    def index():
        return "Hello from async cruet!"

    @app.route("/json")
    def json_view():
        return {"status": "ok", "server": "async"}

    @app.route("/echo", methods=["POST"])
    def echo():
        from cruet.globals import request
        return request.data.decode("utf-8", errors="replace")

    @app.route("/user/<name>")
    def user(name):
        return f"Hello, {name}!"

    return app


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def async_server(app):
    """Start async server in a background process on a random port."""
    port = _find_free_port()

    pid = os.fork()
    if pid == 0:
        # Child: run the event loop
        try:
            run_event_loop(
                app,
                host="127.0.0.1",
                port=port,
                backlog=128,
                read_timeout=5,
                write_timeout=5,
                max_request_size=1048576,
            )
        except Exception:
            pass
        os._exit(0)

    # Parent: wait for server to be ready
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.05)
    else:
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)
        pytest.skip("Async server did not start in time")

    yield port

    # Cleanup
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


def _http_get(port, path="/", headers=None):
    """Send an HTTP GET request and return the raw response."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    req = f"GET {path} HTTP/1.1\r\nHost: localhost\r\n"
    if headers:
        for k, v in headers.items():
            req += f"{k}: {v}\r\n"
    req += "\r\n"
    sock.sendall(req.encode())
    response = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\r\n\r\n" in response:
                # Check if we have Content-Length
                header_part = response.split(b"\r\n\r\n", 1)[0]
                body_part = response.split(b"\r\n\r\n", 1)[1]
                for line in header_part.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        cl = int(line.split(b":")[1].strip())
                        if len(body_part) >= cl:
                            sock.close()
                            return response
                # No content-length, try connection close
                break
        except socket.timeout:
            break
    sock.close()
    return response


def _http_post(port, path, body, content_type="text/plain"):
    """Send an HTTP POST request and return the raw response."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    if isinstance(body, str):
        body = body.encode()
    req = (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
    ).encode() + body
    sock.sendall(req)
    response = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\r\n\r\n" in response:
                header_part = response.split(b"\r\n\r\n", 1)[0]
                body_part = response.split(b"\r\n\r\n", 1)[1]
                for line in header_part.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        cl = int(line.split(b":")[1].strip())
                        if len(body_part) >= cl:
                            sock.close()
                            return response
                break
        except socket.timeout:
            break
    sock.close()
    return response


class TestBasicRequests:
    def test_single_get(self, async_server):
        """Single GET request returns 200 + correct body."""
        response = _http_get(async_server, "/")
        assert b"200 OK" in response
        assert b"Hello from async cruet!" in response

    def test_post_with_body(self, async_server):
        """POST with body echoes it back."""
        response = _http_post(async_server, "/echo", "test body data")
        assert b"200 OK" in response
        assert b"test body data" in response

    def test_json_round_trip(self, async_server):
        """JSON request/response round-trip."""
        response = _http_get(async_server, "/json")
        assert b"200 OK" in response
        assert b'"status"' in response
        assert b'"async"' in response

    def test_404_for_unknown_path(self, async_server):
        """Unknown path returns 404."""
        response = _http_get(async_server, "/nonexistent")
        assert b"404" in response

    def test_url_variable(self, async_server):
        """Route with URL variable."""
        response = _http_get(async_server, "/user/john")
        assert b"200 OK" in response
        assert b"Hello, john!" in response


class TestMultipleRequests:
    def test_sequential_requests(self, async_server):
        """Multiple sequential requests on separate connections."""
        for i in range(5):
            response = _http_get(async_server, "/")
            assert b"200 OK" in response

    def test_keep_alive(self, async_server):
        """Two requests on the same TCP socket (keep-alive)."""
        sock = socket.create_connection(("127.0.0.1", async_server), timeout=5)

        # First request
        sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        time.sleep(0.1)
        resp1 = sock.recv(4096)
        assert b"200 OK" in resp1
        assert b"Hello from async cruet!" in resp1

        # Second request on same socket
        sock.sendall(b"GET /json HTTP/1.1\r\nHost: localhost\r\n\r\n")
        time.sleep(0.1)
        resp2 = sock.recv(4096)
        assert b"200 OK" in resp2
        assert b'"status"' in resp2

        sock.close()

    def test_connection_close(self, async_server):
        """Connection: close header should be respected."""
        response = _http_get(async_server, "/",
                             headers={"Connection": "close"})
        assert b"200 OK" in response


class TestConcurrency:
    def test_concurrent_requests(self, async_server):
        """20 concurrent requests should all succeed."""
        results = [None] * 20

        def make_request(idx):
            try:
                results[idx] = _http_get(async_server, "/")
            except Exception as e:
                results[idx] = str(e).encode()

        threads = [threading.Thread(target=make_request, args=(i,))
                   for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        success = sum(1 for r in results if r and b"200 OK" in r)
        assert success >= 18, f"Only {success}/20 succeeded"


class TestErrorHandling:
    def test_malformed_request(self, async_server):
        """Malformed request should get 400."""
        sock = socket.create_connection(("127.0.0.1", async_server), timeout=5)
        sock.sendall(b"NOT_HTTP garbage\r\n\r\n")
        time.sleep(0.2)
        try:
            response = sock.recv(4096)
            if response:
                assert b"400" in response or b"500" in response
        except (socket.timeout, ConnectionResetError):
            pass  # Server may just close connection
        sock.close()

    def test_request_exceeding_max_size(self, async_server):
        """Request exceeding max_request_size should get 413."""
        sock = socket.create_connection(("127.0.0.1", async_server), timeout=5)
        # Send a very large header that exceeds 1MB
        huge_header = "X-Big: " + "x" * 1_100_000 + "\r\n"
        request = f"GET / HTTP/1.1\r\nHost: localhost\r\n{huge_header}\r\n"
        try:
            sock.sendall(request.encode())
            time.sleep(0.5)
            response = sock.recv(4096)
            if response:
                assert b"413" in response
        except (BrokenPipeError, ConnectionResetError):
            pass  # Server may close before we finish sending
        sock.close()


class TestGracefulShutdown:
    def test_sigterm_clean_exit(self):
        """Sending SIGTERM should result in clean exit."""
        app = Cruet(__name__)

        @app.route("/")
        def index():
            return "ok"

        port = _find_free_port()
        pid = os.fork()
        if pid == 0:
            try:
                run_event_loop(app, host="127.0.0.1", port=port,
                               read_timeout=5, write_timeout=5)
            except Exception:
                pass
            os._exit(0)

        # Wait for server to start
        deadline = time.time() + 5
        started = False
        while time.time() < deadline:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                s.close()
                started = True
                break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.05)

        if started:
            os.kill(pid, signal.SIGTERM)

        _, status = os.waitpid(pid, 0)
        # Process should exit cleanly
        assert os.WIFEXITED(status), "Process did not exit cleanly"
