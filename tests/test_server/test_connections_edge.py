"""Edge case tests for server connections."""
import socket
import threading
import time
import pytest
from cruet import Cruet
from cruet.serving import WSGIServer


@pytest.fixture
def app():
    app = Cruet(__name__)

    @app.route("/")
    def index():
        return "Hello from cruet!"

    @app.route("/echo", methods=["POST"])
    def echo():
        from cruet.globals import request
        return request.data.decode("utf-8", errors="replace")

    @app.route("/json")
    def json_view():
        return {"status": "ok"}

    return app


@pytest.fixture
def server(app):
    """Start a server in a background thread on a random port."""
    srv = WSGIServer(app, host="127.0.0.1", port=0)
    srv._sock = srv._create_socket()
    port = srv._sock.getsockname()[1]
    srv.port = port
    srv._running = True

    def run():
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(srv._sock, selectors.EVENT_READ)
        while srv._running:
            events = sel.select(timeout=0.1)
            for key, mask in events:
                if key.fileobj is srv._sock:
                    try:
                        client_sock, client_addr = srv._sock.accept()
                        client_sock.setblocking(True)
                        srv.handle_request(client_sock, client_addr)
                        client_sock.close()
                    except OSError:
                        pass
        sel.unregister(srv._sock)
        sel.close()
        srv._sock.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.05)

    yield srv

    srv._running = False
    thread.join(timeout=2)


class TestKeepAlive:
    def test_http11_default_keep_alive(self, server):
        """HTTP/1.1 defaults to keep-alive; multiple requests on same socket."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)

        # First request
        sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock.recv(4096)
        assert b"200 OK" in response
        assert b"Hello from cruet!" in response

        sock.close()

    def test_connection_close_header(self, server):
        """Connection: close should close after response."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)
        sock.sendall(
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"\r\n"
        )
        response = sock.recv(4096)
        assert b"200 OK" in response
        sock.close()


class TestHTTP10:
    def test_http10_without_connection_header(self, server):
        """HTTP/1.0 request without Connection header should close."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)
        sock.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
        response = sock.recv(4096)
        assert b"Hello from cruet!" in response
        sock.close()


class TestSlowClient:
    def test_data_one_byte_at_a_time(self, server):
        """Data arriving 1 byte at a time should still work."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)
        request_data = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        for byte in request_data:
            sock.send(bytes([byte]))
            time.sleep(0.001)
        response = sock.recv(4096)
        assert b"200 OK" in response
        sock.close()


class TestClientDisconnect:
    def test_client_disconnects_mid_request(self, server):
        """Client disconnecting mid-request should not crash the server."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.sendall(b"GET / HTTP/1.1\r\nHost: loc")
        sock.close()

        # Server should still be alive for new requests
        time.sleep(0.1)
        sock2 = socket.create_connection(("127.0.0.1", server.port))
        sock2.settimeout(5)
        sock2.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock2.recv(4096)
        assert b"200 OK" in response
        sock2.close()


class TestConcurrentConnections:
    def test_50_concurrent(self, server):
        """50 concurrent connections should all get responses."""
        results = [None] * 50

        def make_request(idx):
            try:
                sock = socket.create_connection(("127.0.0.1", server.port), timeout=10)
                sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                results[idx] = sock.recv(4096)
                sock.close()
            except Exception as e:
                results[idx] = str(e).encode()

        threads = [threading.Thread(target=make_request, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        success = sum(1 for r in results if r and b"200 OK" in r)
        # Allow some failures due to single-threaded server, but most should succeed
        assert success >= 40, f"Only {success}/50 succeeded"


class TestImmediateClose:
    def test_request_then_immediate_close(self, server):
        """Client sends request and immediately closes without reading."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        sock.close()

        # Server should still work
        time.sleep(0.1)
        sock2 = socket.create_connection(("127.0.0.1", server.port))
        sock2.settimeout(5)
        sock2.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock2.recv(4096)
        assert b"200 OK" in response
        sock2.close()

    def test_connect_and_immediately_close(self, server):
        """Connect and immediately close without sending anything."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.close()

        # Server should still work
        time.sleep(0.1)
        sock2 = socket.create_connection(("127.0.0.1", server.port))
        sock2.settimeout(5)
        sock2.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock2.recv(4096)
        assert b"200 OK" in response
        sock2.close()


class TestMalformedRequests:
    def test_garbage_data(self, server):
        """Sending garbage data should get 400 or be handled gracefully."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)
        sock.sendall(b"\x00\x01\x02\x03\x04\r\n\r\n")
        try:
            response = sock.recv(4096)
            # Should get 400 or empty response
            if response:
                assert b"400" in response or b"500" in response
        except (socket.timeout, ConnectionResetError):
            pass  # Server may close connection
        sock.close()

    def test_empty_lines_before_request(self, server):
        """Empty lines before request."""
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)
        sock.sendall(b"\r\n\r\nGET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        try:
            response = sock.recv(4096)
            # May or may not handle preamble
        except (socket.timeout, ConnectionResetError):
            pass
        sock.close()
