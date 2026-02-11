"""Cookie-based session support, compatible with Flask's session API.

Uses HMAC-SHA256 for signing, JSON for serialization, base64 for encoding.
No external dependencies (no itsdangerous).
"""
import base64
import hashlib
import hmac
import json
import time
import warnings


class Session(dict):
    """A dict subclass that tracks whether it has been modified.

    Used as the session object in request contexts. Compatible with
    Flask's SecureCookieSession API.
    """

    def __init__(self, initial=None):
        super().__init__()
        self.modified = False
        self.accessed = False
        self.new = True
        if initial:
            super().update(initial)
            self.new = False

    @property
    def permanent(self):
        return super().get("_permanent", False)

    @permanent.setter
    def permanent(self, value):
        self.accessed = True
        super().__setitem__("_permanent", value)
        self.modified = True

    def __getitem__(self, key):
        self.accessed = True
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.accessed = True
        return super().get(key, default)

    def __contains__(self, key):
        self.accessed = True
        return super().__contains__(key)

    def __setitem__(self, key, value):
        self.accessed = True
        super().__setitem__(key, value)
        self.modified = True

    def __delitem__(self, key):
        self.accessed = True
        super().__delitem__(key)
        self.modified = True

    def pop(self, key, *args):
        self.accessed = True
        self.modified = True
        return super().pop(key, *args)

    def update(self, *args, **kwargs):
        self.accessed = True
        super().update(*args, **kwargs)
        self.modified = True

    def setdefault(self, key, default=None):
        self.accessed = True
        if key not in self:
            self.modified = True
        return super().setdefault(key, default)

    def clear(self):
        self.accessed = True
        super().clear()
        self.modified = True


class NullSession(Session):
    """A session that raises errors on mutation.

    Used when the secret_key is not set, to indicate that session
    support is unavailable.
    """

    _fail_msg = (
        "The session is unavailable because no secret key was set."
        " Set the secret_key on the application to something unique"
        " and secret."
    )

    def _fail(self, *args, **kwargs):
        raise RuntimeError(
            "The session is unavailable because no secret "
            "key was set.  Set the secret_key on the "
            "application to something unique and secret."
        )

    __setitem__ = _fail
    __delitem__ = _fail
    pop = _fail
    update = _fail
    clear = _fail
    setdefault = _fail


