"""Hello World benchmark app -- works with both Flask and cruet.

Set the environment variable CRUET_USE_FLASK=1 to use Flask instead of cruet.

Usage:
    # cruet (default)
    python -m cruet run benchmarks.apps.hello_world:app

    # Flask
    CRUET_USE_FLASK=1 flask --app benchmarks.apps.hello_world:app run
"""

import os

if os.environ.get("CRUET_USE_FLASK", "0") == "1":
    from flask import Flask
else:
    from cruet import Flask

app = Flask(__name__)


@app.route("/")
def hello():
    return "Hello, World!"


if __name__ == "__main__":
    if os.environ.get("CRUET_USE_FLASK", "0") == "1":
        app.run(host="127.0.0.1", port=8000)
    else:
        from cruet.serving import run
        run(app, host="127.0.0.1", port=8000)
