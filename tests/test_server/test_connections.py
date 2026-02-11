"""Tests for server connections using real sockets."""
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
    time.sleep(0.05)  # Let server start

    yield srv

    srv._running = False
    thread.join(timeout=2)


class TestSingleRequest:
    def test_get_request(self, server):
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock.recv(4096)
        sock.close()
        assert b"200 OK" in response
        assert b"Hello from cruet!" in response

    def test_get_json(self, server):
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.sendall(b"GET /json HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock.recv(4096)
        sock.close()
        assert b"200 OK" in response
        assert b'"status"' in response


class TestMultipleConnections:
    def test_sequential_connections(self, server):
        for _ in range(5):
            sock = socket.create_connection(("127.0.0.1", server.port))
            sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = sock.recv(4096)
            sock.close()
            assert b"200 OK" in response

    def test_concurrent_connections(self, server):
        results = [None] * 10

        def make_request(idx):
            try:
                sock = socket.create_connection(("127.0.0.1", server.port))
                sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                results[idx] = sock.recv(4096)
                sock.close()
            except Exception as e:
                results[idx] = str(e).encode()

        threads = []
        for i in range(10):
            t = threading.Thread(target=make_request, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        for r in results:
            assert r is not None
            assert b"200 OK" in r


class TestNotFound:
    def test_404(self, server):
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.sendall(b"GET /nonexistent HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = sock.recv(4096)
        sock.close()
        assert b"404" in response
