"""Integration tests ported from flask-examples/.

Each class re-implements one flask-example app using cruet imports and then
exercises the same behaviour the original app demonstrates.

Apps covered:
  - hello/app.py     (TestHelloApp)
  - http/app.py      (TestHttpApp)
  - template/app.py  (TestTemplateApp)
"""

import html
import json
import os

import pytest
from markupsafe import Markup

from urllib.parse import urlparse, urljoin

from cruet import (
    Flask,
    abort,
    flash,
    get_flashed_messages,
    jsonify,
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    session,
    url_for,
)


# ---------------------------------------------------------------------------
# hello/app.py
# ---------------------------------------------------------------------------

def _make_hello_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return "<h1>Hello, World!</h1>"

    @app.route("/hi")
    @app.route("/hello")
    def say_hello():
        return "<h1>Hello, Flask!</h1>"

    @app.route("/greet", defaults={"name": "Programmer"})
    @app.route("/greet/<name>")
    def greet(name):
        return "<h1>Hello, %s!</h1>" % name

    @app.cli.command()
    def hello():
        """Say hello."""
        return "Hello, Human!"

    return app


class TestHelloApp:
    """Tests derived from flask-examples/hello/app.py."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.app = _make_hello_app()
        self.client = self.app.test_client()

    def test_index(self):
        resp = self.client.get("/")
        assert resp.status_code == 200
        assert resp.text == "<h1>Hello, World!</h1>"

    def test_multiple_routes_hi(self):
        resp = self.client.get("/hi")
        assert resp.status_code == 200
        assert resp.text == "<h1>Hello, Flask!</h1>"

    def test_multiple_routes_hello(self):
        resp = self.client.get("/hello")
        assert resp.status_code == 200
        assert resp.text == "<h1>Hello, Flask!</h1>"

    def test_greet_with_name(self):
        resp = self.client.get("/greet/Sawyer")
        assert resp.status_code == 200
        assert resp.text == "<h1>Hello, Sawyer!</h1>"

    def test_greet_default(self):
        """The original app maps /greet with defaults={'name': 'Programmer'}."""
        resp = self.client.get("/greet")
        assert resp.status_code == 200
        assert resp.text == "<h1>Hello, Programmer!</h1>"

    def test_cli_hello_command(self):
        """@app.cli.command() registers a callable CLI command."""
        assert "hello" in self.app.cli
        assert self.app.cli["hello"] is not None


# ---------------------------------------------------------------------------
# http/app.py
# ---------------------------------------------------------------------------

def _make_http_app():
    app = Flask(__name__)
    app.secret_key = "integration-test-secret"

    @app.route("/")
    @app.route("/hello")
    def hello():
        name = request.args.get("name")
        if name is None:
            name = request.cookies.get("name", "Human")
        response_text = "<h1>Hello, %s!</h1>" % html.escape(name)
        if "logged_in" in session:
            response_text += "[Authenticated]"
        else:
            response_text += "[Not Authenticated]"
        return response_text

    @app.route("/hi")
    def hi():
        return redirect(url_for("hello"))

    @app.route("/goback/<int:year>")
    def go_back(year):
        return "Welcome to %d!" % (2018 - year)

    @app.route("/colors/<any(blue,white,red):color>")
    def three_colors(color):
        return (
            "<p>Love is patient and kind. "
            "Love is not jealous or boastful or proud or rude.</p>"
        )

    @app.route("/brew/<drink>")
    def teapot(drink):
        if drink == "coffee":
            abort(418)
        else:
            return "A drop of tea."

    @app.route("/404")
    def not_found():
        abort(404)

    @app.route("/note", defaults={"content_type": "text"})
    @app.route("/note/<content_type>")
    def note(content_type):
        content_type = content_type.lower()
        if content_type == "text":
            body = (
                "Note\n"
                "to: Peter\n"
                "from: Jane\n"
                "heading: Reminder\n"
                "body: Don't forget the party!\n"
            )
            resp = make_response(body)
            resp.content_type = "text/plain"
        elif content_type == "html":
            body = (
                "<!DOCTYPE html>\n"
                "<html>\n"
                "<head></head>\n"
                "<body>\n"
                "  <h1>Note</h1>\n"
                "  <p>to: Peter</p>\n"
                "  <p>from: Jane</p>\n"
                "  <p>heading: Reminder</p>\n"
                "  <p>body: <strong>Don't forget the party!</strong></p>\n"
                "</body>\n"
                "</html>\n"
            )
            resp = make_response(body)
            resp.content_type = "text/html"
        elif content_type == "xml":
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<note>\n"
                "  <to>Peter</to>\n"
                "  <from>Jane</from>\n"
                "  <heading>Reminder</heading>\n"
                "  <body>Don't forget the party!</body>\n"
                "</note>\n"
            )
            resp = make_response(body)
            resp.content_type = "application/xml"
        elif content_type == "json":
            body = {
                "note": {
                    "to": "Peter",
                    "from": "Jane",
                    "heading": "Remider",
                    "body": "Don't forget the party!",
                }
            }
            resp = jsonify(body)
        else:
            abort(400)
        return resp

    @app.route("/set/<name>")
    def set_cookie(name):
        resp = make_response(redirect(url_for("hello")))
        resp.set_cookie("name", name)
        return resp

    @app.route("/login")
    def login():
        session["logged_in"] = True
        return redirect(url_for("hello"))

    @app.route("/admin")
    def admin():
        if "logged_in" not in session:
            abort(403)
        return "Welcome to admin page."

    @app.route("/logout")
    def logout():
        if "logged_in" in session:
            session.pop("logged_in")
        return redirect(url_for("hello"))

    @app.route("/json")
    def json_view():
        return jsonify(name="Grey Li", message={"text": "Hello!"})

    # AJAX: /post renders a page with Lorem Ipsum, /more returns more text
    @app.route("/post")
    def show_post():
        from jinja2.utils import generate_lorem_ipsum
        post_body = generate_lorem_ipsum(n=2)
        return (
            '<h1>A very long post</h1>'
            '<div class="body">%s</div>'
            '<button id="load">Load More</button>' % post_body
        )

    @app.route("/more")
    def load_post():
        from jinja2.utils import generate_lorem_ipsum
        return generate_lorem_ipsum(n=1)

    # Redirect-back: /foo and /bar link to /do-something which redirects back.
    # Faithful port of the original's is_safe_url / redirect_back helpers.
    def _host_url():
        return request.scheme + "://" + request.host + "/"

    def _is_safe_url(target):
        ref_url = urlparse(_host_url())
        test_url = urlparse(urljoin(_host_url(), target))
        return test_url.scheme in ("http", "https") and \
               ref_url.netloc == test_url.netloc

    def _redirect_back(default="hello", **kwargs):
        for target in request.args.get("next"), request.referrer:
            if not target:
                continue
            if _is_safe_url(target):
                return redirect(target)
        return redirect(url_for(default, **kwargs))

    @app.route("/foo")
    def foo():
        return '<h1>Foo page</h1><a href="%s">Do something</a>' \
               % url_for("do_something", next=request.full_path)

    @app.route("/bar")
    def bar():
        return '<h1>Bar page</h1><a href="%s">Do something</a>' \
               % url_for("do_something", next=request.full_path)

    @app.route("/do-something")
    def do_something():
        return _redirect_back()

    return app


class TestHttpApp:
    """Tests derived from flask-examples/http/app.py."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.app = _make_http_app()
        self.client = self.app.test_client()

    # -- /hello --------------------------------------------------------

    def test_hello_default_name(self):
        resp = self.client.get("/hello")
        assert resp.status_code == 200
        assert "Hello, Human!" in resp.text
        assert "[Not Authenticated]" in resp.text

    def test_hello_query_name(self):
        resp = self.client.get("/hello?name=Alice")
        assert resp.status_code == 200
        assert "Hello, Alice!" in resp.text

    def test_hello_cookie_name(self):
        resp = self.client.get(
            "/hello", headers={"Cookie": "name=CookieMonster"}
        )
        assert resp.status_code == 200
        assert "Hello, CookieMonster!" in resp.text

    def test_hello_query_overrides_cookie(self):
        """Query-string name takes precedence over cookie name."""
        resp = self.client.get(
            "/hello?name=QueryName",
            headers={"Cookie": "name=CookieName"},
        )
        assert resp.status_code == 200
        assert "Hello, QueryName!" in resp.text

    # -- /hi -----------------------------------------------------------

    def test_redirect_hi_to_hello(self):
        resp = self.client.get("/hi")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/hello"

    # -- /goback/<int:year> --------------------------------------------

    def test_int_converter_goback(self):
        resp = self.client.get("/goback/2")
        assert resp.status_code == 200
        assert resp.text == "Welcome to 2016!"

    # -- /colors/<any(blue,white,red):color> ---------------------------

    def test_any_converter_valid(self):
        for color in ("blue", "white", "red"):
            resp = self.client.get(f"/colors/{color}")
            assert resp.status_code == 200
            assert "Love is patient" in resp.text

    def test_any_converter_invalid(self):
        resp = self.client.get("/colors/green")
        assert resp.status_code == 404

    # -- /brew/<drink> -------------------------------------------------

    def test_abort_418_teapot(self):
        resp = self.client.get("/brew/coffee")
        assert resp.status_code == 418

    def test_brew_tea_ok(self):
        resp = self.client.get("/brew/tea")
        assert resp.status_code == 200
        assert resp.text == "A drop of tea."

    # -- /404 ----------------------------------------------------------

    def test_abort_404(self):
        resp = self.client.get("/404")
        assert resp.status_code == 404

    # -- /note/<content_type> ------------------------------------------

    def test_note_text(self):
        resp = self.client.get("/note/text")
        assert resp.status_code == 200
        assert "text/plain" in resp.get_header("Content-Type")
        assert "to: Peter" in resp.text

    def test_note_html(self):
        resp = self.client.get("/note/html")
        assert resp.status_code == 200
        assert "text/html" in resp.get_header("Content-Type")
        assert "<h1>Note</h1>" in resp.text

    def test_note_xml(self):
        resp = self.client.get("/note/xml")
        assert resp.status_code == 200
        assert "application/xml" in resp.get_header("Content-Type")
        assert "<to>Peter</to>" in resp.text

    def test_note_json(self):
        resp = self.client.get("/note/json")
        assert resp.status_code == 200
        assert "application/json" in resp.get_header("Content-Type")
        data = resp.json
        assert data["note"]["to"] == "Peter"
        # Match original typo in flask-examples/http/app.py
        assert data["note"]["heading"] == "Remider"

    def test_note_invalid_400(self):
        resp = self.client.get("/note/yaml")
        assert resp.status_code == 400

    def test_note_default_text(self):
        """GET /note should default to content_type='text'."""
        resp = self.client.get("/note")
        assert resp.status_code == 200
        assert "text/plain" in resp.get_header("Content-Type")
        assert "to: Peter" in resp.text

    # -- /set/<name> ---------------------------------------------------

    def test_set_cookie_redirect(self):
        resp = self.client.get("/set/Alice")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/hello"

    def test_set_cookie_header(self):
        resp = self.client.get("/set/Alice")
        set_cookie = resp.get_header("Set-Cookie")
        assert set_cookie is not None
        assert "name=Alice" in set_cookie

    # -- /post, /more (AJAX) ------------------------------------------

    def test_post_page(self):
        resp = self.client.get("/post")
        assert resp.status_code == 200
        assert "<h1>A very long post</h1>" in resp.text
        assert "Load More" in resp.text

    def test_more_returns_text(self):
        resp = self.client.get("/more")
        assert resp.status_code == 200
        assert len(resp.text) > 0

    # -- /foo, /bar, /do-something (redirect-back) --------------------

    def test_foo_page(self):
        resp = self.client.get("/foo")
        assert resp.status_code == 200
        assert "Foo page" in resp.text
        assert "/do-something" in resp.text

    def test_bar_page(self):
        resp = self.client.get("/bar")
        assert resp.status_code == 200
        assert "Bar page" in resp.text
        assert "/do-something" in resp.text

    def test_do_something_redirects_back_via_next(self):
        """?next= with a same-origin path redirects there."""
        resp = self.client.get("/do-something?next=/foo")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/foo"

    def test_do_something_redirects_back_via_referrer(self):
        """Without ?next, falls back to the Referer header."""
        resp = self.client.get(
            "/do-something", headers={"Referer": "http://localhost/bar"}
        )
        assert resp.status_code == 302
        assert resp.get_header("Location") == "http://localhost/bar"

    def test_do_something_rejects_foreign_next(self):
        """A ?next pointing to another host is rejected (safe-URL check)."""
        resp = self.client.get(
            "/do-something?next=http://evil.com/steal"
        )
        assert resp.status_code == 302
        # Falls through to default
        assert resp.get_header("Location") == "/hello"

    def test_do_something_default_redirect(self):
        """With no ?next and no Referer, redirects to /hello."""
        resp = self.client.get("/do-something")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/hello"

    # -- /json ---------------------------------------------------------

    def test_jsonify(self):
        resp = self.client.get("/json")
        assert resp.status_code == 200
        assert "application/json" in resp.get_header("Content-Type")
        data = resp.json
        assert data["name"] == "Grey Li"
        assert data["message"]["text"] == "Hello!"

    # -- /login, /admin, /logout (session) -----------------------------

    def test_login_redirects(self):
        resp = self.client.get("/login")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/hello"

    def test_admin_no_auth_403(self):
        resp = self.client.get("/admin")
        assert resp.status_code == 403

    def test_session_login_admin_logout(self):
        """Full login -> admin -> logout flow with manual cookie passing."""
        # Login
        resp1 = self.client.get("/login")
        assert resp1.status_code == 302
        session_cookie = resp1.get_header("Set-Cookie").split(";")[0]

        # Admin should succeed with session cookie
        resp2 = self.client.get(
            "/admin", headers={"Cookie": session_cookie}
        )
        assert resp2.status_code == 200
        assert resp2.text == "Welcome to admin page."

        # Logout
        resp3 = self.client.get(
            "/logout", headers={"Cookie": session_cookie}
        )
        assert resp3.status_code == 302

        # After logout, admin should 403 again.
        # Use the new session cookie from logout response.
        logout_cookie = resp3.get_header("Set-Cookie")
        if logout_cookie:
            logout_cookie = logout_cookie.split(";")[0]
            resp4 = self.client.get(
                "/admin", headers={"Cookie": logout_cookie}
            )
        else:
            resp4 = self.client.get("/admin")
        assert resp4.status_code == 403


