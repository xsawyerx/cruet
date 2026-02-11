"""Conftest shim: redirect ``import flask`` to ``cruet`` so that Flask's
own test suite exercises Cruet's API.

Three responsibilities:
1. ``sys.modules`` patching — make ``flask``, ``flask.globals``, etc.
   resolve to cruet or lightweight stubs.
2. Fixtures — replicate Flask's conftest fixtures adapted for cruet.
3. ``pytest_collection_modifyitems`` — xfail tests that exercise features
   cruet does not (yet) implement.
"""
import contextlib
import os
import sys
import types

import pytest
from _pytest import monkeypatch

# ---------------------------------------------------------------------------
# 1. sys.modules patching
# ---------------------------------------------------------------------------

import cruet
import cruet.globals
import cruet.cli
import cruet.config
import cruet.ctx
import cruet.sessions
import cruet.helpers
import cruet.templating
import cruet.json as _cruet_json
import cruet.json.provider as _cruet_json_provider
import cruet.json.tag as _cruet_json_tag

# Main flask module → cruet
sys.modules["flask"] = cruet

# Submodule shims
sys.modules["flask.globals"] = cruet.globals
# --- flask.cli stub (add missing names that tests import) ---
_flask_cli = types.ModuleType("flask.cli")
_flask_cli.AppGroup = cruet.cli.AppGroup
_flask_cli.FlaskGroup = cruet.cli.FlaskGroup
_flask_cli.ScriptInfo = cruet.cli.ScriptInfo
_flask_cli.NoAppException = cruet.cli.NoAppException
_flask_cli.find_best_app = cruet.cli.find_best_app
_flask_cli.get_version = cruet.cli.get_version
_flask_cli.load_dotenv = cruet.cli.load_dotenv
_flask_cli.locate_app = cruet.cli.locate_app
_flask_cli.prepare_import = cruet.cli.prepare_import
_flask_cli.run_command = cruet.cli.run_command
_flask_cli.with_appcontext = cruet.cli.with_appcontext
_flask_cli.cli = cruet.cli.cli
sys.modules["flask.cli"] = _flask_cli
sys.modules["flask.config"] = cruet.config
sys.modules["flask.ctx"] = cruet.ctx

# flask.globals.app_ctx — Flask exposes this as a proxy to the app context.
# Several tests do ``from flask.globals import app_ctx``.
cruet.globals.app_ctx = cruet.globals.app_ctx
# Flask also exposes _cv_app (the raw ContextVar) in globals.
# Flask 3.x merges request and app contexts. Map to request ctx for tests.
cruet.globals._cv_app = cruet.ctx._request_ctx_var

# --- flask.sessions stub ---
_flask_sessions = types.ModuleType("flask.sessions")
_flask_sessions.Session = cruet.sessions.Session
_flask_sessions.NullSession = cruet.sessions.NullSession
_flask_sessions.SecureCookieSessionInterface = cruet.sessions.SecureCookieSessionInterface
_flask_sessions.SessionInterface = cruet.sessions.SessionInterface
sys.modules["flask.sessions"] = _flask_sessions

# --- flask.json stub ---
sys.modules["flask.json"] = _cruet_json

# --- flask.json.provider stub ---
sys.modules["flask.json.provider"] = _cruet_json_provider

# --- flask.json.tag stub ---
sys.modules["flask.json.tag"] = _cruet_json_tag

# --- flask.testing stub ---
_flask_testing = types.ModuleType("flask.testing")
import cruet.testing as _cruet_testing
_flask_testing.FlaskClient = _cruet_testing.FlaskClient
_flask_testing.FlaskCliRunner = _cruet_testing.FlaskCliRunner
_flask_testing.EnvironBuilder = _cruet_testing.EnvironBuilder
sys.modules["flask.testing"] = _flask_testing

# --- flask.views stub ---
_flask_views = types.ModuleType("flask.views")
import cruet.views as _cruet_views
_flask_views.View = _cruet_views.View
_flask_views.MethodView = _cruet_views.MethodView
sys.modules["flask.views"] = _flask_views

# --- flask.logging stub ---
_flask_logging = types.ModuleType("flask.logging")
import cruet.logging as _cruet_logging
_flask_logging.default_handler = _cruet_logging.default_handler
_flask_logging.has_level_handler = _cruet_logging.has_level_handler
_flask_logging.wsgi_errors_stream = _cruet_logging.wsgi_errors_stream
_flask_logging.create_logger = _cruet_logging.create_logger
sys.modules["flask.logging"] = _flask_logging

# --- flask.helpers stub ---
_flask_helpers = types.ModuleType("flask.helpers")
from cruet.cli import get_debug_flag as _cruet_get_debug_flag
_flask_helpers.get_debug_flag = _cruet_get_debug_flag
sys.modules["flask.helpers"] = _flask_helpers

# --- flask.debughelpers stub ---
import cruet.debughelpers as _cruet_debughelpers
sys.modules["flask.debughelpers"] = _cruet_debughelpers

# --- flask.templating stub ---
sys.modules["flask.templating"] = cruet.templating

# Ensure cruet top-level has attributes Flask tests expect
if not hasattr(cruet, "json"):
    cruet.json = _cruet_json

