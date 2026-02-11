"""Routing-heavy benchmark app — 500 routes.

Tests router lookup performance under many registered routes.

Set the environment variable CRUET_USE_FLASK=1 to use Flask instead of cruet.
"""

import os

if os.environ.get("CRUET_USE_FLASK", "0") == "1":
    from flask import Flask
else:
    from cruet import Flask

app = Flask(__name__)


# Register 500 routes
for i in range(500):
    def make_handler(route_id):
        def handler():
            return f"Route {route_id}"
        handler.__name__ = f"route_{route_id}"
        return handler

    app.route(f"/route/{i}")(make_handler(i))


# Some routes with dynamic segments
for i in range(50):
    def make_dynamic_handler(prefix_id):
        def handler(item_id):
            return f"Prefix {prefix_id}, Item {item_id}"
        handler.__name__ = f"dynamic_{prefix_id}"
        return handler

    app.route(f"/dynamic/{i}/<int:item_id>")(make_dynamic_handler(i))


@app.route("/")
def index():
    return "Routing heavy benchmark — 500+ routes registered"


if __name__ == "__main__":
    if os.environ.get("CRUET_USE_FLASK", "0") == "1":
        app.run(host="127.0.0.1", port=8000)
    else:
        from cruet.serving import run
        run(app, host="127.0.0.1", port=8000)
