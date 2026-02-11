"""Flask-compatible helper functions."""
import json as _json
import mimetypes
import os

from cruet._cruet import CResponse

# Import werkzeug exceptions for abort() compatibility
try:
    import werkzeug.exceptions as _wz_exceptions
    from werkzeug.exceptions import HTTPException
    _has_werkzeug = True
except ImportError:
    _has_werkzeug = False

    class HTTPException(Exception):
        """Base HTTP exception (fallback when werkzeug is unavailable)."""
        def __init__(self, code=500, description=None):
            self.code = code
            self.description = description or ""
            super().__init__(self.description)


def jsonify(*args, **kwargs):
    """Create a JSON response."""
    from cruet.globals import current_app
    try:
        app = current_app._get_current_object()
        return app.json.response(*args, **kwargs)
    except RuntimeError:
        pass

    # Fallback: no app context
    if args and kwargs:
        raise TypeError("jsonify() takes either args or kwargs, not both")

    if args:
        if len(args) == 1:
            data = args[0]
        else:
            data = args
    else:
        data = kwargs

    body = _json.dumps(data)
    return CResponse(body, content_type="application/json")


def redirect(location, code=302):
    """Return a redirect response."""
    try:
        from cruet.globals import current_app
        app = current_app._get_current_object()
        if hasattr(app, "redirect"):
            return app.redirect(location, code)
    except (RuntimeError, LookupError):
        pass
    if _has_werkzeug:
        from werkzeug.utils import redirect as wz_redirect
        return wz_redirect(location, code)
    body = f'<!doctype html>\n<p>Redirecting to <a href="{location}">{location}</a></p>'
    response = CResponse(body, status=code)
    response.headers.set("Location", location)
    return response


def abort(status, *args, **kwargs):
    """Raise an HTTP exception with the given status code."""
    try:
        from cruet.globals import current_app
        app = current_app._get_current_object()
        if hasattr(app, "aborter"):
            app.aborter(status, *args, **kwargs)
            return
    except (RuntimeError, LookupError):
        pass
    if _has_werkzeug:
        _wz_exceptions.abort(status, *args, **kwargs)
    else:
        raise HTTPException(status, *args)


