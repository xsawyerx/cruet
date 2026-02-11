"""JSON provider for Flask-compatible JSON serialization."""
import dataclasses
import decimal
import json
import uuid
from datetime import date, datetime

from werkzeug.http import http_date


class DefaultJSONProvider:
    """Flask-compatible JSON provider with custom serialization."""

    def __init__(self, app):
        import weakref
        self._app = weakref.ref(app)
        self.sort_keys = True
        self.compact = None
        self.mimetype = "application/json"
        self.ensure_ascii = True

    def default(self, o):
        if isinstance(o, date):
            return http_date(o)
        if isinstance(o, decimal.Decimal):
            return str(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, "__html__"):
            return str(o.__html__())
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    def dumps(self, obj, **kwargs):
        kwargs.setdefault("default", self.default)
        kwargs.setdefault("ensure_ascii", self.ensure_ascii)
        kwargs.setdefault("sort_keys", self.sort_keys)
        return json.dumps(obj, **kwargs)

    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)

    def response(self, *args, **kwargs):
        from cruet._cruet import CResponse
        if args and kwargs:
            raise TypeError("jsonify() takes either args or kwargs, not both")
        if args:
            if len(args) == 1:
                data = args[0]
            else:
                data = args
        else:
            data = kwargs
        dump_args = {}
        app = self._app()
        debug = getattr(app, "debug", False)
        if (self.compact is None and debug) or self.compact is False:
            dump_args.setdefault("indent", 2)
        else:
            dump_args.setdefault("separators", (",", ":"))
        body = self.dumps(data, **dump_args)
        body += "\n"
        return CResponse(body, content_type=self.mimetype)