# ---------------------------------------------------------------------------
# template/app.py
# ---------------------------------------------------------------------------

# Point at the in-repo template fixture copied from flask-examples so test
# runs are self-contained for anyone cloning this repo.
_TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, "templates",
)


def _make_template_app():
    app = Flask(__name__)
    app.secret_key = "template-test-secret"
    app.template_folder = os.path.abspath(_TEMPLATE_DIR)

    user = {
        "username": "Grey Li",
        "bio": "A boy who loves movies and music.",
    }

    movies = [
        {"name": "My Neighbor Totoro", "year": "1988"},
        {"name": "Three Colours trilogy", "year": "1993"},
        {"name": "Forrest Gump", "year": "1994"},
        {"name": "Perfect Blue", "year": "1997"},
        {"name": "The Matrix", "year": "1999"},
        {"name": "Memento", "year": "2000"},
        {"name": "The Bucket list", "year": "2007"},
        {"name": "Black Swan", "year": "2010"},
        {"name": "Gone Girl", "year": "2014"},
        {"name": "CoCo", "year": "2017"},
    ]

    @app.route("/watchlist")
    def watchlist():
        return render_template("watchlist.html", user=user, movies=movies)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/watchlist2")
    def watchlist_with_static():
        return render_template("watchlist_with_static.html", user=user, movies=movies)

    # register template context handler
    @app.context_processor
    def inject_info():
        foo = "I am foo."
        return dict(foo=foo)

    # register template global function
    @app.template_global()
    def bar():
        return "I am bar."

    # register template filter
    @app.template_filter()
    def musical(s):
        return s + Markup(" &#9835;")

    # register template test (via jinja_env directly — cruet does not
    # expose a template_test() decorator)
    app.jinja_env.tests["baz"] = lambda n: n == "baz"

    # message flashing
    @app.route("/flash")
    def just_flash():
        flash("I am flash, who is looking for me?")
        return redirect(url_for("index"))

    # 404 error handler
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    # 500 error handler
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("errors/500.html"), 500

    # Route that intentionally raises to exercise the 500 handler
    @app.route("/boom")
    def boom():
        raise RuntimeError("intentional error")

    return app