def url_for(endpoint, **values):
    """Build a URL for the given endpoint with values."""
    from cruet.globals import current_app, has_request_context
    from urllib.parse import quote

    app = current_app._get_current_object()

    # Resolve relative endpoints starting with "."
    if endpoint.startswith("."):
        try:
            from cruet.globals import request as req
            bp = getattr(req, 'blueprint', None)
        except (RuntimeError, LookupError):
            bp = None
        if bp:
            endpoint = bp + endpoint  # ".about" -> "frontend.about"
        else:
            endpoint = endpoint[1:]

    # Allow view function objects to be passed as endpoints.
    if callable(endpoint):
        endpoint = getattr(endpoint, "__name__", str(endpoint))

    # Extract special parameters
    _sentinel = object()
    _external_raw = values.pop("_external", _sentinel)
    _external = False if _external_raw is _sentinel else _external_raw
    _anchor = values.pop("_anchor", None)
    _scheme = values.pop("_scheme", None)
    _method = values.pop("_method", None)

    if _scheme:
        if _external_raw is not _sentinel and not _external:
            raise ValueError("When specifying '_scheme', '_external' must be True.")
        _external = True

    # When called from app context without request context,
    # SERVER_NAME is required and URLs are external by default
    if not has_request_context():
        server_name = app.config.get("SERVER_NAME")
        if not server_name:
            raise RuntimeError(
                "Application was not able to create a URL adapter for request"
                " independent URL generation. You might be able to fix this by"
                " setting the SERVER_NAME config variable."
            )
        _external = True

    server_name = None
    script_name = ""
    url_scheme = None
    request_host = None

    # If method selection is requested, use Werkzeug's builder for accuracy.
    if has_request_context():
        try:
            from cruet.globals import request as req
            env = getattr(req, "environ", {}) or {}
            request_host = env.get("HTTP_HOST") or env.get("SERVER_NAME")
            server_name = request_host or app.config.get("SERVER_NAME")
            script_name = env.get("SCRIPT_NAME", "")
            url_scheme = env.get("wsgi.url_scheme") or _scheme or app.config.get("PREFERRED_URL_SCHEME")
            if endpoint == "static" and getattr(app, "static_host", None) and app.host_matching:
                server_name = app.static_host
                _external = True
                if not _scheme:
                    _scheme = app.config.get("PREFERRED_URL_SCHEME") or "http"
                url_scheme = _scheme
            adapter = app._get_adapter(server_name=server_name, script_name=script_name, url_scheme=url_scheme, request_host=request_host)
        except (RuntimeError, LookupError):
            adapter = app._get_adapter()
    else:
        adapter = app._get_adapter()

    if _method is not None:
        wz_map = app.url_map._build_wz_map()
        if has_request_context():
            if not server_name:
                server_name = app.config.get("SERVER_NAME") or "localhost"
            if url_scheme is None:
                url_scheme = app.config.get("PREFERRED_URL_SCHEME") or "http"
            adapter = wz_map.bind(
                server_name,
                script_name=script_name or "",
                url_scheme=url_scheme,
            )
        else:
            server_name = app.config.get("SERVER_NAME") or "localhost"
            adapter = wz_map.bind(server_name)

    # Call url_default_functions to inject default values
    # Determine blueprint from endpoint name or request context
    bp_name = None
    if "." in endpoint:
        bp_name = endpoint.rsplit(".", 1)[0]
    if not bp_name:
        try:
            from cruet.globals import request as req
            bp_name = getattr(req, 'blueprint', None)
        except (RuntimeError, LookupError):
            pass

    for func in app.url_default_functions.get(None, []):
        func(endpoint, values)
    if bp_name:
        for func in app.url_default_functions.get(bp_name, []):
            func(endpoint, values)

    # Save special values for error handlers
    _special_values = {
        "_external": _external,
        "_anchor": _anchor,
        "_method": _method,
        "_scheme": _scheme,
    }

    try:
        try:
            url = adapter.build(endpoint, values, method=_method)
        except TypeError:
            if _method is not None:
                try:
                    wz_map = app.url_map._build_wz_map()
                    if has_request_context():
                        adapter = wz_map.bind(
                            server_name or app.config.get("SERVER_NAME") or "localhost",
                            script_name=script_name or "",
                            url_scheme=url_scheme or app.config.get("PREFERRED_URL_SCHEME") or "http",
                        )
                    else:
                        adapter = wz_map.bind(server_name)
                    url = adapter.build(endpoint, values, method=_method)
                except Exception:
                    url = adapter.build(endpoint, values)
            else:
                url = adapter.build(endpoint, values)
    except LookupError as e:
        # Wrap LookupError into werkzeug BuildError for url_build_error_handlers
        try:
            from werkzeug.routing import BuildError
            error = BuildError(endpoint, values, _method, str(e))
        except (ImportError, TypeError):
            error = e
        return app.handle_url_build_error(error, endpoint, _special_values)
    except Exception as e:
        return app.handle_url_build_error(e, endpoint, _special_values)

    # URL-encode the path portion
    url = quote(url, safe="/:@!$&'()*+,;=-._~?#")

    if _external:
        scheme = _scheme or app.config.get("PREFERRED_URL_SCHEME") or "http"
        if endpoint == "static" and getattr(app, "static_host", None) and app.host_matching:
            server_name = app.static_host
        elif has_request_context():
            try:
                from cruet.globals import request as req
                env = getattr(req, "environ", {}) or {}
                server_name = env.get("HTTP_HOST") or env.get("SERVER_NAME")
            except (RuntimeError, LookupError):
                server_name = None
            if not server_name:
                server_name = app.config.get("SERVER_NAME") or "localhost"
        else:
            server_name = app.config.get("SERVER_NAME") or "localhost"
        if url.startswith(("http://", "https://")):
            pass
        else:
            url = f"{scheme}://{server_name}{url}"

    if _anchor is not None:
        _anchor = quote(_anchor, safe="")
        url = f"{url}#{_anchor}"

    return url


def make_response(*args):
    """Create a response object from the given arguments."""
    from cruet.globals import current_app

    try:
        app = current_app._get_current_object()
    except RuntimeError:
        app = None

    if app is not None:
        if not args:
            return app.make_response("")
        if len(args) == 1:
            return app.make_response(args[0])
        return app.make_response(args)

    # Fallback: no app context
    if not args:
        return CResponse("")
    if len(args) == 1:
        if isinstance(args[0], CResponse):
            return args[0]
        return CResponse(args[0])
    elif len(args) == 2:
        return CResponse(args[0], status=args[1])
    elif len(args) == 3:
        response = CResponse(args[0], status=args[1])
        if isinstance(args[2], dict):
            for k, v in args[2].items():
                response.headers.set(k, v)
        return response
    else:
        raise TypeError(f"make_response takes 0-3 args, got {len(args)}")


