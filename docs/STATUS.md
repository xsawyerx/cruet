# cruet Project Status

## What cruet Is

cruet is a CPython C extension that reimplements Flask's hot path in C while
maintaining API compatibility. The goal: change `from flask import Flask` to
`from cruet import Flask` and get a performance boost with zero code changes.

**Target:** Python 3.11+, production on Linux, development on macOS, MIT license.

---

## What's Implemented

### C Extension (`cruet._cruet`) — ~3,000 lines of C

All of the following are compiled into a single `.so` to avoid inter-module
call overhead.

**URL Routing** (`src/_cruet/routing/`)
- `Rule` type: parses `<converter:name>` patterns into segment descriptors,
  matches paths segment-by-segment, builds URLs from value dicts.
- Six converters: `string` (minlength/maxlength/length), `int` (fixed_digits/
  min/max), `float` (min/max), `uuid` (returns `uuid.UUID`), `path` (matches
  across `/`), `any` (whitelist of allowed values).
- `Map` container with `add()` / `bind()` returning a `MapAdapter`.
- `MapAdapter`: iterates rules, checks methods, returns `(endpoint, values)`
  or raises `LookupError("404")` / `LookupError("405")`.

**HTTP Objects** (`src/_cruet/http/`)
- `CHeaders`: case-insensitive header container backed by a list of
  `(name, value)` tuples. Supports `get()`, `getlist()`, `set()`, `add()`,
  `[]` subscript access, `in` operator, `len()`, iteration.
- `CRequest`: wraps a WSGI environ dict. Lazy-cached properties: `args`
  (MultiDict), `headers` (CHeaders), `data` (bytes), `json` (parsed),
  `form` (MultiDict). Direct properties: `method`, `path`, `query_string`,
  `content_type`, `host`, `url`, `base_url`, `is_json`.
- `CResponse`: body (str/bytes), status code, headers, cookies.
  `set_cookie()` / `delete_cookie()`. WSGI `__call__` returns a compliant
  iterator with `close()`.
- `parse_qs()`: custom query string parser (handles `&`/`;`, `+`-to-space,
  percent-decoding).
- `parse_cookies()`: custom Cookie header parser (quoted values, malformed
  input resilience).
- `parse_multipart()`: streaming multipart/form-data parser for file uploads.
  Returns `{"fields": {...}, "files": {...}}`.

**HTTP/1.1 Parser** (`src/_cruet/server/http_parser.c`)
- Single-pass scan of request line + headers into a Python dict.
- Splits URI into `path` + `query_string`.
- Tracks `Content-Length` for body extraction.
- Detects `Connection: close` for keep-alive.
- Returns `None` for incomplete or malformed input.

**libevent2 Async Server** (`src/_cruet/server/io_loop.c`)
- Non-blocking event loop using libevent2's bufferevent API.
- GIL released during `event_base_dispatch()`, reacquired per-request via
  `PyGILState_Ensure()` / `PyGILState_Release()`.
- TCP and UNIX socket support.
- Connection state machine: READING -> PROCESSING -> WRITING.
- Keep-alive with connection reset after response.
- Configurable timeouts (read/write), max request size (413 on exceed).
- Graceful shutdown on SIGINT/SIGTERM.
- Conditionally compiled via `#ifdef CRUET_HAS_LIBEVENT`.
- Build system auto-detects libevent2 via `pkg-config` with fallback paths.

**Utilities** (`src/_cruet/util/`)
- Growable byte buffer (`Cruet_Buffer`).
- URL percent encoding/decoding.

### Python Layer

**Application Class** (`src/cruet/app.py`)
- `Cruet` (aliased as `Flask`): `@route()`, `add_url_rule()`,
  `before_request()`, `after_request()`, `teardown_request()`,
  `errorhandler()`, `register_blueprint()`.
- `make_response()` handles str, bytes, tuple `(body, status)`,
  tuple `(body, status, headers)`, dict (auto-JSON), and CResponse passthrough.
- `test_client()` returns a `TestClient` for in-process testing.
- `app_context()` and `test_request_context()` context managers.

**Blueprints** (`src/cruet/blueprints.py`)
- Deferred route registration with `url_prefix`.
- Blueprint-scoped `before_request`, `after_request`, `errorhandler`.

