#!/bin/bash
# End-to-end benchmark: cruet async server vs Flask+Gunicorn
# Requires: wrk, gunicorn, flask, cruet

set -e

WRK_THREADS=4
WRK_CONNECTIONS=100
FLASK_WRK_CONNECTIONS=${FLASK_WRK_CONNECTIONS:-50}
WRK_DURATION=10s
COOLDOWN_SECS=${COOLDOWN_SECS:-2}
READY_SUCCESS_COUNT=${READY_SUCCESS_COUNT:-3}
PORT=8111
GUNICORN=$(python -c "import shutil; print(shutil.which('gunicorn'))")
RESULTS_FILE="benchmarks/results_$(date +%Y%m%d_%H%M%S).txt"

HAS_GUNICORN=0
HAS_FLASK=0

if [ -n "$GUNICORN" ] && [ -x "$GUNICORN" ]; then
    HAS_GUNICORN=1
fi

if python -c "import flask" >/dev/null 2>&1; then
    HAS_FLASK=1
fi

RUN_FLASK_BASELINE=0
if [ "$HAS_GUNICORN" -eq 1 ] && [ "$HAS_FLASK" -eq 1 ]; then
    RUN_FLASK_BASELINE=1
fi

wait_for_server() {
    local port=$1
    local max_attempts=60
    local consecutive_ok=0
    for i in $(seq 1 $max_attempts); do
        if curl -s "http://127.0.0.1:$port/" > /dev/null 2>&1; then
            consecutive_ok=$((consecutive_ok + 1))
            if [ "$consecutive_ok" -ge "$READY_SUCCESS_COUNT" ]; then
                return 0
            fi
        else
            consecutive_ok=0
        fi
        sleep 0.2
    done
    echo "ERROR: Server on port $port did not start in time"
    return 1
}

kill_server() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    # Also kill anything on our port
    lsof -ti :$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 0.5
}

run_bench() {
    local label=$1
    local url=$2
    local connections=${3:-$WRK_CONNECTIONS}
    echo ""
    echo "=== $label ==="
    echo "--- wrk -t$WRK_THREADS -c$connections -d$WRK_DURATION $url ---"
    wrk -t$WRK_THREADS -c$connections -d$WRK_DURATION "$url" 2>&1
    sleep "$COOLDOWN_SECS"
}

echo "================================================================"
echo "  cruet End-to-End Benchmarks"
echo "  $(date)"
echo "  wrk: -t$WRK_THREADS -c$WRK_CONNECTIONS -d$WRK_DURATION"
echo "  flask baseline wrk connections: $FLASK_WRK_CONNECTIONS"
echo "  cooldown between runs: ${COOLDOWN_SECS}s"
echo "================================================================"

if [ "$HAS_GUNICORN" -ne 1 ]; then
    echo "NOTE: gunicorn not found; skipping gunicorn-based benchmarks."
fi
if [ "$HAS_FLASK" -ne 1 ]; then
    echo "NOTE: flask not installed; skipping Flask+Gunicorn baseline benchmarks."
fi

# Make sure port is free
kill_server

########################################
# Benchmark 1: cruet async server - hello world
########################################
echo ""
echo "Starting cruet async server (hello_world)..."
python -m cruet run benchmarks.apps.hello_world:app --host 127.0.0.1 --port $PORT --workers 1 &
SERVER_PID=$!
wait_for_server $PORT

run_bench "cruet async (1 worker) - hello_world /" "http://127.0.0.1:$PORT/"
kill_server

########################################
# Benchmark 2: cruet async server - hello world, 4 workers
########################################
echo ""
echo "Starting cruet async server (hello_world, 4 workers)..."
python -m cruet run benchmarks.apps.hello_world:app --host 127.0.0.1 --port $PORT --workers 4 &
SERVER_PID=$!
wait_for_server $PORT

run_bench "cruet async (4 workers) - hello_world /" "http://127.0.0.1:$PORT/"
kill_server

########################################
# Benchmark 3: Flask + Gunicorn - hello world
########################################
if [ "$RUN_FLASK_BASELINE" -eq 1 ]; then
    echo ""
    echo "Starting Flask + Gunicorn (hello_world, 4 workers)..."
    CRUET_USE_FLASK=1 $GUNICORN benchmarks.apps.hello_world:app -w 4 -b 127.0.0.1:$PORT --log-level error &
    SERVER_PID=$!
    wait_for_server $PORT

    run_bench "Flask + Gunicorn (4 workers) - hello_world /" "http://127.0.0.1:$PORT/" "$FLASK_WRK_CONNECTIONS"
    kill_server
fi

########################################
# Benchmark 4: cruet app + Gunicorn - hello world
########################################
if [ "$HAS_GUNICORN" -eq 1 ]; then
    echo ""
    echo "Starting cruet app + Gunicorn (hello_world, 4 workers)..."
    $GUNICORN benchmarks.apps.hello_world:app -w 4 -b 127.0.0.1:$PORT --log-level error &
    SERVER_PID=$!
    wait_for_server $PORT

    run_bench "cruet + Gunicorn (4 workers) - hello_world /" "http://127.0.0.1:$PORT/"
    kill_server