class TestTemplateApp:
    """Tests derived from flask-examples/template/app.py."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.app = _make_template_app()
        self.client = self.app.test_client()

    # -- / (index) -----------------------------------------------------

    def test_index(self):
        resp = self.client.get("/")
        assert resp.status_code == 200
        assert "Template" in resp.text

    def test_index_context_processor(self):
        """context_processor injects 'foo', filter 'musical' adds ♫."""
        resp = self.client.get("/")
        assert "I am foo." in resp.text
        assert "&#9835;" in resp.text

    def test_index_template_global(self):
        """template_global bar() is callable from the template."""
        resp = self.client.get("/")
        assert "I am bar." in resp.text

    def test_index_template_test(self):
        """Custom Jinja2 test 'baz' works: {% if name is baz %}."""
        resp = self.client.get("/")
        assert "I am baz." in resp.text

    def test_index_macro(self):
        """Macro qux() imported from macros.html works."""
        resp = self.client.get("/")
        assert "I am qux." in resp.text

    # -- /watchlist ----------------------------------------------------

    def test_watchlist(self):
        resp = self.client.get("/watchlist")
        assert resp.status_code == 200
        assert "Grey Li" in resp.text

    def test_watchlist_movies(self):
        """All 10 movies are rendered."""
        resp = self.client.get("/watchlist")
        assert "My Neighbor Totoro" in resp.text
        assert "CoCo" in resp.text
        assert "Watchlist (10)" in resp.text

    def test_watchlist_bio(self):
        resp = self.client.get("/watchlist")
        assert "A boy who loves movies and music." in resp.text

    # -- /flash --------------------------------------------------------

    def test_flash_redirect(self):
        resp = self.client.get("/flash")
        assert resp.status_code == 302
        assert resp.get_header("Location") == "/"

    # -- error handlers ------------------------------------------------

    def test_404_error_handler(self):
        resp = self.client.get("/nonexistent")
        assert resp.status_code == 404
        assert "Page Not Found" in resp.text

    def test_500_error_handler(self):
        resp = self.client.get("/boom")
        assert resp.status_code == 500
        assert "Internal Server Error" in resp.text
        assert "Something was wrong" in resp.text

    # -- /watchlist2 ---------------------------------------------------

    def test_watchlist_with_static(self):
        """watchlist2 renders the static-assets variant of the watchlist."""
        resp = self.client.get("/watchlist2")
        assert resp.status_code == 200
        assert "Grey Li" in resp.text
        assert "Watchlist Pro" in resp.text

    def test_watchlist2_movies(self):
        resp = self.client.get("/watchlist2")
        assert "My Neighbor Totoro" in resp.text
        assert "CoCo" in resp.text

    def test_watchlist2_static_asset_url(self):
        """watchlist_with_static.html references a static avatar image."""
        resp = self.client.get("/watchlist2")
        assert "/static/avatar.jpg" in resp.text

    # -- /flash (message appears in template) --------------------------

    def test_flash_message_in_template(self):
        """Flash message is rendered via get_flashed_messages() in base.html."""
        # Step 1: flash a message (this sets it in the session)
        resp1 = self.client.get("/flash")
        assert resp1.status_code == 302
        cookie = resp1.get_header("Set-Cookie").split(";")[0]

        # Step 2: follow the redirect — the flashed message should render
        resp2 = self.client.get("/", headers={"Cookie": cookie})
        assert resp2.status_code == 200
        assert "I am flash, who is looking for me?" in resp2.text

    # -- misc ----------------------------------------------------------

    def test_links_in_index(self):
        """Index page contains links to watchlist and flash."""
        resp = self.client.get("/")
        assert "/watchlist" in resp.text
        assert "/flash" in resp.text
