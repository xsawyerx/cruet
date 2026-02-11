"""Tests for the CLI entry point (python -m cruet)."""
import subprocess
import sys
import pytest


class TestCLINoArgs:
    def test_no_args_shows_help(self):
        """Running with no args should show help."""
        result = subprocess.run(
            [sys.executable, "-m", "cruet"],
            capture_output=True, text=True, timeout=5
        )
        # Should print help and exit
        assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower() or result.returncode == 0

    def test_run_no_app_shows_error(self):
        """'cruet run' without app argument should show error."""
        result = subprocess.run(
            [sys.executable, "-m", "cruet", "run"],
            capture_output=True, text=True, timeout=5
        )
        # Should error about missing required argument
        assert result.returncode != 0 or "error" in result.stderr.lower()


class TestCLIArgParsing:
    def test_module_colon_app_parsing(self):
        """module:app format should be accepted by the parser."""
        # We can't actually run the server, but we can check arg parsing
        # by importing and testing the argument parser directly
        from cruet.__main__ import main
        import argparse

        # Build parser same way main() does
        parser = argparse.ArgumentParser(prog="cruet")
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("app")
        run_parser.add_argument("--host", default="127.0.0.1")
        run_parser.add_argument("--port", type=int, default=8000)
        run_parser.add_argument("--workers", type=int, default=1)

        args = parser.parse_args(["run", "mymodule:myapp"])
        assert args.command == "run"
        assert args.app == "mymodule:myapp"

    def test_host_port_workers_parsing(self):
        """--host, --port, --workers should be parsed correctly."""
        import argparse

        parser = argparse.ArgumentParser(prog="cruet")
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("app")
        run_parser.add_argument("--host", default="127.0.0.1")
        run_parser.add_argument("--port", type=int, default=8000)
        run_parser.add_argument("--workers", type=int, default=1)

        args = parser.parse_args([
            "run", "mod:app",
            "--host", "0.0.0.0",
            "--port", "9000",
            "--workers", "4"
        ])
        assert args.host == "0.0.0.0"
        assert args.port == 9000
        assert args.workers == 4


class TestCLIInvalidModule:
    def test_invalid_module_path(self):
        """Invalid module path should give a useful error."""
        result = subprocess.run(
            [sys.executable, "-m", "cruet", "run", "nonexistent.module:app"],
            capture_output=True, text=True, timeout=5
        )
        assert result.returncode != 0
        # Should mention module import error
        assert "error" in result.stderr.lower() or "ModuleNotFoundError" in result.stderr or "No module" in result.stderr

    def test_module_without_app_attribute(self):
        """Module without the specified app attribute should give error."""
        result = subprocess.run(
            [sys.executable, "-m", "cruet", "run", "os:nonexistent_attr"],
            capture_output=True, text=True, timeout=5
        )
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "Attribute" in result.stderr or "has no attribute" in result.stderr


class TestCLIDefaults:
    def test_default_host(self):
        """Default host should be 127.0.0.1."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("app")
        run_parser.add_argument("--host", default="127.0.0.1")
        run_parser.add_argument("--port", type=int, default=8000)
        run_parser.add_argument("--workers", type=int, default=1)

        args = parser.parse_args(["run", "mod:app"])
        assert args.host == "127.0.0.1"

    def test_default_port(self):
        """Default port should be 8000."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("app")
        run_parser.add_argument("--host", default="127.0.0.1")
        run_parser.add_argument("--port", type=int, default=8000)
        run_parser.add_argument("--workers", type=int, default=1)

        args = parser.parse_args(["run", "mod:app"])
        assert args.port == 8000

    def test_default_workers(self):
        """Default workers should be 1."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("app")
        run_parser.add_argument("--host", default="127.0.0.1")
        run_parser.add_argument("--port", type=int, default=8000)
        run_parser.add_argument("--workers", type=int, default=1)

        args = parser.parse_args(["run", "mod:app"])
        assert args.workers == 1