def flash(message, category="message"):
    """Flash a message for the next request."""
    from cruet.globals import session
    from cruet.ctx import _request_ctx_var
    flashes = session.get("_flashes", [])
    flashes.append((category, message))
    session["_flashes"] = flashes
    try:
        ctx = _request_ctx_var.get()
        ctx._flashes = None  # invalidate cache
        try:
            from cruet.signals import message_flashed
            message_flashed.send(ctx.app, message=message, category=category)
        except Exception:
            pass
    except LookupError:
        pass


def get_flashed_messages(with_categories=False, category_filter=()):
    """Retrieve flashed messages from the session."""
    from cruet.globals import session
    from cruet.ctx import _request_ctx_var

    try:
        ctx = _request_ctx_var.get()
        flashes = getattr(ctx, "_flashes", None)
    except LookupError:
        ctx = None
        flashes = None

    if flashes is None:
        flashes = session.pop("_flashes", [])
        # JSON serialization converts tuples to lists; convert back
        flashes = [tuple(item) if isinstance(item, list) else item for item in flashes]
        if ctx is not None:
            ctx._flashes = flashes

    if category_filter:
        flashes = [(cat, msg) for cat, msg in flashes if cat in category_filter]
    if with_categories:
        return flashes
    return [msg for _, msg in flashes]


def send_file(path_or_file, mimetype=None, as_attachment=False,
              download_name=None, max_age=None):
    """Send a file to the client."""
    from cruet.wrappers import Response
    if isinstance(path_or_file, (str, os.PathLike)):
        path = os.fspath(path_or_file)
        if not os.path.isabs(path):
            try:
                from cruet.globals import current_app
                path = os.path.join(current_app.root_path, path)
            except (RuntimeError, LookupError):
                pass
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        with open(path, "rb") as f:
            data = f.read()
        if mimetype is None:
            mimetype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if download_name is None:
            download_name = os.path.basename(path)
        if max_age is None:
            try:
                from cruet.globals import current_app
                max_age = current_app.get_send_file_max_age(path)
            except (RuntimeError, LookupError):
                pass
    else:
        data = path_or_file.read()
        if mimetype is None:
            mimetype = "application/octet-stream"

    response = Response(data, content_type=mimetype)
    response.direct_passthrough = True

    if as_attachment:
        if download_name:
            response.headers.set(
                "Content-Disposition",
                f'attachment; filename="{download_name}"'
            )
        else:
            response.headers.set("Content-Disposition", "attachment")

    if max_age is not None:
        response.headers.set("Cache-Control", f"max-age={max_age}")

    return response


def send_from_directory(directory, path, **kwargs):
    """Send a file from a directory, securely."""
    directory = os.fspath(directory) if hasattr(directory, "__fspath__") else directory
    if not os.path.isabs(directory):
        try:
            from cruet.globals import current_app
            directory = os.path.join(current_app.root_path, directory)
        except (RuntimeError, LookupError):
            pass
    directory = os.path.abspath(directory)
    safe_path = os.path.normpath(path)
    if os.path.isabs(safe_path) or safe_path.startswith(".."):
        from cruet.app import NotFound
        raise NotFound()
    full_path = os.path.join(directory, safe_path)
    full_path = os.path.abspath(full_path)
    if not full_path.startswith(directory + os.sep) and full_path != directory:
        from cruet.app import NotFound
        raise NotFound()
    if not os.path.isfile(full_path):
        from cruet.app import NotFound
        raise NotFound()
    return send_file(full_path, **kwargs)


def stream_with_context(generator_or_function):
    """Preserve the request context during streaming."""
    from cruet.ctx import _request_ctx_var, RequestContext

    try:
        ctx = _request_ctx_var.get()
    except LookupError:
        raise RuntimeError(
            "Attempted to stream with context but there was no context to copy."
        )

    if callable(generator_or_function) and not hasattr(generator_or_function, "__next__"):
        def wrapper(*a, **kw):
            return stream_with_context(generator_or_function(*a, **kw))
        return wrapper

    gen = generator_or_function

    class _StreamWithContext:
        def __init__(self, app_ctx, environ, session, gen_obj):
            self._ctx = RequestContext(app_ctx, environ)
            self._ctx.session = session
            self._gen = iter(gen_obj)
            self._started = False

        def __iter__(self):
            return self

        def __next__(self):
            if not self._started:
                self._ctx.push()
                self._started = True
            try:
                return next(self._gen)
            except StopIteration:
                self.close()
                raise

        def close(self):
            if self._started:
                try:
                    if hasattr(self._gen, "close"):
                        self._gen.close()
                finally:
                    self._ctx.pop()
                    self._started = False

    return _StreamWithContext(ctx.app, ctx.environ, ctx.session, gen)
