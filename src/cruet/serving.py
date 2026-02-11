"""WSGI server using cruet's C HTTP parser and pre-fork worker model."""
import io
import os
import signal
import socket
import selectors
import sys
import time

from cruet._cruet import parse_http_request, build_environ, format_response


class WSGIServer:
    """Simple WSGI server using cruet's C HTTP parser."""

    def __init__(self, app, host="127.0.0.1", port=8000, backlog=128):
        self.app = app
        self.host = host
        self.port = port
        self.backlog = backlog
        self._running = False
        self._sock = None

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.bind((self.host, self.port))
        sock.listen(self.backlog)
        sock.setblocking(False)
        return sock

    def handle_request(self, client_sock, client_addr):
        """Handle a single HTTP request on a connected socket."""
        try:
            # Read request data
            data = b""
            while True:
                try:
                    chunk = client_sock.recv(65536)
                    if not chunk:
                        return
                    data += chunk
                    # Check if we have a complete request
                    if b"\r\n\r\n" in data:
                        # Check Content-Length for body
                        parsed = parse_http_request(data)
                        if parsed is not None:
                            break
                except BlockingIOError:
                    break

            if not data:
                return

            parsed = parse_http_request(data)
            if parsed is None:
                client_sock.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
                return

            # Build WSGI environ
            environ = build_environ(parsed, client_addr, (self.host, self.port))

            # Call the WSGI app
            status_holder = {}
            headers_holder = {}

            def start_response(status, response_headers, exc_info=None):
                status_holder["status"] = status
                headers_holder["headers"] = response_headers

            body_parts = self.app(environ, start_response)

            # Send response
            response_data = format_response(
                status_holder.get("status", "500 Internal Server Error"),
                headers_holder.get("headers", []),
                body_parts
            )
            client_sock.sendall(response_data)

            # Handle keep-alive
            if not parsed.get("keep_alive", True):
                client_sock.close()

        except Exception as e:
            try:
                error_resp = b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n"
                client_sock.sendall(error_resp)
            except Exception:
                pass

    def serve_forever(self):
        """Run the server event loop."""
        self._sock = self._create_socket()
        self._running = True
        sel = selectors.DefaultSelector()
        sel.register(self._sock, selectors.EVENT_READ)

        print(f" * cruet server running on http://{self.host}:{self.port}/", flush=True)

        while self._running:
            try:
                events = sel.select(timeout=1.0)
                for key, mask in events:
                    if key.fileobj is self._sock:
                        try:
                            client_sock, client_addr = self._sock.accept()
                            client_sock.setblocking(True)
                            self.handle_request(client_sock, client_addr)
                            client_sock.close()
                        except OSError:
                            pass
            except KeyboardInterrupt:
                break

        sel.unregister(self._sock)
        sel.close()
        self._sock.close()
        print(" * Server stopped.", flush=True)

    def shutdown(self):
        self._running = False


def run_worker(app, sock, worker_id):
    """Worker process: accept and handle connections on shared socket."""
    sel = selectors.DefaultSelector()
    sel.register(sock, selectors.EVENT_READ)

    server = WSGIServer.__new__(WSGIServer)
    server.app = app
    server.host = sock.getsockname()[0]
    server.port = sock.getsockname()[1]
    server._running = True

    def handle_signal(signum, frame):
        server._running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while server._running:
        try:
            events = sel.select(timeout=1.0)
            for key, mask in events:
                try:
                    client_sock, client_addr = sock.accept()
                    client_sock.setblocking(True)
                    server.handle_request(client_sock, client_addr)
                    client_sock.close()
                except OSError:
                    pass
        except KeyboardInterrupt:
            break

    sel.unregister(sock)
    sel.close()