def _tag(value):
    from datetime import datetime
    try:
        from markupsafe import Markup
    except Exception:
        Markup = None
    import uuid
    if isinstance(value, tuple):
        return {"__cruet__": ["t", [_tag(v) for v in value]]}
    if isinstance(value, bytes):
        b64 = base64.b64encode(value).decode("ascii")
        return {"__cruet__": ["b", b64]}
    if Markup is not None and isinstance(value, Markup):
        return {"__cruet__": ["m", str(value)]}
    if isinstance(value, uuid.UUID):
        return {"__cruet__": ["u", str(value)]}
    if isinstance(value, datetime):
        return {"__cruet__": ["d", value.isoformat()]}
    if isinstance(value, dict):
        return {k: _tag(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_tag(v) for v in value]
    return value


def _untag(value):
    from datetime import datetime
    try:
        from markupsafe import Markup
    except Exception:
        Markup = None
    import uuid
    if isinstance(value, dict):
        if set(value.keys()) == {"__cruet__"}:
            tag, payload = value["__cruet__"]
            if tag == "t":
                return tuple(_untag(v) for v in payload)
            if tag == "b":
                return base64.b64decode(payload.encode("ascii"))
            if tag == "m" and Markup is not None:
                return Markup(payload)
            if tag == "u":
                return uuid.UUID(payload)
            if tag == "d":
                try:
                    return datetime.fromisoformat(payload)
                except Exception:
                    return payload
        return {k: _untag(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_untag(v) for v in value]
    return value


def _sign(payload_bytes, secret):
    """Create an HMAC-SHA256 signature for the given payload."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()


def _encode_session(data, secret):
    """Serialize and sign session data."""
    payload = json.dumps(_tag(data), separators=(",", ":"), sort_keys=True)
    payload_bytes = payload.encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    sig = _sign(payload_bytes, secret)
    return b64 + "." + sig


def _decode_session(cookie_value, secret):
    """Verify signature and deserialize session data."""
    if not cookie_value or "." not in cookie_value:
        return None

    b64, sig = cookie_value.rsplit(".", 1)

    # Restore base64 padding
    padding = 4 - len(b64) % 4
    if padding != 4:
        b64 += "=" * padding

    try:
        payload_bytes = base64.urlsafe_b64decode(b64)
    except Exception:
        return None

    expected_sig = _sign(payload_bytes, secret)
    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        return _untag(json.loads(payload_bytes))
    except (json.JSONDecodeError, ValueError):
        return None


def _set_vary_cookie(response):
    """Ensure 'Cookie' is in the Vary header."""
    vary = response.headers.get("Vary", "")
    if "Cookie" not in vary:
        if vary:
            vary = vary + ", Cookie"
        else:
            vary = "Cookie"
        response.headers.set("Vary", vary)


def _build_cookie_header(name, value, path="/", domain=None, max_age=None,
                          expires=None, secure=False, httponly=True,
                          samesite=None, partitioned=False):
    """Build a Set-Cookie header string manually."""
    parts = [f"{name}={value}"]
    if domain:
        parts.append(f"Domain={domain}")
    if path:
        parts.append(f"Path={path}")
    if expires:
        if isinstance(expires, str):
            parts.append(f"Expires={expires}")
        else:
            from werkzeug.http import http_date
            parts.append(f"Expires={http_date(expires)}")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if httponly:
        parts.append("HttpOnly")
    if secure:
        parts.append("Secure")
    if samesite:
        parts.append(f"SameSite={samesite}")
    if partitioned:
        parts.append("Partitioned")
    return "; ".join(parts)


class SessionInterface:
    def open_session(self, app, request):
        raise NotImplementedError

    def save_session(self, app, session, response):
        raise NotImplementedError


class SecureCookieSessionInterface(SessionInterface):
    def get_cookie_name(self, app):
        return app.config.get("SESSION_COOKIE_NAME", "session")

    def open_session(self, app, request):
        secret = app.secret_key
        if not secret:
            return NullSession()

        cookie_name = self.get_cookie_name(app)
        cookie_value = request.cookies.get(cookie_name)

        if not cookie_value:
            return Session()

        data = _decode_session(cookie_value, secret)
        if data is not None:
            return Session(data)

        fallbacks = app.config.get("SECRET_KEY_FALLBACKS")
        if fallbacks:
            for fallback_key in fallbacks:
                data = _decode_session(cookie_value, fallback_key)
                if data is not None:
                    session = Session(data)
                    session.modified = True
                    return session

        return Session()

    def save_session(self, app, session, response):
        from datetime import datetime, timedelta, timezone

        secret = app.secret_key
        if not secret:
            return

        is_permanent_refresh = (
            session.permanent
            and app.config.get("SESSION_REFRESH_EACH_REQUEST", True)
        )

        if session.accessed or is_permanent_refresh:
            _set_vary_cookie(response)

        should_save = session.modified
        if not should_save and is_permanent_refresh:
            should_save = True

        if not should_save:
            return

        cookie_name = self.get_cookie_name(app)
        path = _get_cookie_path(app)
        domain = _get_cookie_domain(app)
        secure = app.config.get("SESSION_COOKIE_SECURE", False)
        httponly = app.config.get("SESSION_COOKIE_HTTPONLY", True)
        partitioned = app.config.get("SESSION_COOKIE_PARTITIONED", False)

        samesite = app.config.get("SESSION_COOKIE_SAMESITE", "Lax")
        if samesite is not None:
            valid = {"Strict", "Lax", "None"}
            if samesite not in valid:
                raise ValueError(
                    f"SameSite must be 'Strict', 'Lax', or 'None', not {samesite!r}."
                )

        if not session:
            header = _build_cookie_header(
                cookie_name, "",
                path=path, domain=domain,
                expires="Thu, 01 Jan 1970 00:00:00 GMT",
                max_age=0,
                secure=secure, httponly=httponly,
                samesite=samesite, partitioned=partitioned,
            )
            response.headers.set("Set-Cookie", header)
            return

        value = _encode_session(dict(session), secret)

        max_age = None
        expires = None
        if session.permanent:
            lifetime = app.config.get("PERMANENT_SESSION_LIFETIME", 2678400)
            if isinstance(lifetime, timedelta):
                max_age = int(lifetime.total_seconds())
            else:
                max_age = lifetime
            expires = datetime.now(timezone.utc) + timedelta(seconds=max_age)

        header = _build_cookie_header(
            cookie_name, value,
            path=path, domain=domain,
            max_age=max_age, expires=expires,
            secure=secure, httponly=httponly,
            samesite=samesite, partitioned=partitioned,
        )
        response.headers.set("Set-Cookie", header)


def open_session(app, request):
    return app.session_interface.open_session(app, request)


def save_session(app, session, response):
    return app.session_interface.save_session(app, session, response)


def _get_cookie_path(app):
    """Get the session cookie path from config."""
    return (
        app.config.get("SESSION_COOKIE_PATH")
        or app.config.get("APPLICATION_ROOT")
        or "/"
    )


def _get_cookie_domain(app):
    """Get the session cookie domain from config."""
    return app.config.get("SESSION_COOKIE_DOMAIN")
