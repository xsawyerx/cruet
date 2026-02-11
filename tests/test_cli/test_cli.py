"""Unit tests for cruet CLI support (app.cli / AppGroup)."""

import click
from click.testing import CliRunner
import pytest

from cruet import Flask


class TestAppGroupWithClick:
    """Tests for @app.cli.command() with click available."""

    def test_command_registered(self):
        app = Flask(__name__)

        @app.cli.command()
        def greet():
            pass

        assert "greet" in app.cli

    def test_command_custom_name(self):
        app = Flask(__name__)

        @app.cli.command("custom")
        def greet():
            pass

        assert "custom" in app.cli
        assert "greet" not in app.cli

    def test_command_callable(self):
        """The registered click command is invocable via click's test runner."""
        app = Flask(__name__)

        @app.cli.command()
        def hello():
            click.echo("hello output")

        runner = CliRunner()
        result = runner.invoke(app.cli._group, ["hello"])
        assert result.exit_code == 0
        assert "hello output" in result.output

    def test_click_option(self):
        app = Flask(__name__)

        @app.cli.command()
        @click.option("--name", default="World")
        def greet(name):
            click.echo(f"Hello, {name}!")

        runner = CliRunner()
        result = runner.invoke(app.cli._group, ["greet", "--name", "Alice"])
        assert result.exit_code == 0
        assert "Hello, Alice!" in result.output

    def test_list_commands(self):
        app = Flask(__name__)

        @app.cli.command()
        def beta():
            pass

        @app.cli.command()
        def alpha():
            pass

        assert app.cli.list_commands() == ["alpha", "beta"]

    def test_contains(self):
        app = Flask(__name__)

        @app.cli.command()
        def mycommand():
            pass

        assert "mycommand" in app.cli
        assert "nonexistent" not in app.cli

    def test_getitem(self):
        app = Flask(__name__)

        @app.cli.command()
        def mycommand():
            pass

        cmd = app.cli["mycommand"]
        assert cmd is not None
        assert cmd.name == "mycommand"

    def test_main_delegates_to_click(self):
        """app.cli.main() delegates to click.Group.main()."""
        app = Flask(__name__)

        @app.cli.command()
        def hello():
            click.echo("from main")

        runner = CliRunner()
        result = runner.invoke(app.cli._group, ["hello"])
        assert result.exit_code == 0
        assert "from main" in result.output
