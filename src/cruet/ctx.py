"""Application and request context management using contextvars."""
import contextvars
import json as _json
import sys

_app_ctx_var = contextvars.ContextVar('cruet.app_ctx')
_request_ctx_var = contextvars.ContextVar('cruet.request_ctx')

_sentinel = object()


class _BadRequestKeyDict:
    """A wrapper that raises BadRequest on missing key access."""

    def __init__(self, original):
        self._original = original

    def __getitem__(self, key):
        try:
            return self._original[key]
        except KeyError as e:
            from werkzeug.exceptions import BadRequestKeyError
            exc = BadRequestKeyError(key)
            exc.__cause__ = e
            raise exc

    def __getattr__(self, name):
        return getattr(self._original, name)

    def __contains__(self, key):
        return key in self._original

    def __iter__(self):
        return iter(self._original)

    def __len__(self):
        return len(self._original)

    def get(self, key, default=None):
        return self._original.get(key, default)


class _FileDict:
    def __init__(self, request_wrapper):
        self._request = request_wrapper
        self._files = {}

    def __getitem__(self, key):
        if key in self._files:
            return self._files[key]
        try:
            from cruet.ctx import _app_ctx_var
            ctx = _app_ctx_var.get()
            debug = ctx.app.debug
        except Exception:
            debug = False
        if debug and key in self._request.form:
            from cruet.debughelpers import DebugFilesKeyError
            raise DebugFilesKeyError(key, self._request.form.get(key))
        from werkzeug.exceptions import BadRequestKeyError
        raise BadRequestKeyError(key)

    def __contains__(self, key):
        return key in self._files

    def get(self, key, default=None):
        try:
            return self[key]
        except Exception:
            return default


class _UserAgent:
    def __init__(self, value):
        self.string = value or ""