**Context Management** (`src/cruet/ctx.py`)
- `AppContext` and `RequestContext` using `contextvars`.
- `_AppCtxGlobals` for the `g` object.

**Global Proxies** (`src/cruet/globals.py`)
- `request`, `g`, `current_app` — proxy objects that look up the current
  context variable on every attribute access.

**Helpers** (`src/cruet/helpers.py`)
- `jsonify()`, `redirect()`, `abort()`, `url_for()`, `make_response()`.
- `HTTPException` base class used by `abort()`.

**WSGI Servers** (`src/cruet/serving.py`)
- `AsyncWSGIServer`: libevent2-based async server with pre-fork workers.
  TCP and UNIX socket support. Multi-worker via `SO_REUSEPORT` (TCP) or
  shared fd (UNIX).
- `WSGIServer`: Python `selectors`-based fallback server.
- `build_environ()`: constructs a WSGI environ dict from the C HTTP parser's
  output.
- `format_response()`: serializes status + headers + body to HTTP/1.1 bytes.
- `run()`: unified entry point with `use_async` flag and automatic fallback.
- CLI: `python -m cruet run module:app --host --port --workers --unix-socket --no-async`.

### Test Suite — 602 tests, all passing

| Area | Tests | What's covered |
|------|-------|----------------|
| Build / import | 7 | Module loads, version string, C types exist |
| Routing | 97 | Rules, converters, Map/MapAdapter, 404/405, URL building |
| Headers | 28 | Case-insensitive ops, getlist, set, subscript, iteration |
| Query string | 45 | Parsing, multi-value, URL-decoding, malformed, adversarial |
| Cookies | 38 | Parsing, quoted, special chars, adversarial |
| MultiDict | 24 | get, getlist, subscript, dict behavior, edge cases |
| Request | 68 | All properties, lazy caching, edge cases, large bodies |
| Response | 62 | Status, headers, cookies, WSGI callable, edge cases |
| Multipart | 25 | File uploads, mixed fields, boundary edge cases, adversarial |
| App class | 34 | Route decorator, variables, methods, response types, errors |
| Context | 11 | request/g/current_app proxies, isolation, manual context |
| Lifecycle | 5 | before -> view -> after -> teardown ordering |
| Middleware | 9 | before_request short-circuit, after_request modify, errors |
| Blueprints | 8 | Registration, url_prefix, scoped handlers |
| Helpers | 15 | jsonify, redirect, abort, url_for, make_response |
| CLI | 10 | Arg parsing, invalid module, defaults |
| HTTP parser | 56 | GET/POST, headers, Content-Length, keep-alive, adversarial |
| WSGI compliance | 12 | PEP 3333 environ keys, wsgiref.validate |
| Connections | 17 | Sequential, concurrent, keep-alive, slow client, disconnect |
| Async server | 13 | TCP requests, keep-alive, concurrency, errors, shutdown |
| UNIX socket | 8 | Connect, request, concurrent, lifecycle, cleanup |
| Flask compat | 43 | Same tests against both Flask and cruet |

### Other Artifacts

- **Benchmark apps:** `hello_world.py`, `json_api.py`, `routing_heavy.py`,
  `middleware_chain.py` (all Flask-compatible).
- **Microbenchmarks:** `bench_routing.py` (cruet vs Werkzeug routing),
  `bench_parsing.py` (HTTP parsing, request construction).
- **Examples:** `hello/app.py`, `todo_api/app.py`, `blog/app.py` (with
  blueprints).
- **Type stubs:** `_cruet.pyi`, `py.typed`.

---

## What's Not Implemented

### Route Matching Optimization (Completed)

Static routes are now indexed in a hash table for O(1) lookup. Dynamic
routes use direct C-level matching (no Python method dispatch overhead).
Result: **2.93x faster than Werkzeug** routing (up from 0.45x slower).

### Memory Safety Audit (Completed)

macOS `leaks` analysis: **0 leaks** across 5,000 iterations exercising all C
types. Manual code audit identified and fixed 12 issues:
- 3 critical: NULL-deref on OOM in map.c and rule.c (Py_DECREF on NULL)
- 3 moderate: error/no-match conflation in convert_segment_value
- 3 minor: missing NULL checks on allocations
- 3 safe-but-noted: borrowed reference patterns in io_loop.c