class AsyncWSGIServer:
    """Async WSGI server using libevent2 C event loop with pre-fork workers."""

    def __init__(self, app, host="127.0.0.1", port=8000, unix_socket=None,
                 workers=1, backlog=1024, read_timeout=30, write_timeout=30,
                 max_request_size=1048576):
        self.app = app
        self.host = host
        self.port = port
        self.unix_socket = unix_socket
        self.workers = workers
        self.backlog = backlog
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.max_request_size = max_request_size

    def serve_forever(self):
        from cruet._cruet import run_event_loop

        if self.unix_socket:
            addr_str = f"unix:{self.unix_socket}"
        else:
            addr_str = f"http://{self.host}:{self.port}/"

        if self.workers <= 1:
            print(f" * cruet async server running on {addr_str}", flush=True)
            run_event_loop(
                self.app,
                host=self.host,
                port=self.port,
                unix_path=self.unix_socket or "",
                backlog=self.backlog,
                read_timeout=self.read_timeout,
                write_timeout=self.write_timeout,
                max_request_size=self.max_request_size,
            )
            return

        print(f" * cruet async server running on {addr_str} "
              f"(workers: {self.workers})", flush=True)

        if self.unix_socket:
            # UNIX socket: master creates + binds, children share fd
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.setblocking(False)
            try:
                os.unlink(self.unix_socket)
            except FileNotFoundError:
                pass
            sock.bind(self.unix_socket)
            sock.listen(self.backlog)
            os.chmod(self.unix_socket, 0o666)
            listen_fd = sock.fileno()

            worker_pids = []
            for i in range(self.workers):
                pid = os.fork()
                if pid == 0:
                    run_event_loop(
                        self.app,
                        unix_path=self.unix_socket,
                        backlog=self.backlog,
                        read_timeout=self.read_timeout,
                        write_timeout=self.write_timeout,
                        max_request_size=self.max_request_size,
                        listen_fd=listen_fd,
                    )
                    os._exit(0)
                else:
                    worker_pids.append(pid)
                    print(f" * Worker {i} started (PID {pid})", flush=True)
        else:
            # TCP: master creates + binds, children share fd
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            sock.bind((self.host, self.port))
            sock.listen(self.backlog)
            listen_fd = sock.fileno()

            worker_pids = []
            for i in range(self.workers):
                pid = os.fork()
                if pid == 0:
                    run_event_loop(
                        self.app,
                        host=self.host,
                        port=self.port,
                        backlog=self.backlog,
                        read_timeout=self.read_timeout,
                        write_timeout=self.write_timeout,
                        max_request_size=self.max_request_size,
                        listen_fd=listen_fd,
                    )
                    os._exit(0)
                else:
                    worker_pids.append(pid)
                    print(f" * Worker {i} started (PID {pid})", flush=True)

        # Master: wait for workers, relay SIGTERM
        def shutdown_handler(signum, frame):
            print("\n * Shutting down workers...", flush=True)
            for pid in worker_pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for pid in worker_pids:
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
            if self.unix_socket:
                try:
                    os.unlink(self.unix_socket)
                except FileNotFoundError:
                    pass
            sys.exit(0)

        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            shutdown_handler(None, None)


def run(app, host="127.0.0.1", port=8000, workers=1, unix_socket=None,
        use_async=True):
    """Run the cruet WSGI server.

    Args:
        app: WSGI application callable
        host: Bind address
        port: Bind port
        workers: Number of worker processes (1 = single process)
        unix_socket: Path to UNIX socket (overrides host/port)
        use_async: Use libevent2-based async server if available
    """
    if use_async:
        try:
            from cruet._cruet import run_event_loop  # noqa: F401
            server = AsyncWSGIServer(
                app, host, port,
                unix_socket=unix_socket,
                workers=workers,
            )
            server.serve_forever()
            return
        except ImportError:
            import warnings
            warnings.warn(
                "libevent2 not available, falling back to sync server",
                RuntimeWarning, stacklevel=2,
            )

    if unix_socket:
        raise RuntimeError(
            "UNIX socket support requires the async server (libevent2)")

    if workers <= 1:
        server = WSGIServer(app, host, port)
        server.serve_forever()
        return

    # Pre-fork model
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.bind((host, port))
    sock.listen(128)
    sock.setblocking(False)

    print(f" * cruet server running on http://{host}:{port}/ (workers: {workers})", flush=True)

    worker_pids = []
    for i in range(workers):
        pid = os.fork()
        if pid == 0:
            # Child process
            run_worker(app, sock, i)
            os._exit(0)
        else:
            worker_pids.append(pid)
            print(f" * Worker {i} started (PID {pid})", flush=True)

    # Master process: wait for workers
    def shutdown_handler(signum, frame):
        print("\n * Shutting down workers...", flush=True)
        for pid in worker_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for pid in worker_pids:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        sock.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_handler(None, None)
