"""Microbenchmark: C-level parsing performance.

1. CRequest construction from environ dicts (10K iterations).
2. parse_qs for query string parsing (10K iterations).
3. parse_http_request for raw HTTP parsing (10K iterations).
4. parse_cookies for cookie header parsing (10K iterations).
"""

import io
import time
import statistics
import sys


def _make_environ(i=0):
    """Build a realistic WSGI environ dict."""
    return {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": f"/api/users/{i}",
        "QUERY_STRING": f"page={i % 10}&limit=20&sort=name&order=asc&filter=active",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "HTTP_HOST": "localhost:8000",
        "HTTP_ACCEPT": "application/json",
        "HTTP_USER_AGENT": "bench/1.0",
        "HTTP_ACCEPT_ENCODING": "gzip, deflate",
        "HTTP_CONNECTION": "keep-alive",
        "CONTENT_TYPE": "application/json",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(b""),
        "wsgi.errors": io.BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "SCRIPT_NAME": "",
    }


def bench_crequest_construction(n=10_000):
    """Benchmark constructing CRequest objects from environ dicts."""
    from cruet._cruet import CRequest

    # Pre-build environ dicts
    environs = [_make_environ(i) for i in range(n)]

    # Warm up
    for env in environs[:100]:
        CRequest(env)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for env in environs:
            req = CRequest(env)
            # Access a few attributes to ensure they are parsed
            _ = req.method
            _ = req.path
            _ = req.args
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "CRequest construction",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def bench_parse_qs(n=10_000):
    """Benchmark cruet._cruet.parse_qs."""
    from cruet._cruet import parse_qs

    query_strings = [
        f"page={i % 10}&limit=20&sort=name&order=asc&filter=active&q=search+term+{i}"
        for i in range(n)
    ]

    # Warm up
    for qs in query_strings[:100]:
        parse_qs(qs)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for qs in query_strings:
            parse_qs(qs)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "parse_qs",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def bench_stdlib_parse_qs(n=10_000):
    """Benchmark stdlib urllib.parse.parse_qs for comparison."""
    from urllib.parse import parse_qs

    query_strings = [
        f"page={i % 10}&limit=20&sort=name&order=asc&filter=active&q=search+term+{i}"
        for i in range(n)
    ]

    # Warm up
    for qs in query_strings[:100]:
        parse_qs(qs)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for qs in query_strings:
            parse_qs(qs)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "stdlib parse_qs",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def bench_http_parser(n=10_000):
    """Benchmark cruet._cruet.parse_http_request."""
    from cruet._cruet import parse_http_request

    # Build realistic HTTP requests of varying sizes
    requests = []
    for i in range(n):
        raw = (
            f"GET /api/users/{i}?page={i % 10}&limit=20 HTTP/1.1\r\n"
            f"Host: localhost:8000\r\n"
            f"Accept: application/json\r\n"
            f"User-Agent: bench/1.0\r\n"
            f"Accept-Encoding: gzip, deflate\r\n"
            f"Connection: keep-alive\r\n"
            f"Cookie: session=abc{i}def; tracking=xyz\r\n"
            f"\r\n"
        ).encode()
        requests.append(raw)

    # Warm up
    for raw in requests[:100]:
        parse_http_request(raw)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for raw in requests:
            parse_http_request(raw)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "parse_http_request",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def bench_http_parser_with_body(n=10_000):
    """Benchmark parse_http_request with POST body."""
    from cruet._cruet import parse_http_request

    body = b'{"key": "value", "number": 42, "list": [1, 2, 3]}'
    requests = []
    for i in range(n):
        raw = (
            f"POST /api/users HTTP/1.1\r\n"
            f"Host: localhost:8000\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Accept: application/json\r\n"
            f"\r\n"
        ).encode() + body
        requests.append(raw)

    # Warm up
    for raw in requests[:100]:
        parse_http_request(raw)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for raw in requests:
            parse_http_request(raw)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "parse_http_request (POST)",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def bench_parse_cookies(n=10_000):
    """Benchmark cruet._cruet.parse_cookies."""
    from cruet._cruet import parse_cookies

    cookie_strings = [
        f"session=abc{i}def; tracking=xyz; theme=dark; lang=en; "
        f"_ga=GA1.2.{i}.{i*2}; _gid=GA1.2.{i*3}.{i*4}"
        for i in range(n)
    ]

    # Warm up
    for cs in cookie_strings[:100]:
        parse_cookies(cs)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for cs in cookie_strings:
            parse_cookies(cs)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "parse_cookies",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def bench_stdlib_cookies(n=10_000):
    """Benchmark stdlib http.cookies.SimpleCookie for comparison."""
    from http.cookies import SimpleCookie

    cookie_strings = [
        f"session=abc{i}def; tracking=xyz; theme=dark; lang=en; "
        f"_ga=GA1.2.{i}.{i*2}; _gid=GA1.2.{i*3}.{i*4}"
        for i in range(n)
    ]

    # Warm up
    for cs in cookie_strings[:100]:
        c = SimpleCookie()
        c.load(cs)

    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for cs in cookie_strings:
            c = SimpleCookie()
            c.load(cs)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "name": "stdlib SimpleCookie",
        "n": n,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "ops_per_sec": n / statistics.median(timings),
    }


def print_result(result):
    """Pretty-print a benchmark result dict."""
    print(f"  {result['name']:>30s}: "
          f"median={result['median_s']:.4f}s  "
          f"min={result['min_s']:.4f}s  "
          f"({result['ops_per_sec']:,.0f} ops/sec)")


def main():
    n = 10_000

    print(f"C parser benchmarks ({n} iterations, 5 rounds each)")
    print("-" * 70)

    # CRequest construction
    req_result = bench_crequest_construction(n)
    print_result(req_result)

    # parse_qs
    qs_result = bench_parse_qs(n)
    print_result(qs_result)

    # stdlib comparison
    stdlib_result = bench_stdlib_parse_qs(n)
    print_result(stdlib_result)

    speedup = stdlib_result["median_s"] / qs_result["median_s"]
    print(f"\n  cruet parse_qs is {speedup:.2f}x "
          f"{'faster' if speedup > 1 else 'slower'} than stdlib parse_qs")
    print()

    # HTTP parser
    http_result = bench_http_parser(n)
    print_result(http_result)

    http_post_result = bench_http_parser_with_body(n)
    print_result(http_post_result)
    print()

    # Cookie parser
    cookie_result = bench_parse_cookies(n)
    print_result(cookie_result)

    stdlib_cookie = bench_stdlib_cookies(n)
    print_result(stdlib_cookie)

    speedup = stdlib_cookie["median_s"] / cookie_result["median_s"]
    print(f"\n  cruet parse_cookies is {speedup:.2f}x "
          f"{'faster' if speedup > 1 else 'slower'} than stdlib SimpleCookie")

    print()
    return req_result, qs_result, stdlib_result


if __name__ == "__main__":
    main()
