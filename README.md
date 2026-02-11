# Cruet

Cruet is a CPython extension that combines both layers of a typical Python web stack:

* A Flask 3.x-compatible framework in Python.
* A built-in pre-fork WSGI server with optional libevent2 async I/O written in C.
* Routing, request/response objects, and HTTP parsing all in fast C.

Cruet is designed to replace both Flask and Gunicorn in one package.

## Speed

```
+--------------------------------+--------------+----------------------------------+---------+
| Test                           | cruet        | Baseline                         | Speedup |
+--------------------------------+--------------+----------------------------------+---------+
| Routing                        | 1,067,630 /s | 273,229 /s (Werkzeug)            |  3.91x  |
| Query parsing (parse_qs)       | 1,351,100 /s | 246,125 /s (stdlib)              |  5.49x  |
| Cookie parsing (parse_cookies) | 2,265,092 /s | 66,821  /s (stdlib SimpleCookie) | 33.90x  |
+--------------------------------+--------------+----------------------------------+---------+
```

```
+------------------------+--------------+----------------+---------+
| Endpoint               | cruet async  | Flask+Gunicorn | Speedup |
+------------------------+--------------+----------------+---------+
| Hello world /          | 67,142 req/s | 1,633 req/s    | 41.1x   |
| Routing-heavy /route/0 | 39,600 req/s | 1,634 req/s    | 24.2x   |
| Middleware-chain /     | 54,503 req/s | 1,635 req/s    | 33.3x   |
| JSON /                 | 15,831 req/s | 1,633 req/s    |  9.7x   |
+------------------------+--------------+----------------+---------+
```

## What's Included

* A single package that covers both framework + WSGI server concerns (Gunicorn + Flask replacement model).
* `from cruet import Flask` aliasing a Flask-compatible app class (`Cruet`).
* C-backed routing (`Rule`, `Map`, `MapAdapter`) with converters.
* C-backed HTTP primitives (`CRequest`, `CResponse`, `CHeaders`) and parsers.
* Flask-style lifecycle hooks, blueprints, config, sessions, templating, testing helpers, and CLI integration.
* Built-in server:
  * Async server via `libevent2` when available.
  * Sync fallback without libevent.
  * Multi-worker pre-fork model.
  * TCP and UNIX socket support (UNIX sockets require async/libevent path).

## Quick Start

```python
from cruet import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return {"ok": True}
```

Run:

```bash
PYTHONPATH=src python -m cruet run your_module:app
```

## Compatibility

* Target runtime: CPython `3.11.x` (`requires-python ==3.11.*`).
* Framework target: Flask 3.x behavior and API shape.
* Server model: built-in WSGI server (`python -m cruet run ...`) intended to replace Gunicorn in the default cruet deployment path.
* WSGI compatibility: can also run behind external WSGI servers like Gunicorn when needed.

Migration baseline:

```python
# before
from flask import Flask

# after
from cruet import Flask
```

## Installation and Build

Development install:

```bash
pip install -e ".[dev]" --no-build-isolation
```

Minimal:

```bash
pip install -e . --no-build-isolation
```

If libevent2 is installed, async server support is compiled in. Without it, build still succeeds and uses sync fallback.

## Running

```bash
# TCP
PYTHONPATH=src python -m cruet run benchmarks.apps.hello_world:app --host 127.0.0.1 --port 8000 --workers 4

# UNIX socket (async/libevent build required)
PYTHONPATH=src python -m cruet run benchmarks.apps.hello_world:app --unix-socket /tmp/cruet.sock --workers 4

# Force sync fallback
PYTHONPATH=src python -m cruet run benchmarks.apps.hello_world:app --no-async
```

## License

MIT
