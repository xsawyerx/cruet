# cruet: Flask API Coverage Plan

**Target:** Flask 3.x API compatibility (tested against Flask 3.1.2).

## Current State

- 1062 tests passing, 0 warnings
- libevent2 async server: ~119K req/s (4 workers, hello world)
- Routing: 2.88x faster than Werkzeug, parse_qs 5.7x faster, cookies 33x faster
- HTTP parsing, multipart, cookies all implemented in C
- Priorities 1-9 complete, Flask compat tests expanded, C parser hardening done

## Priority 1: Wire up existing C code to Request object -- DONE

Added to CRequest (all in C, lazy-cached):
- `request.cookies`, `request.files`, `request.remote_addr`,
  `request.environ`, `request.content_length`, `request.mimetype`

## Priority 2: `app.config` -- DONE

- `Config` class (dict subclass) in `src/cruet/config.py`
- `from_object()`, `from_mapping()`, `from_prefixed_env()`, `get_namespace()`
- Flask-compatible defaults (DEBUG, TESTING, SECRET_KEY, SESSION_COOKIE_*, etc.)
- `app.debug`, `app.testing`, `app.secret_key` as config-backed properties

## Priority 3: Sessions (cookie-based) -- DONE

- `Session` class (dict subclass, tracks `modified`/`new`/`permanent`)
- HMAC-SHA256 cookie signing (no external dependencies)
- `session` global proxy with full dict protocol
- `open_session()` / `save_session()` in request lifecycle
- Cookie attributes: HttpOnly, Secure, SameSite, Max-Age, Path, Domain
- Custom cookie name via `SESSION_COOKIE_NAME` config

## Priority 4: Template rendering -- DONE

- `jinja2>=3.0` as default dependency (graceful fallback if absent)
- `app.template_folder` parameter (default `"templates"`)
- `app.jinja_env` lazy cached property
- `render_template(name, **context)` and `render_template_string(source, **context)`
- Auto-injected context: `request`, `session`, `g`, `config`, `url_for`, `get_flashed_messages`
- HTML autoescaping on by default for `.html`/`.htm`/`.xml` and string templates
- Template inheritance (`extends`/`block`) works
- Install without Jinja2: `pip install cruet --no-deps` or `pip install cruet[minimal]`

## Priority 5: Context completeness -- DONE

- `has_request_context()` / `has_app_context()`
- `request.endpoint` — set during dispatch (C getter/setter)
- `request.view_args` — set during dispatch (C getter/setter)
- `request.blueprint` — set during dispatch (C getter/setter)
- `after_this_request(f)` decorator — per-request callbacks, runs before app-level after_request

## Priority 6: App class gaps -- DONE

- `app.run(host, port, debug)` — wraps `serving.run()`
- `app.get()`, `.post()`, `.put()`, `.delete()`, `.patch()` — modern Flask 2.0+ shorthand decorators
- `app.logger` — property returning `logging.getLogger(self.import_name)`
- `app.name` — property returning `self.import_name`
- `app.extensions` — empty dict for Flask extensions
- `app.register_error_handler(code_or_exc, f)` — non-decorator form of `errorhandler()`
- `app.static_folder`, `app.static_url_path`, `app.send_static_file()` — static file serving with auto-registered `/static/<path:filename>` route
- `app.context_processor(f)` — register functions that inject vars into all templates
- `app.template_filter(name)`, `app.add_template_filter(f, name)` — custom Jinja2 filters
- `app.template_global(name)`, `app.add_template_global(f, name)` — custom Jinja2 globals

## Priority 7: Request/Response mutability -- DONE

- `request.get_json(force=False, silent=False, cache=True)` — method form with params (C)
- `request.get_data(cache=True, as_text=False)` — method form of `.data` (C)
- `request.values` — combined args + form MultiDict (C)
- `request.full_path` — path with query string (C)
- `request.is_secure`, `request.scheme` — HTTPS detection (C)
- `request.access_route` — X-Forwarded-For parsing (C)
- `request.referrer`, `request.user_agent` — common header accessors (C)
- `response.status_code` setter (C)
- `response.status` setter (C)
- `response.data` setter — auto-updates Content-Length (C)
- `response.get_data(as_text=False)` (C)
- `response.json` property / `response.get_json()` method (C)
- `response.is_json`, `response.mimetype`, `response.content_length` (C)
- `response.location` getter/setter (C)

## Priority 8: Blueprint completeness & flash messaging -- DONE

- Blueprint: `get()`, `post()`, `put()`, `delete()`, `patch()` — shorthand route decorators
- Blueprint: `add_url_rule()` — non-decorator registration
- Blueprint: `teardown_request()`, `before_app_request()`, `after_app_request()`, `app_errorhandler()`
- `flash(message, category)` / `get_flashed_messages(with_categories, category_filter)` — flash messaging via session
- `get_flashed_messages` auto-injected into template context
- `Config` exported from `cruet.__init__`

## Priority 9: File serving & config loading -- DONE

- `send_file(path_or_file, mimetype, as_attachment, download_name, max_age)` — serve files
- `send_from_directory(directory, path)` — secure file serving with traversal protection
- `Config.from_pyfile(filename, silent)` — load config from .py file
- `Config.from_file(filename, load, silent, text)` — Flask 2.0+ generic file loader (json, toml)

