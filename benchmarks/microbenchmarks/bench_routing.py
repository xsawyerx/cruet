"""Microbenchmark: URL routing performance.

Creates a Map with 100 rules and times match operations.
Optionally compares cruet._cruet.Map against werkzeug.routing.Map.
"""

import time
import statistics
import sys


def bench_cruet_routing(n_rules=100, n_matches=10_000):
    """Benchmark cruet C-extension routing."""
    from cruet._cruet import Rule, Map

    url_map = Map()
    for i in range(n_rules):
        url_map.add(Rule(f"/route{i}/<name>", endpoint=f"view_{i}"))
    adapter = url_map.bind("localhost")

    # Warm up
    for i in range(min(100, n_rules)):
        adapter.match(f"/route{i}/alice", method="GET")

    # Timed run
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for i in range(n_matches):
            idx = i % n_rules
            adapter.match(f"/route{idx}/user{i}", method="GET")
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "framework": "cruet",
        "n_rules": n_rules,
        "n_matches": n_matches,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "matches_per_sec": n_matches / statistics.median(timings),
    }


def bench_werkzeug_routing(n_rules=100, n_matches=10_000):
    """Benchmark werkzeug routing (for comparison)."""
    try:
        from werkzeug.routing import Rule, Map
    except ImportError:
        return None

    url_map = Map([
        Rule(f"/route{i}/<name>", endpoint=f"view_{i}")
        for i in range(n_rules)
    ])
    adapter = url_map.bind("localhost")

    # Warm up
    for i in range(min(100, n_rules)):
        adapter.match(f"/route{i}/alice", method="GET")

    # Timed run
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        for i in range(n_matches):
            idx = i % n_rules
            adapter.match(f"/route{idx}/user{i}", method="GET")
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    return {
        "framework": "werkzeug",
        "n_rules": n_rules,
        "n_matches": n_matches,
        "min_s": min(timings),
        "median_s": statistics.median(timings),
        "mean_s": statistics.mean(timings),
        "matches_per_sec": n_matches / statistics.median(timings),
    }


def print_result(result):
    """Pretty-print a benchmark result dict."""
    if result is None:
        return
    print(f"  {result['framework']:>10s}: "
          f"median={result['median_s']:.4f}s  "
          f"min={result['min_s']:.4f}s  "
          f"({result['matches_per_sec']:,.0f} matches/sec)")


def main():
    n_rules = 100
    n_matches = 10_000

    print(f"Routing benchmark: {n_rules} rules, {n_matches} match operations (5 rounds)")
    print("-" * 70)

    cruet_result = bench_cruet_routing(n_rules, n_matches)
    print_result(cruet_result)

    werkzeug_result = bench_werkzeug_routing(n_rules, n_matches)
    if werkzeug_result is not None:
        print_result(werkzeug_result)
        speedup = werkzeug_result["median_s"] / cruet_result["median_s"]
        print(f"\n  cruet is {speedup:.2f}x {'faster' if speedup > 1 else 'slower'} "
              f"than werkzeug routing")
    else:
        print("  werkzeug not installed -- skipping comparison")

    print()
    return cruet_result, werkzeug_result


if __name__ == "__main__":
    main()
