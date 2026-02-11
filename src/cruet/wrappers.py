"""Python-level Request/Response wrappers."""
from cruet._cruet import CRequest, CResponse
from cruet.ctx import RequestWrapper


class MultiDict(dict):
    """A dict subclass where .get() returns the first value from a list.

    Wraps the output of parse_qs (which maps str -> list[str]) to behave
    like Werkzeug's MultiDict: .get(key) returns the first string, not the
    whole list.  .getlist(key) returns the full list.
    """

    def get(self, key, default=None):
        val = dict.get(self, key)
        if val is None:
            return default
        if isinstance(val, list):
            return val[0] if val else default
        return val

    def getlist(self, key):
        val = dict.get(self, key)
        if val is None:
            return []
        if isinstance(val, list):
            return list(val)
        return [val]

    def __getitem__(self, key):
        val = dict.__getitem__(self, key)
        if isinstance(val, list):
            return val[0] if val else None
        return val


class _ResponseHeaderSet:
    """Set-like wrapper around a specific header on a CResponse."""

    def __init__(self, cresp, header_name):
        self._cresp = cresp
        self._header = header_name

    def _get_items(self):
        current = self._cresp.headers.get(self._header, "")
        if not current:
            return set()
        return {v.strip() for v in current.split(",") if v.strip()}

    def add(self, value):
        items = self._get_items()
        items.add(value)
        self._cresp.headers.set(self._header, ", ".join(sorted(items)))

    def update(self, values):
        items = self._get_items()
        items.update(values)
        self._cresp.headers.set(self._header, ", ".join(sorted(items)))

    def discard(self, value):
        items = self._get_items()
        items.discard(value)
        if items:
            self._cresp.headers.set(self._header, ", ".join(sorted(items)))

    def __contains__(self, value):
        return value in self._get_items()

    def __iter__(self):
        return iter(self._get_items())

    def __len__(self):
        return len(self._get_items())


class Response:
    """Python wrapper around CResponse that adds Flask-compatible properties.

    Used as ``flask.Response`` in view functions. Wraps CResponse and adds
    properties like ``vary`` that CResponse (C type) can't support.
    """

    def __init__(self, body="", status=200, headers=None,
                 content_type="text/html; charset=utf-8"):
        if not isinstance(body, (str, bytes)) and hasattr(body, "__iter__"):
            chunks = []
            try:
                for chunk in body:
                    if isinstance(chunk, str):
                        chunks.append(chunk.encode("utf-8"))
                    else:
                        chunks.append(chunk)
            finally:
                if hasattr(body, "close"):
                    body.close()
            body = b"".join(chunks)
        self._cresp = CResponse(body, status=status, content_type=content_type)
        self.direct_passthrough = False
        if headers:
            if isinstance(headers, dict):
                for k, v in headers.items():
                    self._cresp.headers.set(k, v)
            else:
                for k, v in headers:
                    self._cresp.headers.set(k, v)

    @property
    def vary(self):
        return _ResponseHeaderSet(self._cresp, "Vary")

    @property
    def status_code(self):
        return self._cresp.status_code

    @status_code.setter
    def status_code(self, value):
        self._cresp.status_code = value

    @property
    def headers(self):
        return self._cresp.headers

    @property
    def data(self):
        return self._cresp.data

    @data.setter
    def data(self, value):
        self._cresp.data = value

    @property
    def content_type(self):
        return self._cresp.headers.get("Content-Type", "")

    @property
    def mimetype(self):
        ct = self.content_type
        if ";" in ct:
            return ct.split(";", 1)[0].strip()
        return ct

    @mimetype.setter
    def mimetype(self, value):
        self._cresp.headers.set("Content-Type", value)

    @property
    def max_cookie_size(self):
        try:
            from cruet.ctx import _app_ctx_var
            ctx = _app_ctx_var.get()
            return ctx.app.config.get("MAX_COOKIE_SIZE", 4093)
        except LookupError:
            return 4093

    @property
    def cache_control(self):
        return _CacheControl(self._cresp)

    def set_cookie(self, key, value="", *args, **kwargs):
        self._cresp.set_cookie(key, value, *args, **kwargs)
        max_size = self.max_cookie_size
        if max_size:
            from http.cookies import SimpleCookie
            c = SimpleCookie()
            try:
                c[key] = value if isinstance(value, str) else str(value)
                cookie_header = c.output(header="").strip()
            except Exception:
                cookie_header = f"{key}={value}"
            cookie_size = len(cookie_header.encode("latin-1", errors="replace"))
            if cookie_size > max_size:
                import warnings
                warnings.warn(
                    f"The '{key}' cookie is too large: the value was"
                    f" {cookie_size} bytes but the"
                    f" maximum is {max_size} bytes. Browsers may silently"
                    f" ignore cookies larger than this.",
                    stacklevel=2,
                )

    def delete_cookie(self, *args, **kwargs):
        return self._cresp.delete_cookie(*args, **kwargs)

    def get_data(self, as_text=False):
        data = self._cresp.data
        if as_text:
            return data.decode("utf-8", errors="replace")
        return data

    def __getattr__(self, name):
        return getattr(self._cresp, name)

    def __setattr__(self, name, value):
        if name == '_cresp':
            object.__setattr__(self, name, value)
        else:
            try:
                setattr(self._cresp, name, value)
            except AttributeError:
                object.__setattr__(self, name, value)

    def __call__(self, environ, start_response):
        return self._cresp(environ, start_response)

    def close(self):
        return None


class Request(RequestWrapper):
    """Flask-compatible Request wrapper around CRequest."""

    def __init__(self, environ):
        super().__init__(CRequest(environ), environ)


class _CacheControl:
    def __init__(self, cresp):
        self._cresp = cresp

    @property
    def max_age(self):
        value = self._cresp.headers.get("Cache-Control", "")
        if not value:
            return None
        parts = [p.strip() for p in value.split(",")]
        for part in parts:
            if part.startswith("max-age="):
                try:
                    return int(part.split("=", 1)[1])
                except ValueError:
                    return None
        return None

    @max_age.setter
    def max_age(self, value):
        if value is None:
            return
        self._cresp.headers.set("Cache-Control", f"max-age={int(value)}")