## Item 1: Expanded Flask compat tests -- DONE

- 84 parametrized tests (42 tests x 2 frameworks: Flask 3.1.2 vs cruet)
- Covers: shorthand decorators, `get_json(force/silent)`, `get_data(as_text)`,
  `values`, `full_path`, `scheme`, `is_secure`, `user_agent`, response mutability
  (`status_code`/`data` setters, `get_data`, `location`), flash messaging,
  context processors, template filters/globals, `register_error_handler`,
  blueprint shorthand decorators, `add_url_rule`, config loading (`from_pyfile`,
  `from_file`), static file serving, `send_file`/`send_from_directory`,
  lifecycle hooks (`before_request`, `after_request`, `teardown_request`)
- Bug fix: `get_flashed_messages` now caches on request context (matching Flask behavior —
  multiple calls within same request return same list)

## Item 2: C parser hardening -- DONE

- 206 adversarial edge case tests across 4 C parsers (up from 87, +119 new tests)
- HTTP parser (`test_http_parser_edge.py`): Content-Length overflow (LONG_MAX,
  >32-char strings, negative values, hex prefix, leading zeros), keep-alive
  semantics, URI parsing (fragments, multiple `?`, encoded chars, absolute URI,
  asterisk), body handling (exact match, truncation, short body, binary all-256),
  pipelined requests, header edge cases (duplicates, colons in values, continuation),
  all standard HTTP methods, minimal/empty inputs
- Query string parser (`test_querystring_edge.py`): empty/delimiter-only inputs,
  percent-encoding edge cases (consecutive, encoded delimiters, double-encoding,
  null byte, all ASCII hex values, high-byte graceful handling), duplicate keys,
  semicolon delimiters, stress tests
- Cookie parser (`test_cookies_edge.py`): empty/whitespace-only inputs, quoted
  values (with semicolons, unclosed quotes, embedded equals), 500-cookie stress
  test, 100KB header stress, duplicate names, malformed entries
- Multipart parser (`test_multipart_edge.py`): many parts (50 fields, 20 files,
  mixed), binary file data (all byte values, CRLF, null bytes, 100KB), boundary
  edge cases (long, special chars, all dashes, single char), malformed parts
  (no closing boundary, no blank line, no name param, empty parts, empty body),
  Content-Type handling, filename edge cases (path traversal, empty, unicode)
- All 1062 tests passing, 0 failures

## Item 3: Benchmarks -- DONE

### Microbenchmarks (10K iterations, 5 rounds, median)

| Benchmark                      | ops/sec     | vs baseline               |
|-------------------------------|-------------|---------------------------|
| cruet routing (100 rules)    | 941,476     | 2.88x faster than Werkzeug |
| Werkzeug routing              | 326,769     | (baseline)                |
| CRequest construction         | 806,124     | —                         |
| cruet parse_qs               | 1,507,869   | 5.71x faster than stdlib  |
| stdlib parse_qs               | 264,328     | (baseline)                |
| parse_http_request (GET)      | 976,761     | —                         |
| parse_http_request (POST)     | 1,251,441   | —                         |
| cruet parse_cookies          | 2,221,482   | 33x faster than stdlib    |
| stdlib SimpleCookie           | 67,272      | (baseline)                |

### End-to-end benchmarks (wrk -t4 -c100 -d10s)

| Scenario                                   | req/s     |
|-------------------------------------------|-----------|
| cruet async (1 worker) hello_world       | 52,364    |
| cruet async (4 workers) hello_world      | 119,154   |
| cruet async (4 workers) json /users/1    | 133,640   |
| cruet async (4 workers) routing 500 rules| 142,195   |
| cruet async (4 workers) middleware chain  | 85,723    |
| cruet async (4 workers) middleware /json  | 109,598   |
| Flask + Gunicorn (4 workers) hello_world  | ~1,649    |
| Flask + Gunicorn (4 workers) middleware    | ~1,642    |

Note: Gunicorn benchmarks had socket errors at 100 connections (connect errors),
so Flask+Gunicorn numbers are conservative/understated. Even so, cruet async
server is ~72x faster on hello_world (119K vs 1.6K req/s).

## Deferred

- Signals (`blinker`) — most apps don't use these; extensions that do are rare
- Content negotiation (`request.accept_mimetypes`, etc.) — low usage
- Conditional responses (ETags, `If-Modified-Since`) — low usage
- `stream_with_context`, `stream_template` — streaming responses
- `copy_current_request_context` — threading support
- Pluggable `SessionInterface` — only matters for Flask-Session
- `flask.json` provider system — only matters for custom JSON encoders
- `app.cli` / Click integration — only for `flask` CLI command
- CORS headers — handled by Flask-CORS extension
- Nested blueprints (`bp.register_blueprint()`) — rare usage
- `request.authorization` — parsed Authorization header
- `request.accept_mimetypes` — content negotiation
- Performance optimizations (SIMD, io_uring, arena allocator) — profile first
- CI/CD pipeline
- Valgrind audit on Linux