fi

########################################
# Benchmark 5: cruet async - JSON API
########################################
echo ""
echo "Starting cruet async server (json_api, 4 workers)..."
python -m cruet run benchmarks.apps.json_api:app --host 127.0.0.1 --port $PORT --workers 4 &
SERVER_PID=$!
wait_for_server $PORT

run_bench "cruet async (4 workers) - json_api /" "http://127.0.0.1:$PORT/"
run_bench "cruet async (4 workers) - json_api /users" "http://127.0.0.1:$PORT/users"
run_bench "cruet async (4 workers) - json_api /users/1" "http://127.0.0.1:$PORT/users/1"
kill_server

########################################
# Benchmark 6: Flask + Gunicorn - JSON API
########################################
if [ "$RUN_FLASK_BASELINE" -eq 1 ]; then
    echo ""
    echo "Starting Flask + Gunicorn (json_api, 4 workers)..."
    CRUET_USE_FLASK=1 $GUNICORN benchmarks.apps.json_api:app -w 4 -b 127.0.0.1:$PORT --log-level error &
    SERVER_PID=$!
    wait_for_server $PORT

    run_bench "Flask + Gunicorn (4 workers) - json_api /" "http://127.0.0.1:$PORT/" "$FLASK_WRK_CONNECTIONS"
    run_bench "Flask + Gunicorn (4 workers) - json_api /users" "http://127.0.0.1:$PORT/users" "$FLASK_WRK_CONNECTIONS"
    run_bench "Flask + Gunicorn (4 workers) - json_api /users/1" "http://127.0.0.1:$PORT/users/1" "$FLASK_WRK_CONNECTIONS"
    kill_server
fi

########################################
# Benchmark 7: cruet async - routing heavy
########################################
echo ""
echo "Starting cruet async server (routing_heavy, 4 workers)..."
python -m cruet run benchmarks.apps.routing_heavy:app --host 127.0.0.1 --port $PORT --workers 4 &
SERVER_PID=$!
wait_for_server $PORT

run_bench "cruet async (4 workers) - routing_heavy /route/0" "http://127.0.0.1:$PORT/route/0"
run_bench "cruet async (4 workers) - routing_heavy /route/499" "http://127.0.0.1:$PORT/route/499"
run_bench "cruet async (4 workers) - routing_heavy /dynamic/25/42" "http://127.0.0.1:$PORT/dynamic/25/42"
kill_server

########################################
# Benchmark 8: Flask + Gunicorn - routing heavy
########################################
if [ "$RUN_FLASK_BASELINE" -eq 1 ]; then
    echo ""
    echo "Starting Flask + Gunicorn (routing_heavy, 4 workers)..."
    CRUET_USE_FLASK=1 $GUNICORN benchmarks.apps.routing_heavy:app -w 4 -b 127.0.0.1:$PORT --log-level error &
    SERVER_PID=$!
    wait_for_server $PORT

    run_bench "Flask + Gunicorn (4 workers) - routing_heavy /route/0" "http://127.0.0.1:$PORT/route/0" "$FLASK_WRK_CONNECTIONS"
    run_bench "Flask + Gunicorn (4 workers) - routing_heavy /route/499" "http://127.0.0.1:$PORT/route/499" "$FLASK_WRK_CONNECTIONS"
    run_bench "Flask + Gunicorn (4 workers) - routing_heavy /dynamic/25/42" "http://127.0.0.1:$PORT/dynamic/25/42" "$FLASK_WRK_CONNECTIONS"
    kill_server
fi

########################################
# Benchmark 9: cruet async - middleware chain
########################################
echo ""
echo "Starting cruet async server (middleware_chain, 4 workers)..."
python -m cruet run benchmarks.apps.middleware_chain:app --host 127.0.0.1 --port $PORT --workers 4 &
SERVER_PID=$!
wait_for_server $PORT

run_bench "cruet async (4 workers) - middleware_chain /" "http://127.0.0.1:$PORT/"
run_bench "cruet async (4 workers) - middleware_chain /json" "http://127.0.0.1:$PORT/json"
kill_server

########################################
# Benchmark 10: Flask + Gunicorn - middleware chain
########################################
if [ "$RUN_FLASK_BASELINE" -eq 1 ]; then
    echo ""
    echo "Starting Flask + Gunicorn (middleware_chain, 4 workers)..."
    CRUET_USE_FLASK=1 $GUNICORN benchmarks.apps.middleware_chain:app -w 4 -b 127.0.0.1:$PORT --log-level error &
    SERVER_PID=$!
    wait_for_server $PORT

    run_bench "Flask + Gunicorn (4 workers) - middleware_chain /" "http://127.0.0.1:$PORT/" "$FLASK_WRK_CONNECTIONS"
    run_bench "Flask + Gunicorn (4 workers) - middleware_chain /json" "http://127.0.0.1:$PORT/json" "$FLASK_WRK_CONNECTIONS"
    kill_server
fi

echo ""
echo "================================================================"
echo "  Benchmarks complete"
echo "================================================================"