class RequestWrapper:
    """Python wrapper around CRequest that adds Flask-compatible behavior.

    Wraps get_json() to raise BadRequest on decode errors, and wraps
    form to raise BadRequest on missing key access.
    """

    def __init__(self, crequest, environ=None):
        object.__setattr__(self, '_crequest', crequest)
        object.__setattr__(self, '_environ', environ)
        object.__setattr__(self, '_wrapped_form', None)
        object.__setattr__(self, '_wrapped_files', None)
        object.__setattr__(self, '_max_content_length', None)
        object.__setattr__(self, '_max_form_memory_size', None)
        object.__setattr__(self, '_max_form_parts', None)

    def _get_app_config(self, key, default=None):
        try:
            app_ctx = _app_ctx_var.get()
        except LookupError:
            return default
        return app_ctx.app.config.get(key, default)

    def get_json(self, force=False, silent=False, cache=True):
        data = self._crequest.get_data()
        if not data:
            if silent:
                return None
            self._raise_bad_json("Failed to decode JSON object: No data")
        if not force:
            ct = self._crequest.content_type or ""
            mt = ct.split(";", 1)[0].strip()
            if mt != "application/json" and not (
                mt.startswith("application/") and mt.endswith("+json")
            ):
                if silent:
                    return None
                self._raise_bad_json("Failed to decode JSON object: Content type is not JSON")
        try:
            # Use app's JSON provider if available
            try:
                app_ctx = _app_ctx_var.get()
                return app_ctx.app.json.loads(data)
            except LookupError:
                return _json.loads(data)
        except (ValueError, _json.JSONDecodeError) as e:
            if silent:
                return None
            self._raise_bad_json(f"Failed to decode JSON object: {e}", cause=e)

    def _raise_bad_json(self, message, cause=None):
        from werkzeug.exceptions import BadRequest
        # In debug mode, include details; in production, use generic message
        try:
            app_ctx = _app_ctx_var.get()
            debug = app_ctx.app.debug
        except LookupError:
            debug = False
        if debug:
            exc = BadRequest(message)
        else:
            exc = BadRequest()
        if cause is not None:
            exc.__cause__ = cause
        raise exc

    @property
    def environ(self):
        return object.__getattribute__(self, "_environ") or {}

    @property
    def form(self):
        max_content_length = self.max_content_length
        if max_content_length is not None:
            content_length = getattr(self._crequest, "content_length", None)
            if content_length is not None and content_length > max_content_length:
                from werkzeug.exceptions import RequestEntityTooLarge
                raise RequestEntityTooLarge()
        wrapped = object.__getattribute__(self, '_wrapped_form')
        if wrapped is None:
            wrapped = _BadRequestKeyDict(self._crequest.form)
            object.__setattr__(self, '_wrapped_form', wrapped)
        return wrapped

    @property
    def files(self):
        wrapped = object.__getattribute__(self, '_wrapped_files')
        if wrapped is None:
            wrapped = _FileDict(self)
            object.__setattr__(self, '_wrapped_files', wrapped)
        return wrapped

    @property
    def json(self):
        return self.get_json(silent=True)

    @property
    def is_json(self):
        ct = self._crequest.content_type or ""
        mt = ct.split(";", 1)[0].strip()
        return mt == "application/json" or (
            mt.startswith("application/") and mt.endswith("+json")
        )

    @property
    def url(self):
        environ = object.__getattribute__(self, "_environ") or {}
        scheme = environ.get("wsgi.url_scheme") or "http"
        host = environ.get("HTTP_HOST")
        if not host:
            server_name = environ.get("SERVER_NAME", "localhost")
            server_port = environ.get("SERVER_PORT")
            if server_port and server_port not in ("80", "443"):
                host = f"{server_name}:{server_port}"
            else:
                host = server_name
        script_name = environ.get("SCRIPT_NAME", "") or ""
        path = environ.get("PATH_INFO", "") or ""
        if script_name.endswith("/") and path.startswith("/"):
            full_path = script_name.rstrip("/") + path
        elif script_name and not path.startswith("/"):
            full_path = script_name + "/" + path
        else:
            full_path = script_name + path
        if not full_path.startswith("/"):
            full_path = "/" + full_path
        qs = environ.get("QUERY_STRING", "")
        if qs:
            return f"{scheme}://{host}{full_path}?{qs}"
        return f"{scheme}://{host}{full_path}"

    @property
    def user_agent(self):
        environ = object.__getattribute__(self, "_environ") or {}
        return _UserAgent(environ.get("HTTP_USER_AGENT", ""))

    @property
    def max_content_length(self):
        override = object.__getattribute__(self, "_max_content_length")
        if override is not None:
            return override
        return self._get_app_config("MAX_CONTENT_LENGTH")

    @max_content_length.setter
    def max_content_length(self, value):
        object.__setattr__(self, "_max_content_length", value)

    @property
    def max_form_memory_size(self):
        override = object.__getattribute__(self, "_max_form_memory_size")
        if override is not None:
            return override
        return self._get_app_config("MAX_FORM_MEMORY_SIZE", 500_000)

    @max_form_memory_size.setter
    def max_form_memory_size(self, value):
        object.__setattr__(self, "_max_form_memory_size", value)

    @property
    def max_form_parts(self):
        override = object.__getattribute__(self, "_max_form_parts")
        if override is not None:
            return override
        return self._get_app_config("MAX_FORM_PARTS", 1_000)

    @max_form_parts.setter
    def max_form_parts(self, value):
        object.__setattr__(self, "_max_form_parts", value)

    def __getattr__(self, name):
        return getattr(self._crequest, name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            try:
                setattr(self._crequest, name, value)
            except AttributeError:
                object.__setattr__(self, name, value)

    def __repr__(self):
        return repr(self._crequest)


class _AppCtxGlobals:
    """A plain object for storing data during an application context.
    Behaves like Flask's g."""

    def __getattr__(self, name):
        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        self.__dict__[name] = value

    def __delattr__(self, name):
        try:
            del self.__dict__[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def get(self, name, default=None):
        return self.__dict__.get(name, default)

    def pop(self, name, *args):
        return self.__dict__.pop(name, *args)

    def setdefault(self, name, default=None):
        return self.__dict__.setdefault(name, default)

    def __contains__(self, item):
        return item in self.__dict__

    def __iter__(self):
        return iter(self.__dict__)

    def __repr__(self):
        ctx = _app_ctx_var.get(None)
        if ctx is not None:
            return f"<flask.g of '{ctx.app.name}'>"
        return object.__repr__(self)


class AppContext:
    """The application context binds current_app and g."""

    def __init__(self, app, *, is_request_context=False):
        self.app = app
        self.g = getattr(app, 'app_ctx_globals_class', _AppCtxGlobals)()
        self._token = None
        self._is_request_context = is_request_context
        self._refcnt = 0
        self._fallback = None

    def push(self):
        current = _app_ctx_var.get(None)
        if current is self:
            self._refcnt += 1
            return
        if current is not None and current.app is self.app:
            current._refcnt += 1
            self._fallback = current
            return
        self._refcnt = 1
        self._token = _app_ctx_var.set(self)
        try:
            from cruet.signals import appcontext_pushed
            appcontext_pushed.send(self.app)
        except Exception:
            pass

    def pop(self, exc=_sentinel):
        if self._fallback is not None:
            fallback = self._fallback
            self._fallback = None
            fallback.pop(exc)
            return
        if exc is _sentinel:
            exc = sys.exc_info()[1]
        if self._refcnt > 1:
            self._refcnt -= 1
            return
        self._run_teardown_funcs(exc)
        try:
            from cruet.signals import appcontext_popped
            appcontext_popped.send(self.app)
        except Exception:
            pass
        self._refcnt = 0
        if self._token is not None:
            _app_ctx_var.reset(self._token)
            self._token = None

    def _run_teardown_funcs(self, exc):
        import asyncio
        ensure_sync = getattr(self.app, "ensure_sync", None)
        try:
            from cruet.signals import appcontext_tearing_down
            appcontext_tearing_down.send(self.app, exc=exc)
        except Exception:
            pass
        for func in reversed(getattr(self.app, 'teardown_appcontext_funcs', [])):
            try:
                if ensure_sync is not None:
                    rv = ensure_sync(func)(exc)
                    if asyncio.iscoroutine(rv):
                        asyncio.run(rv)
                else:
                    func(exc)
            except Exception:
                pass

    def __enter__(self):
        self.push()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pop(exc_val)
        return False

    def copy(self):
        """Return a copy of the current request context (Flask 3.x compat)."""
        try:
            ctx = _request_ctx_var.get()
        except LookupError:
            raise RuntimeError("No request context to copy.")
        return ctx.copy()

    def match_request(self):
        """Match the current request and populate request context attributes."""
        try:
            ctx = _request_ctx_var.get()
        except LookupError:
            raise RuntimeError("No request context to match.")
        ctx.app._match_request()


class RequestContext:
    """The request context binds the request and pushes an app context."""

    def __init__(self, app, environ, match_request=False, request=None, session=None):
        from cruet._cruet import CRequest
        self.app = app
        self.environ = environ
        if request is None:
            request = RequestWrapper(CRequest(environ), environ)
        self.request = request
        self.session = session
        self._after_request_funcs = []
        self._app_ctx = None
        self._token = None
        self._match_request = match_request

    def push(self):
        # Push (or reuse) an app context for each request
        try:
            existing = _app_ctx_var.get()
        except LookupError:
            existing = None
        if existing is not None and existing.app is self.app:
            self._app_ctx = existing
        else:
            self._app_ctx = AppContext(self.app, is_request_context=True)
        self._app_ctx.push()

        self._token = _request_ctx_var.set(self)

        # Open a session if one hasn't been set
        if self.session is None:
            from cruet.sessions import open_session, NullSession
            try:
                session = open_session(self.app, self.request)
            except Exception:
                if self._token is not None:
                    _request_ctx_var.reset(self._token)
                    self._token = None
                if self._app_ctx is not None:
                    self._app_ctx.pop()
                    self._app_ctx = None
                raise
            if session is None:
                session = NullSession()
            self.session = session

        if self._match_request:
            try:
                self.app._match_request()
            except Exception:
                pass

    def pop(self, exc=_sentinel):
        if exc is _sentinel:
            exc = sys.exc_info()[1]
        self._run_teardown_funcs(exc)
        if self._token is not None:
            _request_ctx_var.reset(self._token)
            self._token = None

        if self._app_ctx is not None:
            # If the app context is refcounted (e.g., nested app.app_context()
            # inside a request), run teardown_appcontext at request end since
            # AppContext.pop will only decrement and not tear down yet.
            if self._app_ctx._refcnt > 1:
                self._app_ctx._run_teardown_funcs(exc)
            self._app_ctx.pop(exc)
            self._app_ctx = None

    def _run_teardown_funcs(self, exc):
        import asyncio
        ensure_sync = getattr(self.app, "ensure_sync", None)
        for func in reversed(getattr(self.app, 'teardown_request_funcs', [])):
            try:
                if ensure_sync is not None:
                    rv = ensure_sync(func)(exc)
                    if asyncio.iscoroutine(rv):
                        asyncio.run(rv)
                else:
                    func(exc)
            except Exception:
                pass

    def __enter__(self):
        self.push()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pop(exc_val)
        return False

    def copy(self):
        """Create a copy of this request context for another greenlet."""
        return self.__class__(
            self.app,
            environ=self.request.environ,
            request=self.request,
            session=self.session,
        )


def copy_current_request_context(f):
    """Decorator to copy the current request context for use in a greenlet."""
    from functools import update_wrapper
    try:
        ctx = _request_ctx_var.get()
    except LookupError:
        raise RuntimeError("No request context to copy.")
    ctx_copy = ctx.copy()

    def wrapper(*args, **kwargs):
        with ctx_copy:
            return f(*args, **kwargs)

    return update_wrapper(wrapper, f)
