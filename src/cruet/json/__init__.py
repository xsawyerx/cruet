"""JSON helpers compatible with Flask's flask.json."""
import json as _json

from cruet.helpers import jsonify
from cruet.json_provider import DefaultJSONProvider


def dumps(obj, **kwargs):
    """Flask-compatible json.dumps using the app's JSON provider if available."""
    try:
        from cruet.globals import current_app
        app = current_app._get_current_object()
        return app.json.dumps(obj, **kwargs)
    except (RuntimeError, LookupError):
        pass
    class _DummyApp:
        debug = False
    _provider = DefaultJSONProvider(_DummyApp())
    kwargs.setdefault("default", _provider.default)
    return _json.dumps(obj, **kwargs)


def loads(s, **kwargs):
    """Flask-compatible json.loads using the app's JSON provider if available."""
    try:
        from cruet.globals import current_app
        app = current_app._get_current_object()
        return app.json.loads(s, **kwargs)
    except (RuntimeError, LookupError):
        pass
    return _json.loads(s, **kwargs)


def dump(obj, fp, **kwargs):
    return _json.dump(obj, fp, **kwargs)


def load(fp, **kwargs):
    return _json.load(fp, **kwargs)


__all__ = [
    "dumps",
    "loads",
    "dump",
    "load",
    "jsonify",
    "DefaultJSONProvider",
]
