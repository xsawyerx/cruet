"""Global proxy objects for request, g, current_app."""
from cruet.ctx import _app_ctx_var, _request_ctx_var

# Flask-compatible contextvars
_cv_app = _app_ctx_var
_cv_request = _request_ctx_var


class _ProxyLookup:
    """A proxy that looks up an attribute on a context variable."""

    def __init__(self, lookup_func, name=None):
        self._lookup_func = lookup_func
        self.__name__ = name

    def _get_current(self):
        try:
            return self._lookup_func()
        except LookupError:
            raise RuntimeError(
                f"Working outside of {'request' if 'request' in (self.__name__ or '') else 'application'} context."
            )

    def _get_current_object(self):
        """Return the actual proxied object (Flask/Werkzeug compat)."""
        return self._get_current()

    def __getattr__(self, name):
        if name in ('_lookup_func', '_get_current', '__name__'):
            raise AttributeError(name)
        return getattr(self._get_current(), name)

    def __setattr__(self, name, value):
        if name.startswith('_') or name == '__name__':
            super().__setattr__(name, value)
        else:
            setattr(self._get_current(), name, value)

    def __delattr__(self, name):
        if name.startswith('_'):
            super().__delattr__(name)
        else:
            delattr(self._get_current(), name)

    def __repr__(self):
        try:
            obj = self._get_current()
            return repr(obj)
        except RuntimeError:
            return "<LocalProxy unbound>"

    def __enter__(self):
        return self._get_current().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._get_current().__exit__(exc_type, exc_val, exc_tb)

    def __bool__(self):
        try:
            self._get_current()
            return True
        except RuntimeError:
            return False

    def __eq__(self, other):
        return self._get_current() == other

    def __hash__(self):
        return id(self)

    # Dict protocol — needed for session proxy
    def __getitem__(self, key):
        return self._get_current()[key]

    def __setitem__(self, key, value):
        self._get_current()[key] = value

    def __delitem__(self, key):
        del self._get_current()[key]

    def __contains__(self, key):
        return key in self._get_current()

    def __iter__(self):
        return iter(self._get_current())

    def __len__(self):
        return len(self._get_current())


def _get_request():
    return _request_ctx_var.get().request


def _get_g():
    return _app_ctx_var.get().g


def _get_current_app():
    return _app_ctx_var.get().app


def _get_session():
    return _request_ctx_var.get().session


def _get_app_ctx():
    return _app_ctx_var.get()


request = _ProxyLookup(_get_request, name="request")
g = _ProxyLookup(_get_g, name="g")
current_app = _ProxyLookup(_get_current_app, name="current_app")
session = _ProxyLookup(_get_session, name="session")
app_ctx = _ProxyLookup(_get_app_ctx, name="app_ctx")


def has_request_context():
    """Return True if a request context is active."""
    try:
        _request_ctx_var.get()
        return True
    except LookupError:
        return False


def has_app_context():
    """Return True if an application context is active."""
    try:
        _app_ctx_var.get()
        return True
    except LookupError:
        return False


def after_this_request(f):
    """Register a function to run after the current request.

    The function is called with the response object and must return
    a response object (the same or a new one).

    Usage::

        @app.route("/")
        def index():
            @after_this_request
            def add_header(response):
                response.headers.set("X-Custom", "value")
                return response
            return "Hello"
    """
    try:
        ctx = _request_ctx_var.get()
    except LookupError:
        raise RuntimeError("Working outside of request context.")
    ctx._after_request_funcs.append(f)
    return f
