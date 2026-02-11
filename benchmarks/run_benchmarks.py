#!/usr/bin/env python3
"""Run all cruet microbenchmarks and print a summary table.

Usage:
    python -m benchmarks.run_benchmarks
    # or
    python benchmarks/run_benchmarks.py
"""

import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def run_all():
    results = []

    print("=" * 70)
    print("  cruet Microbenchmark Suite")
    print("=" * 70)
    print()

    # ---- Routing benchmarks ------------------------------------------------
    print("[1/2] Routing benchmarks")
    print("-" * 70)
    try:
        from benchmarks.microbenchmarks.bench_routing import (
            bench_cruet_routing,
            bench_werkzeug_routing,
            print_result as print_routing_result,
        )

        cruet_routing = bench_cruet_routing()
        print_routing_result(cruet_routing)
        results.append(cruet_routing)

        werkzeug_routing = bench_werkzeug_routing()
        if werkzeug_routing is not None:
            print_routing_result(werkzeug_routing)
            results.append(werkzeug_routing)
    except Exception as exc:
        print(f"  ERROR: {exc}")
    print()

    # ---- Parsing benchmarks ------------------------------------------------
    print("[2/4] Request & query string parsing")
    print("-" * 70)
    try:
        from benchmarks.microbenchmarks.bench_parsing import (
            bench_crequest_construction,
            bench_parse_qs,
            bench_stdlib_parse_qs,
            bench_http_parser,
            bench_http_parser_with_body,
            bench_parse_cookies,
            bench_stdlib_cookies,
            print_result as print_parse_result,
        )

        req_result = bench_crequest_construction()
        print_parse_result(req_result)
        results.append({"framework": "cruet", **req_result})

        qs_result = bench_parse_qs()
        print_parse_result(qs_result)
        results.append({"framework": "cruet", **qs_result})

        stdlib_result = bench_stdlib_parse_qs()
        print_parse_result(stdlib_result)
        results.append({"framework": "stdlib", **stdlib_result})
    except Exception as exc:
        print(f"  ERROR: {exc}")
    print()

    # ---- HTTP parser benchmarks --------------------------------------------
    print("[3/4] HTTP parser")
    print("-" * 70)
    try:
        http_result = bench_http_parser()
        print_parse_result(http_result)
        results.append({"framework": "cruet", **http_result})

        http_post_result = bench_http_parser_with_body()
        print_parse_result(http_post_result)
        results.append({"framework": "cruet", **http_post_result})
    except Exception as exc:
        print(f"  ERROR: {exc}")
    print()

    # ---- Cookie parser benchmarks ------------------------------------------
    print("[4/4] Cookie parsing")
    print("-" * 70)
    try:
        cookie_result = bench_parse_cookies()
        print_parse_result(cookie_result)
        results.append({"framework": "cruet", **cookie_result})

        stdlib_cookie = bench_stdlib_cookies()
        print_parse_result(stdlib_cookie)
        results.append({"framework": "stdlib", **stdlib_cookie})
    except Exception as exc:
        print(f"  ERROR: {exc}")
    print()

    # ---- Summary table ------------------------------------------------------
    print("=" * 70)
    print("  Summary")
    print("=" * 70)
    print()
    print(f"  {'Benchmark':<30s} {'Median (s)':>12s} {'Ops/sec':>14s}")
    print(f"  {'-' * 30} {'-' * 12} {'-' * 14}")

    for r in results:
        name = r.get("name", r.get("framework", "?"))
        median = r.get("median_s", 0)
        ops = r.get("ops_per_sec", r.get("matches_per_sec", 0))
        print(f"  {name:<30s} {median:>12.4f} {ops:>14,.0f}")

    print()
    print("Done.")


if __name__ == "__main__":
    run_all()