# ``appcontext_popped`` — signal stub (some tests import it)
if not hasattr(cruet, "appcontext_popped"):
    class _FakeSignal:
        """Minimal signal stub — .connect() is a no-op."""
        def connect(self, *a, **kw):
            pass
        def disconnect(self, *a, **kw):
            pass
        def send(self, *a, **kw):
            pass
        @contextlib.contextmanager
        def connected_to(self, receiver, sender=None):
            yield
    cruet.appcontext_popped = _FakeSignal()

# ---------------------------------------------------------------------------
# 2. Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _standard_os_environ():
    mp = monkeypatch.MonkeyPatch()
    out = (
        (os.environ, "FLASK_ENV_FILE", monkeypatch.notset),
        (os.environ, "FLASK_APP", monkeypatch.notset),
        (os.environ, "FLASK_DEBUG", monkeypatch.notset),
        (os.environ, "FLASK_RUN_FROM_CLI", monkeypatch.notset),
        (os.environ, "WERKZEUG_RUN_MAIN", monkeypatch.notset),
    )
    for _, key, value in out:
        if value is monkeypatch.notset:
            mp.delenv(key, False)
        else:
            mp.setenv(key, value)
    yield out
    mp.undo()


@pytest.fixture(autouse=True)
def _reset_os_environ(monkeypatch, _standard_os_environ):
    monkeypatch._setitem.extend(_standard_os_environ)


@pytest.fixture
def app():
    app = cruet.Flask(
        "flask_test", root_path=os.path.dirname(__file__)
    )
    app.config.update(TESTING=True, SECRET_KEY="test key")
    return app


@pytest.fixture
def app_ctx(app):
    with app.app_context() as ctx:
        yield ctx


@pytest.fixture
def req_ctx(app):
    with app.test_request_context() as ctx:
        yield ctx


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def test_apps(monkeypatch):
    monkeypatch.syspath_prepend(
        os.path.join(os.path.dirname(__file__), "test_apps")
    )
    original_modules = set(sys.modules.keys())
    yield
    for key in sys.modules.keys() - original_modules:
        sys.modules.pop(key)


@pytest.fixture(autouse=True)
def leak_detector():
    yield
    # Pop any leaked app contexts
    from cruet.ctx import _app_ctx_var
    while True:
        try:
            ctx = _app_ctx_var.get()
            ctx.pop()
        except LookupError:
            break


@pytest.fixture
def modules_tmp_path(tmp_path, monkeypatch):
    rv = tmp_path / "modules_tmp"
    rv.mkdir()
    monkeypatch.syspath_prepend(os.fspath(rv))
    return rv


@pytest.fixture
def modules_tmp_path_prefix(modules_tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "prefix", os.fspath(modules_tmp_path))
    return modules_tmp_path


@pytest.fixture
def site_packages(modules_tmp_path, monkeypatch):
    py_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
    rv = modules_tmp_path / "lib" / py_dir / "site-packages"
    rv.mkdir(parents=True)
    monkeypatch.syspath_prepend(os.fspath(rv))
    return rv


@pytest.fixture
def purge_module(request):
    def inner(name):
        request.addfinalizer(lambda: sys.modules.pop(name, None))
    return inner


# ---------------------------------------------------------------------------
# 3. xfail marking
# ---------------------------------------------------------------------------

# Files that test features cruet doesn't support at all
_XFAIL_FILES = {
}

# Individual tests to xfail in partially-passing files.
# Keys are "filename::test_function_name" (without the tests_flask/ prefix).
_XFAIL_TESTS = {
    # --- test_reqctx.py ---
    #"test_reqctx.py::TestGreenletContextCopying::test_greenlet_context_copying",
    #"test_reqctx.py::TestGreenletContextCopying::test_greenlet_context_copying_api",

    # --- test_json.py ---
    # (all json tests now pass)

}


# Parameterized test variants that still fail (matched by full nodeid).
# Used when some param variants pass but others fail for the same test.
_XFAIL_PARAMS = {
}

# Tests that must be skipped entirely (would hang or crash the process)
_SKIP_TESTS = {
}


def pytest_collection_modifyitems(config, items):
    _tests_flask_dir = os.path.dirname(__file__)
    for item in items:
        # Only apply to tests inside this directory
        if not str(item.fspath).startswith(_tests_flask_dir):
            continue

        # Get the filename relative to tests_flask/
        rel = os.path.basename(item.fspath)

        # Whole-file xfails
        if rel in _XFAIL_FILES:
            item.add_marker(pytest.mark.xfail(
                reason=f"cruet: {rel} not supported yet", strict=False
            ))
            continue

        # Build test_id: include class name if present
        cls = getattr(item, "cls", None)
        if cls:
            test_id = f"{rel}::{cls.__name__}::{item.originalname}"
        else:
            test_id = f"{rel}::{item.originalname}"

        # Individual test skips (would hang)
        if test_id in _SKIP_TESTS:
            item.add_marker(pytest.mark.skip(
                reason="cruet: test would hang (calls app.run)"
            ))
            continue

        # Individual test xfails
        if test_id in _XFAIL_TESTS:
            item.add_marker(pytest.mark.xfail(
                reason="cruet: not yet implemented", strict=False
            ))
            continue

        # Parameterized variant xfails (matched by full name including params)
        cls = getattr(item, "cls", None)
        if cls:
            param_id = f"{rel}::{cls.__name__}::{item.name}"
        else:
            param_id = f"{rel}::{item.name}"
        if param_id in _XFAIL_PARAMS:
            item.add_marker(pytest.mark.xfail(
                reason="cruet: not yet implemented", strict=False
            ))
