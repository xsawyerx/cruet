"""JSON API benchmark app -- works with both Flask and cruet.

Multiple routes returning JSON responses, some with URL variables.

Set the environment variable CRUET_USE_FLASK=1 to use Flask instead of cruet.
"""

import os
import json

if os.environ.get("CRUET_USE_FLASK", "0") == "1":
    from flask import Flask, jsonify
else:
    from cruet import Flask, jsonify

app = Flask(__name__)

# Fake dataset for responses
USERS = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
    3: {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
}

POSTS = [
    {"id": i, "title": f"Post {i}", "author_id": (i % 3) + 1}
    for i in range(1, 51)
]


@app.route("/")
def index():
    return jsonify(status="ok", endpoints=["/users", "/users/<id>", "/posts", "/posts/<id>"])


@app.route("/users")
def list_users():
    return jsonify(users=list(USERS.values()))


@app.route("/users/<int:user_id>")
def get_user(user_id):
    user = USERS.get(user_id)
    if user is None:
        return jsonify(error="not found"), 404
    return jsonify(user)


@app.route("/posts")
def list_posts():
    return jsonify(posts=POSTS)


@app.route("/posts/<int:post_id>")
def get_post(post_id):
    for post in POSTS:
        if post["id"] == post_id:
            return jsonify(post)
    return jsonify(error="not found"), 404


@app.route("/users/<int:user_id>/posts")
def user_posts(user_id):
    user_post_list = [p for p in POSTS if p["author_id"] == user_id]
    return jsonify(posts=user_post_list)


@app.route("/health")
def health():
    return jsonify(status="healthy")


if __name__ == "__main__":
    if os.environ.get("CRUET_USE_FLASK", "0") == "1":
        app.run(host="127.0.0.1", port=8000)
    else:
        from cruet.serving import run
        run(app, host="127.0.0.1", port=8000)
