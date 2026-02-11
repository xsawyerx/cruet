"""Middleware chain benchmark app — 5 before + 5 after request hooks.

Tests the overhead of request lifecycle hooks.

Set the environment variable CRUET_USE_FLASK=1 to use Flask instead of cruet.
"""

import os
import time

if os.environ.get("CRUET_USE_FLASK", "0") == "1":
    from flask import Flask, g
else:
    from cruet import Flask, g

app = Flask(__name__)


# 5 before_request hooks
@app.before_request
def before_1():
    g.timing_start = time.monotonic()


@app.before_request
def before_2():
    g.request_id = "req-12345"


@app.before_request
def before_3():
    g.user = "benchmark-user"


@app.before_request
def before_4():
    g.locale = "en-US"


@app.before_request
def before_5():
    g.feature_flags = {"dark_mode": True, "beta": False}


# 5 after_request hooks
@app.after_request
def after_1(response):
    response.headers.set("X-Request-Id", g.request_id)
    return response


@app.after_request
def after_2(response):
    response.headers.set("X-User", g.user)
    return response


@app.after_request
def after_3(response):
    response.headers.set("X-Locale", g.locale)
    return response


@app.after_request
def after_4(response):
    elapsed = time.monotonic() - g.timing_start
    response.headers.set("X-Response-Time", f"{elapsed*1000:.2f}ms")
    return response


@app.after_request
def after_5(response):
    response.headers.set("X-Server", "cruet-bench")
    return response


@app.route("/")
def index():
    return "Middleware chain benchmark"


@app.route("/json")
def json_view():
    return {
        "status": "ok",
        "user": g.user,
        "locale": g.locale,
    }


@app.route("/user/<name>")
def user(name):
    return f"Hello, {name}!"


if __name__ == "__main__":
    if os.environ.get("CRUET_USE_FLASK", "0") == "1":
        app.run(host="127.0.0.1", port=8000)
    else:
        from cruet.serving import run
        run(app, host="127.0.0.1", port=8000)