### Deferred: Performance Utilities

| Planned file | Purpose | Status |
|-------------|---------|--------|
| `util/arena.c` | Per-request arena allocator (free all temp memory in one shot) | Not implemented |

Arena allocator is the main remaining optimization target. The current code
uses Python's allocator, which is correct but leaves performance on the table.

### Deferred: Advanced Optimizations

- **SIMD byte scanning** for header/delimiter parsing (SSE4.2, NEON).
- **io_uring** support for Linux 5.1+ (reduces syscall overhead).
- **Pre-computed hash values** for common header names.
- **`writev()`** for header+body coalescing.
- **sendfile()** for zero-copy static file serving.
- **uwsgi binary protocol** for nginx -> cruet communication.

These depend on profiling data to guide where optimization matters most.

### Not Yet Done

- **CI/CD pipeline.** No GitHub Actions, no PyPI publishing.

---

## Architecture Summary

```
User code                    Python layer                 C extension
─────────                    ────────────                 ───────────
@app.route("/")         →    Cruet.add_url_rule()   →   Rule(), Map.add()
request arrives         →    io_loop.c / serving.py  →   parse_http_request() [C]
                        →    build_environ()          →   (Python dict construction)
                        →    Cruet.wsgi_app()
                        →      RequestContext push    →   CRequest(environ) [C]
                        →      before_request hooks
                        →      dispatch_request()     →   MapAdapter.match() [C]
                        →      view_function()
                        →      make_response()        →   CResponse() [C]
                        →      after_request hooks
                        →      teardown hooks
                        →    response.__call__()      →   CResponse WSGI callable [C]
                        →    io_loop.c / serving.py sends bytes
```

The C extension handles the per-request hot path: URL matching, request
parsing, response serialization, and (with libevent2) the I/O event loop.
The Python layer handles lifecycle orchestration, middleware dispatch, and
context management — things that benefit from Python's flexibility more
than C's speed.

---

## How to Verify

```bash
make build          # Compile C extension + install
make test           # Run all 602 tests

# Run microbenchmarks
make bench

# Serve an app (async server with libevent2)
python -m cruet run examples.hello.app:app --port 8000 --workers 4

# UNIX socket
python -m cruet run examples.hello.app:app --unix-socket /tmp/cruet.sock

# Or use with any WSGI server
gunicorn examples.hello.app:app -w 4 -b 127.0.0.1:8000
```

---

## Next

1. Memory safety audit (high priority)
No valgrind/leaks analysis has been done on the C extension. Every PyObject * in ~3,000 lines of C needs correct refcounting. This is the biggest risk before any production use.
# Linux
valgrind --leak-check=full python -m pytest tests/
# macOS
leaks --atExit -- python -m pytest tests/

2. End-to-end benchmarks with wrk (quick win)
The benchmark apps exist but no numbers have been collected. This will tell you where cruet actually stands vs Flask+Gunicorn:
# Terminal 1: start server
python -m cruet run benchmarks.apps.hello_world:app --port 8000 --workers 4

# Terminal 2: benchmark
wrk -t4 -c100 -d30s http://127.0.0.1:8000/
Compare against CRUET_USE_FLASK=1 gunicorn benchmarks.apps.hello_world:app -w 4.

3. Fix routing performance
The microbenchmarks showed cruet routing at ~0.44x Werkzeug speed. The current C router does linear scan over rules. A trie-based lookup or hash table for static routes would likely flip this to a significant win
 — routing is supposed to be the primary C hot-path advantage.

4. CI/CD pipeline
GitHub Actions for automated testing on Linux + macOS, with and without libevent2. PyPI publishing when ready.

5. Deferred optimizations (profile-guided)
Once benchmarks identify actual bottlenecks: arena allocator, SIMD parsing, io_uring, sendfile(), pre-computed header hashes. These should be driven by profiling data, not guesswork.

The memory audit is the most important — everything else is performance or convenience, but incorrect refcounting means silent memory leaks or crashes under load.

