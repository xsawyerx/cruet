# Hacking on Cruet

This document is for contributors who need to understand how cruet works internally.

## Design Intent

Cruet splits responsibilities across two layers that ship together:

* Python framework layer (`src/cruet/`): Flask-compatible API, app lifecycle, context, blueprints, helpers.
* WSGI server + C hot path layer (`src/_cruet/` and `src/cruet/serving.py`): parsing, I/O loop, request dispatch plumbing.

Contributors should treat Cruet as a combined Gunicorn + Flask replacement architecture, not just a framework shim.

The core tradeoff is deliberate: keep Python ergonomics and extension compatibility where possible, move high-frequency work into C.

## High-Level Request Flow

1. Server accepts bytes (async libevent path or sync selectors path).
2. `parse_http_request` (C) parses request line/headers/body metadata.
3. `build_environ` (C) builds WSGI environ.
4. `Cruet.wsgi_app` (Python) runs context/lifecycle dispatch.
5. URL matching uses `MapAdapter.match` (C-first path unless Werkzeug fallback is required).
6. View result normalized to response (`Response`/`CResponse` path).
7. `format_response` (C) serializes status+headers+body.

## Source Layout

```text
src/
  _cruet/
    module.c, module.h              module init and exported methods
    routing/
      rule.c                        rule parsing/matching/building
      map.c                         map adapter and matching strategy
      converters.c                  string/int/float/path/uuid/any converters
      routing.h, routing_init.c     routing declarations/registration
    http/
      request.c                     CRequest
      response.c                    CResponse
      headers.c                     CHeaders
      querystring.c                 parse_qs
      cookies.c                     parse_cookies
      multipart.c                   parse_multipart
      http.h, http_init.c
    server/
      http_parser.c                 parse_http_request
      wsgi.c                        build_environ + format_response
      io_loop.c                     libevent2 event loop (conditional compile)
      server.h, server_init.c
    util/
      buffer.c, buffer.h            growable buffer
      percent_encode.c/.h
  cruet/
    app.py                          Cruet/Flask app class and dispatch lifecycle
    serving.py                      sync+async server wrappers and pre-fork logic
    wrappers.py                     Python wrappers around C request/response
    blueprints.py                   Blueprint behavior
    ctx.py, globals.py              contextvars-based context and proxies
    cli.py                          Flask-like Click CLI integration
    __main__.py                     `python -m cruet run` entrypoint
```

## Routing Internals

`URLMap` in `src/cruet/app.py` wraps C `Map`, but can switch to Werkzeug routing for unsupported/advanced cases (custom converters, host/subdomain features, rule factories).

Important behavior:

* Fast path: C map/rule matching.
* Compatibility path: Werkzeug map bind/match when needed.
* `add_spec` keeps metadata and can force Werkzeug fallback based on route shape/method conflicts.

The CoW-focused routing tests are in `tests/test_routing/test_cow_routing.py`.

## HTTP and WSGI Internals

* `parse_http_request` returns parsed request metadata or `None` for incomplete/malformed input.
* `build_environ` produces PEP 3333-style environ keys.
* `CRequest` lazily parses args/form/json/headers.
* `CResponse` owns serialization state and cookie helpers.
* `Response` in `src/cruet/wrappers.py` is a Python compatibility wrapper around `CResponse`.

## Server Internals

`src/cruet/serving.py` has two paths:

* `AsyncWSGIServer`:
  * Requires `run_event_loop` from C module (libevent build).
  * Supports TCP and UNIX sockets.
  * Multi-worker pre-fork model.
* `WSGIServer`:
  * Pure Python `selectors` fallback.
  * Used when async path unavailable or disabled.

`run()` chooses async when available unless `use_async=False`.

## Build System

Files:

* `pyproject.toml` (package metadata + pytest config)
* `setup.py` (C extension compile, libevent detection, conditional source inclusion)

Build commands:

```bash
pip install -e . --no-build-isolation
pip install -e ".[dev]" --no-build-isolation
```

Why `--no-build-isolation`: useful in offline/dev environments where pulling build deps is not possible.

`setup.py` details:

* Detects libevent via `pkg-config` then fallback include/lib directories.
* Defines `CRUET_HAS_LIBEVENT=1` when found.
* Excludes `src/_cruet/server/io_loop.c` if libevent missing.

## Test Layout and What to Run

Quick commands:

```bash
PYTHONPATH=src python -m pytest tests/test_build.py -q
PYTHONPATH=src python -m pytest tests/test_routing/ -q
PYTHONPATH=src python -m pytest tests/test_http/ -q
PYTHONPATH=src python -m pytest tests/test_app/ -q
PYTHONPATH=src python -m pytest tests/ --collect-only -q
```

Compatibility tests include `tests/test_flask_upstream/` shims and `tests/test_compat/`.

## Benchmarks

* Micro: `python benchmarks/run_benchmarks.py`
* End-to-end wrk: `bash benchmarks/run_wrk.sh`

Benchmark apps:

* `benchmarks/apps/hello_world.py`
* `benchmarks/apps/json_api.py`
* `benchmarks/apps/routing_heavy.py`
* `benchmarks/apps/middleware_chain.py`

## Contributor Checklist

1. Edit C/Python code.
2. Rebuild extension when C changes.
3. Run focused tests first, then broader suites.
4. Run benchmark scripts only when profiling a concrete change.
5. Update `README.md` (product impact) and this file (internal mechanics) when behavior changes.
