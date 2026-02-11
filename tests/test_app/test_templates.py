"""Tests for Jinja2 template rendering."""
import os
import tempfile
import pytest
from cruet import Cruet, render_template, render_template_string, session


class TestRenderTemplateString:
    def test_simple_variable(self):
        app = Cruet(__name__)
        with app.test_request_context():
            result = render_template_string("Hello {{ name }}!", name="Alice")
            assert result == "Hello Alice!"

    def test_multiple_variables(self):
        app = Cruet(__name__)
        with app.test_request_context():
            result = render_template_string(
                "{{ a }} + {{ b }} = {{ a + b }}", a=2, b=3)
            assert result == "2 + 3 = 5"

    def test_conditional(self):
        app = Cruet(__name__)
        with app.test_request_context():
            tmpl = "{% if show %}visible{% else %}hidden{% endif %}"
            assert render_template_string(tmpl, show=True) == "visible"
            assert render_template_string(tmpl, show=False) == "hidden"

    def test_loop(self):
        app = Cruet(__name__)
        with app.test_request_context():
            tmpl = "{% for i in items %}{{ i }},{% endfor %}"
            result = render_template_string(tmpl, items=[1, 2, 3])
            assert result == "1,2,3,"

    def test_no_variables(self):
        app = Cruet(__name__)
        with app.test_request_context():
            result = render_template_string("plain text")
            assert result == "plain text"

    def test_html_autoescaped(self):
        app = Cruet(__name__)
        with app.test_request_context():
            result = render_template_string("{{ x }}", x="<b>bold</b>")
            # Autoescaping is on by default (safe default, matches Flask)
            assert "&lt;b&gt;" in result
            assert "<b>bold</b>" not in result


class TestContextInjection:
    def test_request_available(self):
        app = Cruet(__name__)

        @app.route("/test")
        def test_view():
            return render_template_string("{{ request.method }}")

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "GET"

    def test_config_available(self):
        app = Cruet(__name__)
        app.config["MY_VAR"] = "hello"

        @app.route("/test")
        def test_view():
            return render_template_string("{{ config.MY_VAR }}")

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "hello"

    def test_session_available(self):
        app = Cruet(__name__)
        app.secret_key = "test"

        @app.route("/test")
        def test_view():
            session["user"] = "alice"
            return render_template_string("{{ session.user }}")

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "alice"

    def test_g_available(self):
        app = Cruet(__name__)

        @app.before_request
        def set_g():
            from cruet import g
            g.value = 42

        @app.route("/test")
        def test_view():
            return render_template_string("{{ g.value }}")

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "42"

    def test_url_for_available(self):
        app = Cruet(__name__)

        @app.route("/hello/<name>")
        def hello(name):
            pass

        @app.route("/test")
        def test_view():
            return render_template_string("{{ url_for('hello', name='alice') }}")

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "/hello/alice"

    def test_explicit_context_overrides(self):
        app = Cruet(__name__)

        @app.route("/test")
        def test_view():
            return render_template_string(
                "{{ custom }}", custom="my_value")

        client = app.test_client()
        resp = client.get("/test")
        assert resp.text == "my_value"


class TestRenderTemplateFile:
    def test_render_from_file(self, tmp_path):
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        (tmpl_dir / "hello.html").write_text("<p>Hello {{ name }}!</p>")

        app = Cruet(__name__, template_folder=str(tmpl_dir))
        with app.test_request_context():
            result = render_template("hello.html", name="Bob")
            assert result == "<p>Hello Bob!</p>"

    def test_template_inheritance(self, tmp_path):
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        (tmpl_dir / "base.html").write_text(
            "<html>{% block content %}{% endblock %}</html>")
        (tmpl_dir / "child.html").write_text(
            "{% extends 'base.html' %}{% block content %}Hello{% endblock %}")

        app = Cruet(__name__, template_folder=str(tmpl_dir))
        with app.test_request_context():
            result = render_template("child.html")
            assert result == "<html>Hello</html>"

    def test_template_not_found(self, tmp_path):
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()

        app = Cruet(__name__, template_folder=str(tmpl_dir))
        with app.test_request_context():
            with pytest.raises(Exception):  # TemplateNotFound
                render_template("nonexistent.html")

    def test_template_with_autoescaping(self, tmp_path):
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        (tmpl_dir / "page.html").write_text("{{ content }}")

        app = Cruet(__name__, template_folder=str(tmpl_dir))
        with app.test_request_context():
            result = render_template("page.html", content="<script>alert(1)</script>")
            assert "&lt;script&gt;" in result
            assert "<script>" not in result

    def test_subdirectory_template(self, tmp_path):
        tmpl_dir = tmp_path / "templates"
        sub = tmpl_dir / "emails"
        sub.mkdir(parents=True)
        (sub / "welcome.html").write_text("Welcome {{ user }}!")

        app = Cruet(__name__, template_folder=str(tmpl_dir))
        with app.test_request_context():
            result = render_template("emails/welcome.html", user="Carol")
            assert result == "Welcome Carol!"


class TestRenderInView:
    def test_render_template_string_in_view(self):
        app = Cruet(__name__)

        @app.route("/greet/<name>")
        def greet(name):
            return render_template_string("<b>Hi {{ name }}</b>", name=name)

        client = app.test_client()
        resp = client.get("/greet/Dave")
        assert resp.text == "<b>Hi Dave</b>"
        assert resp.status_code == 200

    def test_render_template_file_in_view(self, tmp_path):
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        (tmpl_dir / "index.html").write_text("<h1>{{ title }}</h1>")

        app = Cruet(__name__, template_folder=str(tmpl_dir))

        @app.route("/")
        def index():
            return render_template("index.html", title="Home")

        client = app.test_client()
        resp = client.get("/")
        assert resp.text == "<h1>Home</h1>"


class TestJinjaEnv:
    def test_jinja_env_is_cached(self):
        app = Cruet(__name__)
        with app.test_request_context():
            env1 = app.jinja_env
            env2 = app.jinja_env
            assert env1 is env2

    def test_jinja_env_is_jinja_environment(self):
        import jinja2
        app = Cruet(__name__)
        with app.test_request_context():
            assert isinstance(app.jinja_env, jinja2.Environment)


class TestTemplateFolderConfig:
    def test_default_template_folder(self):
        app = Cruet(__name__)
        assert app.template_folder == "templates"

    def test_custom_template_folder(self):
        app = Cruet(__name__, template_folder="/custom/path")
        assert app.template_folder == "/custom/path"

    def test_none_template_folder(self):
        app = Cruet(__name__, template_folder=None)
        assert app.template_folder is None
        # Should still work with render_template_string
        with app.test_request_context():
            result = render_template_string("{{ x }}", x=42)
            assert result == "42"
