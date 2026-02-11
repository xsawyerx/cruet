
 Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 cruet: Next Steps

 Context

 Phases 0-7 are complete. cruet has a working C extension with URL routing,
 HTTP request/response objects, a custom HTTP/1.1 parser, multipart parsing,
 a Flask-compatible Python app class with blueprints/helpers/context, and 395
 passing tests (including 42 parametrized Flask-vs-cruet compatibility tests).

 The current WSGI server (serving.py) is a Python-level fallback using
 selectors. It works but won't outperform Gunicorn/uWSGI because the event
 loop itself is Python. The next major milestone is a libevent2-based async
 server in C.

 What's done: Phases 0-7 (scaffolding, routing, HTTP objects, app class,
 blueprints, multipart, HTTP parser, Flask compat tests, basic benchmarks/examples).
 395 tests passing, 0 warnings.

 What's next (this plan):
 1. Test audit — make existing tests exhaustive
 2. libevent2-based async WSGI server with UNIX socket support
 3. Run benchmarks and establish baselines

 ---
 Phase A: Test Audit & Hardening

 Goal: Make the test suite exhaustive before adding the async server.
 Catching bugs now is cheaper than debugging them through libevent callbacks.

 A1. Adversarial input tests for C parsers

 File: tests/test_server/test_http_parser_edge.py

 - Extremely long URI (>8KB) — should return None or handle gracefully
 - Extremely long header value (>64KB)
 - Null bytes in path, headers, body
 - CRLF injection in header values (Header: value\r\nEvil: injected)
 - Missing colon in header line
 - Request with 1000+ headers
 - Negative or non-numeric Content-Length
 - Multiple conflicting Content-Length headers
 - HTTP/1.0 request (keep_alive should default to False)
 - Empty method, empty path
 - Request line with extra spaces

 File: tests/test_http/test_querystring_edge.py

 - Malformed percent encoding (%ZZ, %2, %)
 - Null bytes in keys/values
 - Extremely long query string (>64KB)
 - 1000+ parameters

 File: tests/test_http/test_cookies_edge.py

 - Null bytes in cookie values
 - Extremely long cookie values (>4KB)
 - 100+ cookies in a single header

 File: tests/test_http/test_multipart_edge.py

 - Boundary string appearing inside file content
 - Missing Content-Disposition header
 - CRLF vs LF line endings
 - Null bytes in filenames
 - Extremely long field names

 A2. Request/Response edge cases

 File: tests/test_http/test_request_edge.py

 - POST with no Content-Length (empty body)
 - Body larger than Content-Length (should truncate)
 - Non-ASCII characters in query strings (percent-encoded UTF-8)
 - request.cookies property (currently untested — may not exist yet)
 - request.environ direct access
 - Very large JSON body (>1MB)

 File: tests/test_http/test_response_edge.py

 - Content-Length automatically matches body length
 - HEAD request response (headers present, no body)
 - 204 No Content (no body, no Content-Length)
 - Empty Set-Cookie value
 - Response with many headers (100+)
 - Large response body (>1MB)

 A3. MultiDict tests

 File: tests/test_http/test_multidict.py

 - Direct tests for MultiDict class in wrappers.py
 - .get() returns first value from list
 - .get() with default when key missing
 - .getlist() returns full list
 - [] subscript returns first value
 - Empty list edge case
 - Subclass of dict — works with dict.get(), in, len(), iteration

 A4. Server and connection tests

 File: tests/test_server/test_connections_edge.py

 - Keep-alive: multiple requests on same TCP socket
 - HTTP/1.0 request without Connection header (should close)
 - HTTP/1.1 with Connection: close (should close after response)
 - Slow client (data arriving 1 byte at a time)
 - Client disconnects mid-request
 - 50+ concurrent connections
 - Request followed by immediate client close

 A5. App-level edge cases

 File: tests/test_app/test_app_edge.py

 - View function raises an unhandled exception → 500
 - before_request raises exception → error handler
 - after_request raises exception → 500
 - Multiple converters in one route (/user/<int:id>/post/<int:pid>)
 - Route with float and uuid converters
 - Empty response body
 - Response with explicit Content-Type: application/json header

 A6. CLI tests

 File: tests/test_app/test_cli.py

 - python -m cruet run with no args → help/error
 - python -m cruet run module:app parses correctly
 - --host, --port, --workers argument parsing
 - Invalid module path → useful error
 - Module without specified app attribute → useful error

 Verification

 make build && make test
 # Target: 500+ tests, all passing

 ---
 Phase B: libevent2 Async WSGI Server

 Goal: Non-blocking C server using libevent2's bufferevent API. Supports
 TCP and UNIX sockets. Pre-fork worker model. Each worker has its own
 event_base and runs an independent event loop.

 Architecture

 Python: run() → fork N workers → each calls run_event_loop()
                                          ↓
 C:      event_base_new()
         evconnlistener_new_bind()  (TCP or UNIX socket)
         Py_BEGIN_ALLOW_THREADS
         event_base_dispatch()      ← blocks here, GIL released
         Py_END_ALLOW_THREADS
         cleanup and return

 Per connection (inside event_base_dispatch):
         accept_conn_cb()
           → bufferevent_socket_new(fd)
           → set read_cb, write_cb, event_cb
           → enable EV_READ

         read_cb()
           → drain evbuffer into Cruet_Buffer
           → PyGILState_Ensure()
           → call parse_http_request(data)
           → if incomplete: release GIL, return (keep reading)
           → if complete: call process_request()
           → PyGILState_Release()

         process_request()  [GIL held]
           → build_environ(parsed, client_addr, server_addr)
           → app(environ, start_response)
           → format_response(status, headers, body_parts)
           → memcpy response bytes, queue into bufferevent
           → transition to WRITING state

         write_cb()
           → response fully flushed?
           → if keep_alive: reset to READING
           → else: conn_close()

         event_cb()
           → on error/timeout/EOF: conn_close()

 GIL Strategy

 Workers hold the GIL after os.fork(). Before entering event_base_dispatch,
 release it with Py_BEGIN_ALLOW_THREADS. In callbacks, reacquire with
 PyGILState_Ensure() / PyGILState_Release(). This is safe because each
 worker is single-threaded — no contention, just CPython bookkeeping.

 B1. Build system: link libevent2

 File: setup.py — modify

 - Add detect_libevent(): try pkg-config --cflags --libs libevent, then
 fall back to common paths (/opt/homebrew/include, /usr/local/include,
 /usr/include).
 - If found: add include dirs, library dirs, -levent, define
 CRUET_HAS_LIBEVENT=1.
 - If not found: skip io_loop.c from compilation, warn.
 - io_loop.c is entirely inside #ifdef CRUET_HAS_LIBEVENT.

 Verify: make build succeeds with and without libevent installed.

 B2. C structs and declarations

 File: src/_cruet/server/server.h — modify

 Add (under #ifdef CRUET_HAS_LIBEVENT):

 #include <event2/event.h>
 #include <event2/listener.h>
 #include <event2/bufferevent.h>
 #include <event2/buffer.h>
 #include <sys/un.h>

 typedef enum { CRUET_SOCK_TCP, CRUET_SOCK_UNIX } Cruet_SocketType;

 typedef struct {
     Cruet_SocketType socket_type;
     char host[256];
     int port;
     char unix_path[PATH_MAX];
     mode_t unix_mode;       /* default 0666 */
     int backlog;            /* default 1024 */
     double read_timeout;    /* seconds, default 30 */
     double write_timeout;   /* seconds, default 30 */
     size_t max_request_size;/* bytes, default 1MB */
 } Cruet_ServerConfig;

 typedef enum {
     CONN_READING, CONN_PROCESSING, CONN_WRITING, CONN_CLOSING
 } Cruet_ConnState;

 typedef struct {
     Cruet_ConnState state;
     struct bufferevent *bev;
     struct event_base *base;
     Cruet_Buffer read_buf;
     char *response_data;    /* malloc'd, freed after write */
     size_t response_len;
     int keep_alive;
     PyObject *app;          /* borrowed ref */
     Cruet_ServerConfig *config;
     char remote_addr[64];
     int remote_port;
 } Cruet_Connection;

 typedef struct {
     struct event_base *base;
     struct evconnlistener *listener;
     struct event *sig_int;
     struct event *sig_term;
     PyObject *app;          /* borrowed ref */
     Cruet_ServerConfig *config;
     int active_connections;
 } Cruet_Worker;

 PyObject *cruet_run_event_loop(PyObject *self, PyObject *args, PyObject *kw);

 B3. Core event loop implementation

 File: src/_cruet/server/io_loop.c — new

 cruet_run_event_loop() — Python-callable, registered on the module:
 - Parses kwargs: app, host, port, unix_path, backlog,
 read_timeout, write_timeout, max_request_size, listen_fd.
 - Builds Cruet_ServerConfig.
 - Creates event_base_new().
 - If listen_fd >= 0: evconnlistener_new(base, accept_cb, ..., listen_fd).
 - Else if UNIX: bind struct sockaddr_un, unlink() first, chmod() after.
 - Else TCP: bind struct sockaddr_in.
 - Register SIGINT/SIGTERM handlers.
 - Py_BEGIN_ALLOW_THREADS → event_base_dispatch() → Py_END_ALLOW_THREADS.
 - Cleanup: free listener, event base, unlink UNIX socket.

 accept_conn_cb() — libevent accept callback:
 - Allocate Cruet_Connection, init Cruet_Buffer.
 - Extract client address (IPv4 → remote_addr:remote_port, UNIX → "unix":0).
 - Create bufferevent_socket_new(fd, BEV_OPT_CLOSE_ON_FREE).
 - Set callbacks: read_cb, write_cb, event_cb.
 - Set timeouts.
 - Enable EV_READ.

 read_cb() — data available on connection:
 - Drain evbuffer into conn->read_buf.
 - Check max_request_size; send 413 if exceeded.
 - PyGILState_Ensure().
 - Call cruet_parse_http_request(data).
 - If None: incomplete, release GIL, return.
 - If complete: verify body length matches Content-Length.
 - If body incomplete: release GIL, return.
 - Disable EV_READ, call process_request().
 - PyGILState_Release().

 process_request() — GIL is held:
 - Import cruet.serving, call build_environ(parsed, client_addr, server_addr).
 - Create a C start_response callable via PyCapsule + PyCFunction_New.
 - Call app(environ, start_response) → get body iterator.
 - Call format_response(status, headers, body_iter) → get response bytes.
 - Call body_iter.close() if it has one (PEP 3333).
 - malloc + memcpy the response bytes.
 - bufferevent_write(bev, response_data, response_len).
 - Transition to CONN_WRITING.

 write_cb() — output buffer flushed:
 - If evbuffer_get_length(output) > 0: still writing, return.
 - free(conn->response_data).
 - If keep_alive: reset to CONN_READING, re-init read buffer, re-enable
 EV_READ.
 - Else: conn_close().

 event_cb() — error/timeout/EOF:
 - conn_close().

 conn_close():
 - Free read buffer, response data, bufferevent (closes fd).
 - Decrement worker->active_connections.
 - free(conn).

 signal_cb() — graceful shutdown:
 - Disable listener (stop accepting).
 - If no active connections: event_base_loopexit(base, NULL).
 - Else: event_base_loopexit(base, &five_second_timeout).

 send_error_response() — for 400/413/500 before WSGI:
 - Format "HTTP/1.1 {code} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".
 - bufferevent_write(), set keep_alive = 0.

 c_start_response() — the start_response callable:
 - Receives (status_str, headers_list), stores them in a StartResponseData
 struct accessed via PyCapsule.

 B4. Register in server_init.c

 File: src/_cruet/server/server_init.c — modify

 Add to server_functions[]:
 #ifdef CRUET_HAS_LIBEVENT
     {"run_event_loop", (PyCFunction)cruet_run_event_loop,
      METH_VARARGS | METH_KEYWORDS,
      "Run a libevent2-based async WSGI server event loop."},
 #endif

 B5. Python interface

 File: src/cruet/serving.py — modify

 Add AsyncWSGIServer class:
 - __init__(app, host, port, unix_socket, workers, backlog, read_timeout, write_timeout, max_request_size)
 - serve_forever():
   - Single worker: call cruet._cruet.run_event_loop(app, ...) directly.
   - Multi-worker with TCP: fork N children, each calls run_event_loop()
 independently (each binds with SO_REUSEPORT).
   - Multi-worker with UNIX socket: master creates+binds listening socket,
 forks children, each calls run_event_loop(listen_fd=sock.fileno()).
 (macOS UNIX sockets don't support SO_REUSEPORT, so we share the fd.)
   - Master waits, relays SIGTERM to children on shutdown.

 Update run():
 - Add unix_socket=None, use_async=True parameters.
 - If use_async: try importing run_event_loop, use AsyncWSGIServer.
 - If import fails: warn, fall back to existing WSGIServer.

 File: src/cruet/__main__.py — modify

 Add to run subparser:
 - --unix-socket PATH — UNIX socket path (overrides host/port).
 - --no-async — force sync server fallback.

 B6. Tests for async server

 File: tests/test_server/test_async_server.py

 Fixture: start async server in background thread/process on a random port,
 yield, shutdown.

 Tests:
 - Single GET request → 200 + correct body
 - POST with body → echo back
 - JSON request/response round-trip
 - 404 for unknown path
 - Multiple sequential requests on separate connections
 - Keep-alive: two requests on same TCP socket
 - Connection: close header respected
 - Concurrent requests (20 threads)
 - Malformed request → 400
 - Request exceeding max_request_size → 413
 - Graceful shutdown (send SIGTERM, verify clean exit)

 File: tests/test_server/test_unix_socket.py

 Fixture: start async server on a temp UNIX socket file.

 Tests:
 - Connect via UNIX socket, send request, get response
 - Multiple requests on UNIX socket
 - Socket file exists during serving
 - Socket file cleaned up after shutdown
 - Concurrent connections over UNIX socket

 Verification

 make build && make test
 # All existing tests still pass
 # New async server tests pass
 # New UNIX socket tests pass

 # Manual smoke test:
 python -m cruet run examples.hello.app:app --port 8000
 curl http://127.0.0.1:8000/

 python -m cruet run examples.hello.app:app --unix-socket /tmp/cruet.sock
 curl --unix-socket /tmp/cruet.sock http://localhost/

 ---
 Phase C: Benchmarks

 Goal: Establish performance baselines and compare against Flask+Gunicorn.

 C1. Run microbenchmarks

 The scripts already exist at benchmarks/microbenchmarks/:
 - bench_routing.py — cruet routing vs Werkzeug routing
 - bench_parsing.py — HTTP parsing, request construction

 Run them and record numbers.

 C2. End-to-end benchmarks with wrk

 Use benchmarks/apps/hello_world.py and benchmarks/apps/json_api.py.

 Compare:
 1. cruet async server (TCP, 4 workers)
 2. cruet async server (UNIX socket, 4 workers)
 3. Flask + Gunicorn (4 workers)
 4. cruet app + Gunicorn (4 workers — C routing/parsing, Python server)

 Methodology:
 - wrk -t4 -c100 -d30s for each
 - Collect req/s, latency p50/p99

 C3. Missing benchmark apps

 Write:
 - benchmarks/apps/routing_heavy.py — 500 routes
 - benchmarks/apps/middleware_chain.py — 5 before + 5 after hooks

 Verification

 make bench          # Run microbenchmarks
 # Manual:
 wrk -t4 -c100 -d30s http://127.0.0.1:8000/
 wrk -t4 -c100 -d30s --unix /tmp/cruet.sock http://localhost/

 ---
 Deferred (Not In Scope)

 These are explicitly deferred. They may be done later but are not part of
 this plan:

 - io_uring — Linux 5.1+ syscall reduction. Not needed until we've
 profiled and confirmed syscall overhead is the bottleneck.
 - sendfile() — Zero-copy static file serving. cruet is a dynamic
 framework; nginx handles static files in production.
 - Arena allocator (util/arena.c) — Per-request memory pool. The current
 code uses Python's allocator. Worth doing after profiling shows allocation
 is a bottleneck.
 - Hashtable (util/hashtable.c) — Fast route lookup. Current sequential
 matching is fine for <500 routes. Profile first.
 - SIMD parsing — SSE4.2/NEON byte scanning for delimiters. Micro-
 optimization for the HTTP parser inner loop. Profile first.
 - uwsgi binary protocol — For nginx → cruet without HTTP overhead. Low
 priority since UNIX sockets already eliminate most overhead.
 - Valgrind/leaks audit — Important but separate work. Should be done
 before any production use. Track as a follow-up task.
 - CI/CD pipeline — GitHub Actions, PyPI publishing. Not blocking development.

 ---
 File Inventory

 Files to create
 ┌────────────────────────────────────────────┬───────┐
 │                    File                    │ Phase │
 ├────────────────────────────────────────────┼───────┤
 │ src/_cruet/server/io_loop.c               │ B3    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_server/test_http_parser_edge.py │ A1    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_http/test_querystring_edge.py   │ A1    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_http/test_cookies_edge.py       │ A1    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_http/test_multipart_edge.py     │ A1    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_http/test_request_edge.py       │ A2    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_http/test_response_edge.py      │ A2    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_http/test_multidict.py          │ A3    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_server/test_connections_edge.py │ A4    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_app/test_app_edge.py            │ A5    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_app/test_cli.py                 │ A6    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_server/test_async_server.py     │ B6    │
 ├────────────────────────────────────────────┼───────┤
 │ tests/test_server/test_unix_socket.py      │ B6    │
 ├────────────────────────────────────────────┼───────┤
 │ benchmarks/apps/routing_heavy.py           │ C3    │
 ├────────────────────────────────────────────┼───────┤
 │ benchmarks/apps/middleware_chain.py        │ C3    │
 └────────────────────────────────────────────┴───────┘
 Files to modify
 ┌──────────────────────────────────┬───────┬─────────────────────────────────────────────────┐
 │               File               │ Phase │                     Changes                     │
 ├──────────────────────────────────┼───────┼─────────────────────────────────────────────────┤
 │ setup.py                         │ B1    │ detect_libevent(), conditional flags/linking    │
 ├──────────────────────────────────┼───────┼─────────────────────────────────────────────────┤
 │ src/_cruet/server/server.h      │ B2    │ Structs, libevent includes, run_event_loop decl │
 ├──────────────────────────────────┼───────┼─────────────────────────────────────────────────┤
 │ src/_cruet/server/server_init.c │ B4    │ Register run_event_loop                         │
 ├──────────────────────────────────┼───────┼─────────────────────────────────────────────────┤
 │ src/cruet/serving.py            │ B5    │ AsyncWSGIServer, update run()                   │
 ├──────────────────────────────────┼───────┼─────────────────────────────────────────────────┤
 │ src/cruet/__main__.py           │ B5    │ --unix-socket, --no-async args                  │
 └──────────────────────────────────┴───────┴─────────────────────────────────────────────────┘
 Key existing files (read-only reference)
 ┌──────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────┐
 │               File               │                               What it provides                               │
 ├──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
 │ src/_cruet/server/http_parser.c │ parse_http_request() — returns dict with method/path/headers/body/keep_alive │
 ├──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
 │ src/_cruet/util/buffer.h + .c   │ Cruet_Buffer — reusable growable buffer for connection read accumulation    │
 ├──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
 │ src/_cruet/http/http.h          │ Struct layouts for CHeaders, CRequest, CResponse                             │
 ├──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
 │ src/_cruet/module.c             │ Module init pattern, calls Cruet_InitServer()                               │
 ├──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
 │ src/cruet/serving.py            │ build_environ() and format_response() — reused by the C server               │
 └──────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────┘
 ---
 Build Requirements

 libevent2 must be discoverable. On macOS with Homebrew:
 export PKG_CONFIG_PATH=/opt/homebrew/lib/pkgconfig:/opt/homebrew/share/pkgconfig
 export CPPFLAGS="-I/opt/homebrew/include"
 export LDFLAGS="-L/opt/homebrew/lib"

 On Linux:
 apt install libevent-dev

 If libevent2 is not found, the build succeeds without it — io_loop.c is
 excluded, CRUET_HAS_LIBEVENT is not defined, and the Python server is
 used as a fallback.

