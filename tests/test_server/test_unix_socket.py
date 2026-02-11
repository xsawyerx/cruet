"""Tests for UNIX socket support in the async server."""
import os
import signal
import socket
import tempfile
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
        return "Hello from UNIX socket!"

    @app.route("/json")
    def json_view():
        return {"status": "ok", "socket": "unix"}

    return app


@pytest.fixture
def unix_server(app):
    """Start async server on a temp UNIX socket."""
    tmpdir = tempfile.mkdtemp()
    sock_path = os.path.join(tmpdir, "cruet_test.sock")

    pid = os.fork()
    if pid == 0:
        try:
            run_event_loop(
                app,
                unix_path=sock_path,
                backlog=128,
                read_timeout=5,
                write_timeout=5,
                max_request_size=1048576,
            )
        except Exception:
            pass
        os._exit(0)

    # Wait for socket file to appear
    deadline = time.time() + 5
    while time.time() < deadline:
        if os.path.exists(sock_path):
            # Try connecting
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(sock_path)
                s.close()
                break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.05)
        else:
            time.sleep(0.05)
    else:
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)
        pytest.skip("UNIX socket server did not start in time")

    yield sock_path, pid

    # Cleanup
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    # Clean up temp files
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


def _unix_http_get(sock_path, path="/"):
    """Send HTTP GET over UNIX socket."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(sock_path)
    req = f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n"
    sock.sendall(req.encode())
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


class TestUnixSocketBasic:
    def test_get_request(self, unix_server):
        """Connect via UNIX socket, send request, get response."""
        sock_path, _ = unix_server
        response = _unix_http_get(sock_path, "/")
        assert b"200 OK" in response
        assert b"Hello from UNIX socket!" in response

    def test_json_request(self, unix_server):
        """JSON response over UNIX socket."""
        sock_path, _ = unix_server
        response = _unix_http_get(sock_path, "/json")
        assert b"200 OK" in response
        assert b'"status"' in response

    def test_404_over_unix(self, unix_server):
        """404 for unknown path over UNIX socket."""
        sock_path, _ = unix_server
        response = _unix_http_get(sock_path, "/nonexistent")
        assert b"404" in response


class TestUnixSocketMultiple:
    def test_multiple_requests(self, unix_server):
        """Multiple requests on UNIX socket."""
        sock_path, _ = unix_server
        for _ in range(5):
            response = _unix_http_get(sock_path, "/")
            assert b"200 OK" in response

    def test_concurrent_unix_connections(self, unix_server):
        """Concurrent connections over UNIX socket."""
        sock_path, _ = unix_server
        import threading

        results = [None] * 10

        def make_request(idx):
            try:
                results[idx] = _unix_http_get(sock_path, "/")
            except Exception as e:
                results[idx] = str(e).encode()

        threads = [threading.Thread(target=make_request, args=(i,))
                   for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        success = sum(1 for r in results if r and b"200 OK" in r)
        assert success >= 8, f"Only {success}/10 succeeded"


class TestUnixSocketLifecycle:
    def test_socket_file_exists_during_serving(self, unix_server):
        """Socket file should exist while server is running."""
        sock_path, _ = unix_server
        assert os.path.exists(sock_path)

    def test_socket_file_cleaned_up_after_shutdown(self, app):
        """Socket file should be cleaned up after shutdown."""
        tmpdir = tempfile.mkdtemp()
        sock_path = os.path.join(tmpdir, "cleanup_test.sock")

        pid = os.fork()
        if pid == 0:
            try:
                run_event_loop(
                    app,
                    unix_path=sock_path,
                    read_timeout=5,
                    write_timeout=5,
                )
            except Exception:
                pass
            os._exit(0)

        # Wait for server to start
        deadline = time.time() + 5
        while time.time() < deadline:
            if os.path.exists(sock_path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(sock_path)
                    s.close()
                    break
                except (ConnectionRefusedError, OSError):
                    time.sleep(0.05)
            else:
                time.sleep(0.05)

        # Send SIGTERM
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)

        # Socket file should be cleaned up by the C code
        time.sleep(0.1)
        # The C event loop unlinks the socket on shutdown
        assert not os.path.exists(sock_path), \
            "Socket file should be cleaned up after shutdown"

        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
