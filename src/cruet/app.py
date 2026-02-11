"""Cruet application class -- Flask-compatible API."""
import io
import asyncio
import importlib.metadata
import importlib.util
import os
import pathlib
import sys
import traceback

from cruet._cruet import Rule, Map, CResponse
from cruet.cli import AppGroup
from cruet.config import Config
from cruet.ctx import AppContext, RequestContext, _AppCtxGlobals

#: Default configuration values, matching Flask's defaults.
_default_config = {
    "DEBUG": False,
    "TESTING": False,
    "SECRET_KEY": None,
    "PERMANENT_SESSION_LIFETIME": 2678400,  # 31 days in seconds
    "SESSION_COOKIE_NAME": "session",
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SECURE": False,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_DOMAIN": None,
    "SESSION_COOKIE_PATH": None,
    "SESSION_REFRESH_EACH_REQUEST": True,
    "MAX_CONTENT_LENGTH": None,
    "MAX_FORM_MEMORY_SIZE": 500_000,
    "MAX_FORM_PARTS": 1000,
    "MAX_COOKIE_SIZE": 4093,
    "PREFERRED_URL_SCHEME": "http",
    "TRAP_HTTP_EXCEPTIONS": False,
    "TRAP_BAD_REQUEST_ERRORS": None,
    "PROPAGATE_EXCEPTIONS": None,
    "JSON_SORT_KEYS": False,
    "JSONIFY_MIMETYPE": "application/json",
    "SERVER_NAME": None,
    "APPLICATION_ROOT": "/",
    "TRUSTED_HOSTS": None,
    "SEND_FILE_MAX_AGE_DEFAULT": None,
    "TEMPLATES_AUTO_RELOAD": None,
    "SECRET_KEY_FALLBACKS": None,
}


def _static_view(filename):
    from cruet.globals import current_app
    return current_app.send_static_file(filename)


class URLMap:
    """Python wrapper around C Map that adds a converters dict and rule tracking."""

    def __init__(self, host_matching=False, subdomain_matching=False):
        self._map = Map()
        self._rules = []
        self._rule_specs = []
        self._path_methods = {}
        self._wz_rulefactories = []
        self._force_werkzeug = False
        self._host_matching = host_matching
        self._subdomain_matching = subdomain_matching
        self._wz_map = None
        self.converters = {
            "default": str,
        }
        self._default_converters = dict(self.converters)

    def add(self, rule):
        if isinstance(rule, Rule):
            self._rules.append(rule)
            return self._map.add(rule)
        self._wz_rulefactories.append(rule)
        self._force_werkzeug = True
        self._wz_map = None
        return None

    def add_spec(self, spec):
        self._rule_specs.append(spec)
        rule = spec.get("rule")
        methods = spec.get("methods")
        if rule is not None:
            prev = self._path_methods.get(rule)
            if prev is not None and methods is not None and set(prev) != set(methods):
                self._force_werkzeug = True
            elif prev is not None and prev is not None and methods is None:
                self._force_werkzeug = True
            elif prev is None and methods is not None:
                self._path_methods[rule] = list(methods)
        self._wz_map = None

    def _has_custom_converters(self):
        if self.converters.keys() != self._default_converters.keys():
            return True
        for key, val in self.converters.items():
            if self._default_converters.get(key) is not val:
                return True
        return False

    def _needs_werkzeug(self):
        if self._force_werkzeug or self._wz_rulefactories:
            return True
        if self._host_matching or self._subdomain_matching:
            return True
        for spec in self._rule_specs:
            if spec.get("subdomain") or spec.get("host"):
                return True
        if self._has_custom_converters():
            return True
        return False

    def _build_wz_map(self):
        from werkzeug.routing import Map as WzMap
        from werkzeug.routing import Rule as WzRule
        from werkzeug.routing import BaseConverter, UnicodeConverter, IntegerConverter, FloatConverter, PathConverter, AnyConverter, UUIDConverter

        converters = {}
        for name, conv in self.converters.items():
            if name == "default":
                continue
            if isinstance(conv, type) and issubclass(conv, BaseConverter):
                converters[name] = conv
            else:
                if conv is str:
                    converters[name] = UnicodeConverter
                elif conv is int:
                    converters[name] = IntegerConverter
                elif conv is float:
                    converters[name] = FloatConverter
                else:
                    converters[name] = UnicodeConverter

        converters.setdefault("string", UnicodeConverter)
        converters.setdefault("int", IntegerConverter)
        converters.setdefault("float", FloatConverter)
        converters.setdefault("path", PathConverter)
        converters.setdefault("any", AnyConverter)
        converters.setdefault("uuid", UUIDConverter)

        rules = list(self._wz_rulefactories)
        for spec in self._rule_specs:
            rules.append(
                WzRule(
                    spec["rule"],
                    endpoint=spec.get("endpoint"),
                    methods=spec.get("methods"),
                    strict_slashes=spec.get("strict_slashes", True),
                    defaults=spec.get("defaults"),
                    subdomain=spec.get("subdomain"),
                    host=spec.get("host"),
                )
            )
        map_kwargs = {"rules": rules, "host_matching": self._host_matching, "converters": converters}
        try:
            WzMap(subdomain_matching=True)
            map_kwargs["subdomain_matching"] = self._subdomain_matching
        except TypeError:
            pass
        wz_map = WzMap(**map_kwargs)
        wz_map.converters.update(self.converters)
        return wz_map

    def bind(self, *args, **kwargs):
        if self._needs_werkzeug():
            if self._wz_map is None:
                self._wz_map = self._build_wz_map()
            return self._wz_map.bind(*args, **kwargs)
        if kwargs:
            server_name = args[0] if args else kwargs.get("server_name")
            return self._map.bind(server_name)
        return self._map.bind(*args)

    def iter_rules(self):
        if self._needs_werkzeug():
            if self._wz_map is None:
                self._wz_map = self._build_wz_map()
            return self._wz_map.iter_rules()
        return iter(self._rules)

    @property
    def host_matching(self):
        return self._host_matching

    @property
    def subdomain_matching(self):
        return self._subdomain_matching

    def __iter__(self):
        return iter(self._rules)

    def is_endpoint_expecting(self, endpoint, argument):
        """Check if an endpoint expects a given argument."""
        for rule in self._rules:
            if rule.endpoint == endpoint:
                # Check if the rule pattern contains the argument
                pattern = rule.rule if hasattr(rule, 'rule') else str(rule)
                if f"<{argument}>" in pattern or f"<path:{argument}>" in pattern:
                    return True
                if f"<int:{argument}>" in pattern or f"<float:{argument}>" in pattern:
                    return True
                if f"<string:{argument}>" in pattern or f"<any:{argument}>" in pattern:
                    return True
                if f"<uuid:{argument}>" in pattern:
                    return True
        return False

    def __getattr__(self, name):
        return getattr(self._map, name)


def _find_package_path(import_name):
    if not import_name:
        return os.getcwd()
    root_mod_name, _, _ = import_name.partition(".")
    try:
        root_spec = importlib.util.find_spec(root_mod_name)
        if root_spec is None:
            raise ValueError("not found")
    except (ImportError, ValueError):
        return os.getcwd()

    if root_spec.submodule_search_locations:
        if root_spec.origin is None or root_spec.origin == "namespace":
            package_spec = importlib.util.find_spec(import_name)
            if package_spec is not None and package_spec.submodule_search_locations:
                package_path = pathlib.Path(
                    os.path.commonpath(package_spec.submodule_search_locations)
                )
                search_location = next(
                    location
                    for location in root_spec.submodule_search_locations
                    if package_path.is_relative_to(location)
                )
            else:
                search_location = root_spec.submodule_search_locations[0]
            return os.path.dirname(search_location)
        return os.path.dirname(os.path.dirname(root_spec.origin))
    return os.path.dirname(root_spec.origin)


def find_package(import_name):
    package_path = _find_package_path(import_name)
    py_prefix = os.path.abspath(sys.prefix)

    if pathlib.PurePath(package_path).is_relative_to(py_prefix):
        return py_prefix, package_path

    site_parent, site_folder = os.path.split(package_path)
    if site_folder.lower() == "site-packages":
        parent, folder = os.path.split(site_parent)
        if folder.lower() == "lib":
            return parent, package_path
        if os.path.basename(parent).lower() == "lib":
            return os.path.dirname(parent), package_path
        return site_parent, package_path

    return None, package_path


class Cruet:
    """The main application class, API-compatible with Flask."""

    #: The class to use for the ``g`` object. Defaults to :class:`_AppCtxGlobals`.
    app_ctx_globals_class = _AppCtxGlobals

    #: The response class to use. Defaults to CResponse.
    response_class = CResponse

    try:
        from werkzeug.exceptions import Aborter as _Aborter
    except Exception:
        class _Aborter:
            def __call__(self, code, *args, **kwargs):
                raise Exception(code)
    aborter_class = _Aborter

    #: The config class to use. Defaults to :class:`Config`.
    config_class = Config

    #: Default configuration values, matching Flask's defaults.
    default_config = _default_config

    #: The JSON provider class.
    json_provider_class = None  # Set below after DefaultJSONProvider import

    #: The CLI runner class for tests.
    test_cli_runner_class = None

    def __init__(self, import_name=None, static_folder="static",
                 static_url_path=None, template_folder="templates",
                 root_path=None, host_matching=False,
                 subdomain_matching=False, static_host=None,
                 instance_path=None, instance_relative_config=False):
        self.import_name = import_name
        if static_folder == "":
            static_folder = "static"
        self._static_folder = static_folder
        if static_url_path == "":
            static_url_path = "/static"
        self.static_url_path = static_url_path if static_url_path is not None else "/static"
        self.template_folder = template_folder
        self._explicit_root_path = root_path
        if instance_path is None:
            instance_path = self.auto_find_instance_path()
        elif not os.path.isabs(instance_path):
            raise ValueError(
                "If an instance path is provided it must be absolute."
                " A relative path was given instead."
            )
        self.instance_path = instance_path
        config_root = self.instance_path if instance_relative_config else self.root_path
        self.config = self.config_class(config_root, _default_config)
        self._jinja_env = None
        self.url_map = URLMap(host_matching=host_matching, subdomain_matching=subdomain_matching)
        self.view_functions = {}
        self.before_request_funcs = []
        self.after_request_funcs = []
        self.teardown_request_funcs = []
        self.teardown_appcontext_funcs = []
        self.error_handlers = {}
        self._adapter = None
        self.blueprints = {}
        self.extensions = {}
        self.template_context_processors = []
        self._endpoint_defaults = {}
        self._logger = None
        self.cli = AppGroup(name=self.import_name)
        import weakref
        self.cli._app_ref = weakref.ref(self)
        self.url_build_error_handlers = []
        self.url_default_functions = {}
        self.url_value_preprocessors = {}
        self._got_first_request = False
        self.host_matching = host_matching
        self.subdomain_matching = subdomain_matching
        if static_host and not host_matching:
            raise AssertionError(
                "Invalid static_host/host_matching combination."
            )
        if host_matching and static_host is None and self._static_folder is not None:
            raise AssertionError(
                "Invalid static_host/host_matching combination."
            )
        self.static_host = static_host

        # JSON provider
        from cruet.json_provider import DefaultJSONProvider
        if self.json_provider_class is None:
            self.json_provider_class = DefaultJSONProvider
        self.json = self.json_provider_class(self)

        # Session interface
        from cruet.sessions import SecureCookieSessionInterface
        if getattr(self, "session_interface", None) is None:
            self.session_interface = SecureCookieSessionInterface()

        # Aborter (Flask parity)
        self.aborter = self.aborter_class()

        # Template-related deferred registrations
        self._template_filters = {}
        self._template_tests = {}
        self._template_globals = {}

        # Auto-register static file route
        if self._static_folder is not None:
            static_path = self.static_url_path.rstrip("/")
            self.add_url_rule(
                static_path + "/<path:filename>",
                endpoint="static",
                view_func=_static_view,
                methods=["GET"],
                host=self.static_host if self.host_matching else None,
            )

    def ensure_sync(self, func):
        if asyncio.iscoroutinefunction(func):
            try:
                from asgiref.sync import async_to_sync
                return async_to_sync(func)
            except Exception:
                def _run(*args, **kwargs):
                    return asyncio.run(func(*args, **kwargs))
                return _run
        return func

    def _call_handler(self, func, *args, **kwargs):
        rv = self.ensure_sync(func)(*args, **kwargs)
        if asyncio.iscoroutine(rv):
            return asyncio.run(rv)
        return rv

    @property
    def jinja_env(self):
        """The Jinja2 Environment for this app (lazy, cached)."""
        from cruet.templating import _get_jinja_env
        return _get_jinja_env(self)

    @property
    def debug(self):
        return self.config["DEBUG"]

    @debug.setter
    def debug(self, value):
        self.config["DEBUG"] = bool(value)

    @property
    def testing(self):
        return self.config["TESTING"]

    @testing.setter
    def testing(self, value):
        self.config["TESTING"] = bool(value)

    @property
    def secret_key(self):
        return self.config["SECRET_KEY"]

    @secret_key.setter
    def secret_key(self, value):
        self.config["SECRET_KEY"] = value

    @property
    def name(self):
        return self.import_name

    @property
    def logger(self):
        if self._logger is None:
            from cruet.logging import create_logger
            self._logger = create_logger(self)
        return self._logger

    @property
    def static_folder(self):
        if self._static_folder is None:
            return None
        sf = os.fspath(self._static_folder) if hasattr(self._static_folder, '__fspath__') else self._static_folder
        if os.path.isabs(sf):
            return sf
        return os.path.join(self._root_path, sf)

    @static_folder.setter
    def static_folder(self, value):
        if value is not None:
            value = os.fspath(value) if hasattr(value, '__fspath__') else value
        self._static_folder = value

    @property
    def has_static_folder(self):
        return self.static_folder is not None and os.path.isdir(self.static_folder)

    @property
    def _root_path(self):
        if self._explicit_root_path is not None:
            return self._explicit_root_path
        if self.import_name:
            mod = sys.modules.get(self.import_name)
            if mod and hasattr(mod, "__file__") and mod.__file__:
                return os.path.dirname(os.path.abspath(mod.__file__))
        return os.getcwd()

    # Alias for Flask compatibility (Flask exposes root_path as a public attr)
    @property
    def root_path(self):
        return self._root_path

    @root_path.setter
    def root_path(self, value):
        self._explicit_root_path = value

    def auto_find_instance_path(self):
        prefix, package_path = find_package(self.import_name)
        if prefix is None:
            return os.path.join(package_path, "instance")
        return os.path.join(prefix, "var", f"{self.name}-instance")

    @property
    def permanent_session_lifetime(self):
        from datetime import timedelta
        val = self.config.get("PERMANENT_SESSION_LIFETIME", 2678400)
        if isinstance(val, timedelta):
            return val
        return timedelta(seconds=val)

    def register_blueprint(self, blueprint, **options):
        """Register a Blueprint on this application."""
        if isinstance(blueprint, Cruet):
            raise TypeError("Cannot register an app as a blueprint.")
        blueprint._register(self, options)

    def _get_adapter(self, server_name=None, script_name=None, url_scheme=None, request_host=None):
        if server_name is None and script_name is None and url_scheme is None and request_host is None:
            if self._adapter is None:
                server_name = self.config.get("SERVER_NAME") or "localhost"
                self._adapter = self.url_map.bind(server_name)
            return self._adapter
        server_name = server_name or (self.config.get("SERVER_NAME") or "localhost")
        script_name = script_name or ""
        url_scheme = url_scheme or self.config.get("PREFERRED_URL_SCHEME") or "http"

        if getattr(self.url_map, "_needs_werkzeug", None) and self.url_map._needs_werkzeug():
            if self.subdomain_matching and not self.host_matching:
                base_server = self.config.get("SERVER_NAME") or server_name
                subdomain = None
                if request_host:
                    req_host = request_host.split(":", 1)[0]
                    srv_host = base_server.split(":", 1)[0]
                    if req_host == srv_host:
                        subdomain = ""
                    elif req_host.endswith("." + srv_host):
                        subdomain = req_host[: -(len(srv_host) + 1)]
                    else:
                        try:
                            werkzeug_3_2 = importlib.metadata.version("werkzeug") >= "3.2."
                        except Exception:
                            werkzeug_3_2 = False
                        subdomain = "" if werkzeug_3_2 else "<invalid>"
                return self.url_map.bind(
                    base_server,
                    script_name=script_name,
                    subdomain=subdomain,
                    url_scheme=url_scheme,
                )
        return self.url_map.bind(server_name, script_name=script_name, url_scheme=url_scheme)

    def route(self, rule_str, **options):
        """Decorator to register a view function for a URL rule."""
        def decorator(f):
            endpoint = options.pop("endpoint", f.__name__)
            methods = options.pop("methods", None)
            strict_slashes = options.pop("strict_slashes", True)
            defaults = options.pop("defaults", None)
            subdomain = options.pop("subdomain", None)
            self.add_url_rule(rule_str, endpoint, f, methods=methods,
                              strict_slashes=strict_slashes, defaults=defaults,
                              subdomain=subdomain, **options)
            return f
        return decorator

    def add_url_rule(self, rule_str, endpoint=None, view_func=None,
                     methods=None, strict_slashes=True, defaults=None,
                     subdomain=None, provide_automatic_options=None, **kwargs):
        """Add a URL rule to the map."""
        if self._got_first_request:
            raise AssertionError(
                "The setup method 'add_url_rule' can no longer be"
                " called on the application. It has already handled"
                " its first request, any changes will not be applied"
                " consistently.\n"
                "Make sure all imports, decorators, functions, etc."
                " needed to set up the application are done before"
                " running it."
            )
        if isinstance(methods, str):
            raise TypeError(
                "Allowed methods must be a list of strings, for"
                ' example: @app.route(..., methods=["POST"])'
            )
        if endpoint is None and view_func is not None:
            endpoint = view_func.__name__
        if methods is None and view_func is not None:
            view_methods = getattr(view_func, "methods", None)
            if view_methods:
                methods = list(view_methods)
        if methods is None:
            methods = ["GET"]
        if methods:
            methods = [m.upper() for m in methods]
            if "OPTIONS" in methods:
                self.url_map._force_werkzeug = True
                self.url_map._wz_map = None
        # Track if OPTIONS was explicitly provided
        has_options = False
        if methods:
            has_options = any(m.upper() == "OPTIONS" for m in methods)
            explicit_methods = {m.upper() for m in methods}
        else:
            explicit_methods = None
        host = kwargs.pop("host", None)
        if not self.host_matching:
            host = None
        rule = Rule(rule_str, endpoint=endpoint, methods=methods,
                    strict_slashes=strict_slashes)
        self.url_map.add(rule)
        self.url_map.add_spec(
            {
                "rule": rule_str,
                "endpoint": endpoint,
                "methods": methods,
                "strict_slashes": strict_slashes,
                "defaults": defaults,
                "subdomain": subdomain,
                "host": host,
            }
        )
        if has_options:
            self._explicit_options_endpoints = getattr(self, '_explicit_options_endpoints', set())
            self._explicit_options_endpoints.add(endpoint)
        if explicit_methods is not None:
            self._explicit_methods_endpoints = getattr(self, '_explicit_methods_endpoints', {})
            self._explicit_methods_endpoints[endpoint] = explicit_methods

        # Handle provide_automatic_options
        pao = provide_automatic_options
        if pao is None and view_func is not None:
            pao = getattr(view_func, 'provide_automatic_options', None)
        if pao is False:
            self._no_auto_options_endpoints = getattr(self, '_no_auto_options_endpoints', set())
            self._no_auto_options_endpoints.add(endpoint)
        elif pao is True:
            self._force_auto_options_endpoints = getattr(self, '_force_auto_options_endpoints', set())
            self._force_auto_options_endpoints.add(endpoint)
        if view_func is not None:
            if endpoint in self.view_functions:
                existing = self.view_functions[endpoint]
                if existing is not view_func:
                    existing_self = getattr(existing, "__self__", None)
                    existing_func = getattr(existing, "__func__", None)
                    new_self = getattr(view_func, "__self__", None)
                    new_func = getattr(view_func, "__func__", None)
                    same_bound = (
                        existing_self is not None
                        and new_self is not None
                        and existing_func is new_func
                        and existing_self is new_self
                    )
                    if not same_bound:
                        raise AssertionError(
                            "View function mapping is overwriting an existing endpoint function"
                        )
            else:
                self.view_functions[endpoint] = view_func
        if defaults:
            existing = self._endpoint_defaults.get(endpoint, {})
            existing.update(defaults)
            self._endpoint_defaults[endpoint] = existing
        # Reset adapter since rules changed
        self._adapter = None

    def endpoint(self, endpoint_name):
        """Decorator to register a view function for an endpoint."""
        def decorator(f):
            self.view_functions[endpoint_name] = f
            return f
        return decorator

    def before_request(self, f):
        """Register a function to run before each request."""
        self.before_request_funcs.append(f)
        return f

    def after_request(self, f):
        """Register a function to run after each request."""
        self.after_request_funcs.append(f)
        return f

    def teardown_request(self, f):
        """Register a function to run at teardown of each request."""
        self.teardown_request_funcs.append(f)
        return f

    def teardown_appcontext(self, f):
        """Register a function called when the app context is popped."""
        self.teardown_appcontext_funcs.append(f)
        return f

    def before_first_request(self, f):
        """Register a function to run before the first request."""
        # Deprecated in Flask 2.3 but still tested
        if not hasattr(self, '_before_first_request_funcs'):
            self._before_first_request_funcs = []
        self._before_first_request_funcs.append(f)
        return f

    def errorhandler(self, code_or_exception):
        """Register an error handler for a status code or exception class."""
        def decorator(f):
            self._register_error_handler(None, code_or_exception, f)
            return f
        return decorator

    def register_error_handler(self, code_or_exception, f):
        """Non-decorator version of errorhandler()."""
        self._register_error_handler(None, code_or_exception, f)

    def _register_error_handler(self, key, code_or_exception, f):
        """Internal error handler registration.

        key is None for app-level handlers or a blueprint name for blueprint-scoped handlers.
        """
        if isinstance(code_or_exception, int):
            # Validate that it's a recognized HTTP error code
            try:
                from werkzeug.exceptions import default_exceptions
                if code_or_exception not in default_exceptions:
                    raise ValueError(
                        f"Use a subclass of HTTPException with code"
                        f" {code_or_exception!r}. There is no exception for"
                        f" that code."
                    )
            except ImportError:
                pass
        else:
            # Must be a class, not an instance
            if not isinstance(code_or_exception, type):
                raise TypeError(
                    f"{type(code_or_exception).__name__}() is an instance,"
                    f" not a class. Handlers can only be registered for"
                    f" Exception classes or HTTP error codes."
                )
            if not issubclass(code_or_exception, Exception):
                raise ValueError(
                    f"'{code_or_exception.__name__}' is not a subclass of"
                    f" Exception."
                )

        handlers = self.error_handlers.setdefault(key, {})
        if isinstance(code_or_exception, int):
            handlers[code_or_exception] = f
            try:
                from werkzeug.exceptions import default_exceptions
                exc_class = default_exceptions.get(code_or_exception)
                if exc_class is not None:
                    handlers[exc_class] = f
            except ImportError:
                pass
        else:
            handlers[code_or_exception] = f

    def _check_no_methods_kwarg(self, name, options):
        if "methods" in options:
            raise TypeError(
                f"Use '@app.{name}' instead of '@app.route' to use the"
                f" '{name.upper()}' method. The 'methods' parameter"
                " is not allowed here."
            )

    def get(self, rule_str, **options):
        """Shorthand for @app.route(rule, methods=["GET"])."""
        self._check_no_methods_kwarg("get", options)
        options["methods"] = ["GET"]
        return self.route(rule_str, **options)

    def post(self, rule_str, **options):
        """Shorthand for @app.route(rule, methods=["POST"])."""
        self._check_no_methods_kwarg("post", options)
        options["methods"] = ["POST"]
        return self.route(rule_str, **options)

    def put(self, rule_str, **options):
        """Shorthand for @app.route(rule, methods=["PUT"])."""
        self._check_no_methods_kwarg("put", options)
        options["methods"] = ["PUT"]
        return self.route(rule_str, **options)

    def delete(self, rule_str, **options):
        """Shorthand for @app.route(rule, methods=["DELETE"])."""
        self._check_no_methods_kwarg("delete", options)
        options["methods"] = ["DELETE"]
        return self.route(rule_str, **options)

    def patch(self, rule_str, **options):
        """Shorthand for @app.route(rule, methods=["PATCH"])."""
        self._check_no_methods_kwarg("patch", options)
        options["methods"] = ["PATCH"]
        return self.route(rule_str, **options)

    def context_processor(self, f):
        """Register a template context processor."""
        self.template_context_processors.append(f)
        return f

    def template_filter(self, name=None):
        """Register a custom Jinja2 template filter."""
        def decorator(f):
            self.add_template_filter(f, name)
            return f
        if callable(name):
            f = name
            name = None
            self.add_template_filter(f, None)
            return f
        return decorator

    def add_template_filter(self, f, name=None):
        """Non-decorator version of template_filter()."""
        self._template_filters[name or f.__name__] = f
        if self._jinja_env is not None:
            self._jinja_env.filters[name or f.__name__] = f

    def template_test(self, name=None):
        """Register a custom Jinja2 template test."""
        def decorator(f):
            self.add_template_test(f, name)
            return f
        if callable(name):
            f = name
            name = None
            self.add_template_test(f, None)
            return f
        return decorator

    def add_template_test(self, f, name=None):
        """Non-decorator version of template_test()."""
        self._template_tests[name or f.__name__] = f
        if self._jinja_env is not None:
            self._jinja_env.tests[name or f.__name__] = f

    def template_global(self, name=None):
        """Register a custom Jinja2 template global."""
        def decorator(f):
            self.add_template_global(f, name)
            return f
        if callable(name):
            f = name
            name = None
            self.add_template_global(f, None)
            return f
        return decorator

    def add_template_global(self, f, name=None):
        """Non-decorator version of template_global()."""
        self._template_globals[name or f.__name__] = f
        if self._jinja_env is not None:
            self._jinja_env.globals[name or f.__name__] = f

    def handle_url_build_error(self, error, endpoint, values):
        """Handle a URL build error."""
        for handler in self.url_build_error_handlers:
            rv = handler(error, endpoint, values)
            if rv is not None:
                return rv

        # Re-raise the error
        raise error

    def url_defaults(self, f):
        """Register a URL defaults function for all views."""
        self.url_default_functions.setdefault(None, []).append(f)
        return f

    def inject_url_defaults(self, endpoint, values):
        """Inject URL defaults for the given endpoint."""
        bp_name = endpoint.rsplit(".", 1)[0] if "." in endpoint else None
        for func in self.url_default_functions.get(None, []):
            func(endpoint, values)
        if bp_name:
            for func in self.url_default_functions.get(bp_name, []):
                func(endpoint, values)

    def url_value_preprocessor(self, f):
        """Register a URL value preprocessor for all views."""
        self.url_value_preprocessors.setdefault(None, []).append(f)
        return f

    def send_static_file(self, filename):
        """Send a file from the static folder."""
        from cruet.helpers import send_from_directory
        return send_from_directory(self.static_folder, filename)

    def _static_view(self, filename):
        """Internal view function for serving static files."""
        return self.send_static_file(filename)

    def open_resource(self, resource, mode="rb", encoding=None):
        """Open a resource from the application's root path."""
        if mode not in ("r", "rb", "rt"):
            raise ValueError("Resources can only be opened for reading.")
        path = os.path.join(self.root_path, resource)
        if encoding is not None or "b" not in mode:
            return open(path, mode, encoding=encoding)
        return open(path, mode)

    def get_send_file_max_age(self, filename):
        """Return the cache timeout for send_file."""
        val = self.config.get("SEND_FILE_MAX_AGE_DEFAULT")
        if val is None:
            return None
        try:
            from datetime import timedelta
            if isinstance(val, timedelta):
                return int(val.total_seconds())
        except Exception:
            pass
        return int(val)

    def make_response(self, rv):
        """Convert a view function return value to a response object."""
        from werkzeug.exceptions import HTTPException as WerkzeugHTTPException

        status = None
        headers = None

        # Unpack tuple returns
        if isinstance(rv, tuple):
            tlen = len(rv)
            if tlen == 3:
                rv, status, headers = rv
            elif tlen == 2:
                rv, status_or_headers = rv
                if isinstance(status_or_headers, (dict, list)):
                    headers = status_or_headers
                else:
                    status = status_or_headers
            else:
                raise TypeError(
                    "The view function did not return a valid"
                    " response tuple. The tuple must have the form"
                    " (body, status, headers), (body, status), or"
                    " (body, headers)."
                )

        # Reject None
        if rv is None:
            # Try to include the view function name
            view_name = "unknown"
            try:
                from cruet.globals import request as req_proxy
                ep = getattr(req_proxy, 'endpoint', None)
                if ep:
                    view_name = ep
            except (RuntimeError, LookupError):
                pass
            raise TypeError(
                f"The view function for '{view_name}' returned None,"
                f" but a valid response was expected. Check that it"
                f" has a return statement."
            )

        # Handle werkzeug HTTPException (it's a WSGI app)
        if isinstance(rv, WerkzeugHTTPException):
            # Convert werkzeug exception to a response
            exc_headers = rv.get_headers({})
            if status is not None:
                response = CResponse(rv.get_body(), status=status)
            else:
                response = CResponse(rv.get_body(), status=rv.code,
                                     content_type="text/html; charset=utf-8")
            # Copy headers from werkzeug exception
            for key, value in exc_headers:
                if key.lower() != 'content-type':
                    response.headers.set(key, value)
            if headers:
                self._apply_headers(response, headers)
            return response

        # If already a response, update status/headers
        if isinstance(rv, CResponse):
            if status is not None:
                rv.status_code = int(status) if not isinstance(status, int) else status
            if headers:
                self._apply_headers(rv, headers)
            return rv

        # Check for our Python Response wrapper
        from cruet.wrappers import Response as PyResponse
        if isinstance(rv, PyResponse):
            if status is not None:
                rv.status_code = int(status) if not isinstance(status, int) else status
            if headers:
                self._apply_headers(rv, headers)
            return rv

        # Check for werkzeug Response
        if hasattr(rv, 'status_code') and hasattr(rv, 'headers') and callable(getattr(rv, 'get_data', None)):
            # werkzeug Response-like object
            response = CResponse(rv.get_data(), status=status or rv.status_code,
                                 content_type=rv.content_type)
            for key, value in rv.headers:
                response.headers.set(key, value)
            if status is not None:
                response.status_code = int(status) if not isinstance(status, int) else status
            if headers:
                self._apply_headers(response, headers)
            return response

        # Reject bad types
        if isinstance(rv, bool):
            raise TypeError(
                "The view function return type is not supported:"
                f" it was a {type(rv).__name__}."
            )

        # Convert data types
        if isinstance(rv, dict):
            rv = self.json.response(rv)
            if status is not None:
                rv.status_code = int(status) if not isinstance(status, int) else status
            if headers:
                self._apply_headers(rv, headers)
            return rv

        if isinstance(rv, list):
            rv = self.json.response(rv)
            if status is not None:
                rv.status_code = int(status) if not isinstance(status, int) else status
            if headers:
                self._apply_headers(rv, headers)
            return rv

        if isinstance(rv, (str, bytes)):
            response = CResponse(rv, status=status or 200)
            if headers:
                self._apply_headers(response, headers)
            return response

        # Generator / iterator
        if hasattr(rv, '__next__') or hasattr(rv, '__iter__'):
            try:
                body = b"".join(
                    part.encode("utf-8") if isinstance(part, str) else part
                    for part in rv
                )
                response = CResponse(body, status=status or 200)
                if headers:
                    self._apply_headers(response, headers)
                return response
            except Exception:
                pass

        raise TypeError(
            "The view function return type is not supported:"
            f" it was a {type(rv).__name__}."
        )

    def _apply_headers(self, response, headers):
        """Apply headers from dict or list of tuples to a response."""
        if isinstance(headers, dict):
            for k, v in headers.items():
                response.headers.set(k, v)
        elif isinstance(headers, list):
            for k, v in headers:
                response.headers.set(k, v)

    def full_dispatch_request(self, environ):
        """Full request dispatch: before -> view -> after, with error handling."""
        if isinstance(environ, RequestContext):
            environ = environ.environ
        try:
            # Run before_first_request handlers
            if not self._got_first_request:
                self._got_first_request = True
                for func in getattr(self, '_before_first_request_funcs', []):
                    func()

            # Pre-match the URL to set request.endpoint and request.blueprint
            # before running before_request handlers (Flask does this at push time)
            self._match_request()

            # Run before_request handlers
            rv = None
            for func in self.before_request_funcs:
                rv = self._call_handler(func)
                if rv is not None:
                    break

            if rv is None:
                # Dispatch to view
                rv = self.dispatch_request(environ)

            response = self.make_response(rv)

        except Exception as exc:
            response = self.handle_exception(exc)

        try:
            # Wrap CResponse in Python wrapper for after_request handlers
            from cruet.wrappers import Response as PyResponse
            if isinstance(response, CResponse) and not isinstance(response, PyResponse):
                wrapped = PyResponse.__new__(PyResponse)
                object.__setattr__(wrapped, '_cresp', response)
                response = wrapped

            # Run per-request after_this_request callbacks (in reverse order)
            from cruet.ctx import _request_ctx_var
            try:
                ctx = _request_ctx_var.get()
                for func in reversed(ctx._after_request_funcs):
                    response = self._call_handler(func, response) or response
            except LookupError:
                pass

            # Run after_request handlers (in reverse order)
            for func in reversed(self.after_request_funcs):
                response = self._call_handler(func, response) or response
        except Exception as exc:
            return self.handle_exception(exc)

        return response

    def _match_request(self):
        """Pre-match the URL and set request attributes (endpoint, blueprint, view_args).

        Stores routing exceptions on the request context to be raised later
        in dispatch_request, allowing before_request handlers to run first.
        """
        from cruet.globals import request as request_proxy
        from cruet.ctx import _request_ctx_var
        from werkzeug.exceptions import NotFound as WerkzeugNotFound
        from werkzeug.exceptions import MethodNotAllowed as WerkzeugMethodNotAllowed
        from werkzeug.exceptions import BadRequest as WerkzeugBadRequest

        env = getattr(request_proxy, "environ", {}) or {}
        request_host = env.get("HTTP_HOST") or env.get("SERVER_NAME")
        if request_host and not self._is_valid_host(request_host):
            raise WerkzeugBadRequest()
        server_name = request_host or self.config.get("SERVER_NAME") or "localhost"
        script_name = env.get("SCRIPT_NAME", "")
        url_scheme = env.get("wsgi.url_scheme") or self.config.get("PREFERRED_URL_SCHEME") or "http"
        adapter = self._get_adapter(server_name=server_name, script_name=script_name, url_scheme=url_scheme, request_host=request_host)
        method = request_proxy.method
        path = request_proxy.path

        try:
            endpoint, values = adapter.match(path, method=method)
        except Exception as e:
            matched = False
            # For OPTIONS, try to match using an allowed method so we can
            # generate the automatic OPTIONS response.
            if method == "OPTIONS":
                allowed = None
                try:
                    allowed = getattr(e, "valid_methods", None)
                except Exception:
                    allowed = None
                if allowed is None:
                    try:
                        allowed = self._get_allowed_methods(path)
                    except Exception:
                        allowed = None
                if allowed:
                    try:
                        endpoint, values = adapter.match(path, method=allowed[0])
                        matched = True
                    except Exception:
                        matched = False
            if not matched:
                error_str = str(e)
                if "405" not in error_str:
                    alt_path = path + "/" if not path.endswith("/") else path.rstrip("/")
                    if alt_path != path:
                        try:
                            adapter.match(alt_path, method=method)
                            from werkzeug.routing import RequestRedirect
                            qs = request_proxy.query_string
                            env = getattr(request_proxy, "environ", {}) or {}
                            scheme = env.get("wsgi.url_scheme") or getattr(request_proxy, "scheme", "http")
                            host = env.get("HTTP_HOST") or getattr(request_proxy, "host", "localhost")
                            script_name = env.get("SCRIPT_NAME", "")
                            base = f"{scheme}://{host}{script_name}"
                            new_url = base.rstrip("/") + alt_path
                            if qs:
                                new_url += f"?{qs}"
                            raise RequestRedirect(new_url)
                        except LookupError:
                            pass
                # Store the routing exception to raise in dispatch_request
                try:
                    ctx = _request_ctx_var.get()
                    if "405" in error_str:
                        # Find allowed methods for this path
                        allowed = self._get_allowed_methods(path)
                        exc = WerkzeugMethodNotAllowed(allowed)
                        ctx._routing_exception = exc
                    else:
                        ctx._routing_exception = WerkzeugNotFound()
                except LookupError:
                    if "405" in error_str:
                        allowed = self._get_allowed_methods(path)
                        raise WerkzeugMethodNotAllowed(allowed)
                    raise WerkzeugNotFound()
                # Try to determine blueprint from URL prefix for scoped error handling
                for bp_name, bp in self.blueprints.items():
                    prefix = getattr(bp, 'url_prefix', None) or ''
                    if prefix and path.startswith(prefix):
                        request_proxy.blueprint = bp_name
                        break
                return

        # Merge route defaults
        ep_defaults = self._endpoint_defaults.get(endpoint)
        if ep_defaults:
            values = {**ep_defaults, **values}

        # Set request context attributes
        request_proxy.endpoint = endpoint
        request_proxy.view_args = values

        # Determine blueprint from endpoint
        if "." in endpoint:
            bp_name = endpoint.rsplit(".", 1)[0]
            if bp_name in self.blueprints:
                request_proxy.blueprint = bp_name
            else:
                request_proxy.blueprint = None
        else:
            request_proxy.blueprint = None

        # Run URL value preprocessors
        for func in self.url_value_preprocessors.get(None, []):
            self._call_handler(func, endpoint, values)
        if request_proxy.blueprint:
            for func in self.url_value_preprocessors.get(request_proxy.blueprint, []):
                self._call_handler(func, endpoint, values)

    def dispatch_request(self, environ):
        """Call the matched view function."""
        from cruet.globals import request as request_proxy
        from cruet.ctx import _request_ctx_var
        from werkzeug.exceptions import NotFound as WerkzeugNotFound

        # Check for stored routing exception
        try:
            ctx = _request_ctx_var.get()
            routing_exc = getattr(ctx, '_routing_exception', None)
            if routing_exc is not None:
                raise routing_exc
        except LookupError:
            pass

        endpoint = request_proxy.endpoint
        values = request_proxy.view_args

        # Automatic OPTIONS handling
        if request_proxy.method == "OPTIONS":
            no_auto = getattr(self, '_no_auto_options_endpoints', set())
            force_auto = getattr(self, '_force_auto_options_endpoints', set())
            if endpoint in no_auto:
                # No automatic OPTIONS — let it fall through to 405
                from werkzeug.exceptions import MethodNotAllowed as WerkzeugMethodNotAllowed
                allowed = self._get_allowed_methods(request_proxy.path)
                allowed = [m for m in allowed if m != "OPTIONS"]
                raise WerkzeugMethodNotAllowed(allowed)
            explicit_opts = getattr(self, '_explicit_options_endpoints', set())
            if endpoint in force_auto or endpoint not in explicit_opts:
                return self._make_options_response(endpoint)

        view_func = self.view_functions.get(endpoint)
        if view_func is None:
            raise WerkzeugNotFound()

        rv = self._call_handler(view_func, **values)
        return rv

    def _get_allowed_methods(self, path):
        """Get allowed methods for a path by checking all rules."""
        no_auto = getattr(self, '_no_auto_options_endpoints', set())
        methods = set()
        matched_endpoints = set()
        for rule in self.url_map._rules:
            try:
                result = rule.match(path)
                if result is not None and rule.methods:
                    methods.update(m.upper() for m in rule.methods)
                    matched_endpoints.add(rule.endpoint)
            except Exception:
                pass
        # If all matched endpoints have provide_automatic_options=False,
        # remove OPTIONS from the allowed set
        if matched_endpoints and matched_endpoints.issubset(no_auto):
            methods.discard("OPTIONS")
        return sorted(methods)

    def _make_options_response(self, endpoint):
        """Build an automatic OPTIONS response with allowed methods."""
        from cruet.globals import request as request_proxy
        path = request_proxy.path

        methods = set()
        for rule in self.url_map._rules:
            # Check all rules matching this path
            try:
                result = rule.match(path)
                if result is not None and rule.methods:
                    methods.update(m.upper() for m in rule.methods)
            except Exception:
                pass

        if not methods:
            # Fallback: just use the matched endpoint's methods
            for rule in self.url_map._rules:
                if rule.endpoint == endpoint:
                    if rule.methods:
                        methods.update(m.upper() for m in rule.methods)

        view_func = self.view_functions.get(endpoint)
        pao = getattr(view_func, "provide_automatic_options", None)
        if pao is True:
            explicit = getattr(self, "_explicit_methods_endpoints", {}).get(endpoint)
            if explicit is not None:
                methods = set(explicit)
            else:
                methods = set()
                for rule in self.url_map._rules:
                    if rule.endpoint == endpoint and rule.methods:
                        methods.update(m.upper() for m in rule.methods)
            methods.add("OPTIONS")
        else:
            # Always include OPTIONS and HEAD for GET endpoints
            if "GET" in methods:
                methods.add("HEAD")
            methods.add("OPTIONS")
        response = CResponse("", status=200)
        response.headers.set("Allow", ", ".join(sorted(methods)))
        return response

    def handle_exception(self, exc):
        """Handle an exception by looking for a registered error handler."""
        from werkzeug.exceptions import HTTPException as WerkzeugHTTPException
        from werkzeug.exceptions import InternalServerError

        try:
            from cruet.signals import got_request_exception
            got_request_exception.send(self, exception=exc)
        except Exception:
            pass

        # Store the exception on the request context for teardown handlers
        from cruet.ctx import _request_ctx_var
        try:
            ctx = _request_ctx_var.get()
            ctx._exc = exc
        except LookupError:
            pass

        # Handle RequestRedirect directly (don't run error handlers)
        try:
            from werkzeug.routing import RequestRedirect
            if isinstance(exc, RequestRedirect):
                response = CResponse("", status=exc.code)
                response.headers.set("Location", exc.new_url)
                return response
        except ImportError:
            pass

        # TRAP_HTTP_EXCEPTIONS: re-raise HTTP exceptions
        if self.config.get("TRAP_HTTP_EXCEPTIONS"):
            if isinstance(exc, WerkzeugHTTPException):
                raise

        # TRAP_BAD_REQUEST_ERRORS
        if self.config.get("TRAP_BAD_REQUEST_ERRORS"):
            from werkzeug.exceptions import BadRequest as WerkzeugBadRequest
            if isinstance(exc, WerkzeugBadRequest):
                if hasattr(exc, 'show_exception'):
                    exc.show_exception = True
                raise

        # Debug mode + BadRequest with __cause__ (e.g., KeyError wrapped)
        if self.config.get("DEBUG") and self.config.get("TRAP_BAD_REQUEST_ERRORS") is None:
            from werkzeug.exceptions import BadRequest as WerkzeugBadRequest
            from werkzeug.exceptions import BadRequestKeyError
            if isinstance(exc, BadRequestKeyError) or (
                isinstance(exc, WerkzeugBadRequest) and exc.__cause__ is not None
            ):
                if hasattr(exc, 'show_exception'):
                    exc.show_exception = True
                raise

        # Wrap non-HTTP exceptions in InternalServerError
        if not isinstance(exc, WerkzeugHTTPException):
            # First try to find a handler for the original exception class
            handler, code = self._find_error_handler(exc)
            if handler is not None:
                try:
                    rv = self._call_handler(handler, exc)
                    response = self.make_response(rv)
                    self._clear_exc_on_ctx()
                    return response
                except Exception:
                    exc = sys.exc_info()[1] or exc

            # Try handlers for InternalServerError/500
            wrapped = InternalServerError()
            wrapped.original_exception = exc
            handler, code = self._find_error_handler(wrapped)
            if handler is not None:
                try:
                    rv = self._call_handler(handler, wrapped)
                    response = self.make_response(rv)
                    self._clear_exc_on_ctx()
                    return response
                except Exception:
                    exc = sys.exc_info()[1] or exc
            # No handler — propagate if needed
            if self._should_propagate(exc):
                raise exc
            self.log_exception(exc)
            # Default 500 response using the wrapped exception
            response = CResponse(wrapped.get_body(), status=500,
                                 content_type="text/html; charset=utf-8")
            return response

        # Try to find an error handler for HTTP exceptions
        handler, code = self._find_error_handler(exc)

        if handler is not None:
            try:
                rv = self._call_handler(handler, exc)
                response = self.make_response(rv)
                self._clear_exc_on_ctx()
                return response
            except Exception:
                # Handler itself raised - fall through
                exc = sys.exc_info()[1] or exc

        # If the HTTPException wraps a response, return it directly.
        if getattr(exc, "response", None) is not None:
            resp = exc.response
            if isinstance(resp, CResponse):
                return resp
            try:
                body = resp.get_data()
                content_type = resp.content_type
                status = resp.status_code
                response = CResponse(body, status=status, content_type=content_type)
                for key, value in resp.headers.items():
                    if key.lower() != "content-type":
                        response.headers.set(key, value)
                return response
            except Exception:
                pass

        # No handler found - propagate in testing/debug if not HTTP exception
        if not isinstance(exc, WerkzeugHTTPException):
            if self._should_propagate(exc):
                raise

        # Default error response
        if isinstance(exc, WerkzeugHTTPException):
            code = exc.code
        elif isinstance(exc, NotFound):
            code = 404
        elif isinstance(exc, MethodNotAllowed):
            code = 405
        else:
            code = 500

        if isinstance(exc, WerkzeugHTTPException):
            response = CResponse(exc.get_body(), status=exc.code,
                                 content_type="text/html; charset=utf-8")
            # Copy headers from werkzeug exception (e.g. Allow for 405)
            try:
                for key, value in exc.get_headers({}):
                    if key.lower() != 'content-type':
                        response.headers.set(key, value)
            except Exception:
                pass
            return response

        status_messages = {
            400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
            404: "Not Found", 405: "Method Not Allowed", 408: "Request Timeout",
            409: "Conflict", 410: "Gone", 418: "I'm a Teapot",
            422: "Unprocessable Entity", 429: "Too Many Requests",
            500: "Internal Server Error", 502: "Bad Gateway",
            503: "Service Unavailable",
        }
        msg = status_messages.get(code, f"Error {code}")
        return CResponse(msg, status=code, content_type="text/plain")

    def _find_error_handler(self, exc):
        """Find a registered error handler for the exception. Returns (handler, code) or (None, None)."""
        from werkzeug.exceptions import HTTPException as WerkzeugHTTPException
        try:
            from werkzeug.routing import RequestRedirect
            if isinstance(exc, RequestRedirect):
                return None, None
        except Exception:
            pass

        # Determine the current blueprint
        bp_name = None
        try:
            from cruet.globals import request as req_proxy
            bp_name = getattr(req_proxy, 'blueprint', None)
        except (RuntimeError, LookupError):
            pass

        # Get status code
        if isinstance(exc, WerkzeugHTTPException):
            code = exc.code
        elif isinstance(exc, NotFound):
            code = 404
        elif isinstance(exc, MethodNotAllowed):
            code = 405
        else:
            code = 500

        # Search in order: blueprint handlers (walking up hierarchy), then app handlers
        search_keys = []
        if bp_name:
            parts = bp_name.split(".")
            for i in range(len(parts), 0, -1):
                search_keys.append(".".join(parts[:i]))
        search_keys.append(None)

        is_http = isinstance(exc, WerkzeugHTTPException)

        for key in search_keys:
            handlers = self.error_handlers.get(key, {})
            if not isinstance(handlers, dict):
                # Backwards compat: if error_handlers has old-style flat entries, skip
                continue

            # Walk MRO for class-based handlers
            for cls in type(exc).__mro__:
                handler = handlers.get(cls)
                if handler:
                    return handler, code

            # Only do code-based lookup for HTTP exceptions
            if is_http:
                # Try code-based handler
                handler = handlers.get(code)
                if handler:
                    return handler, code

                # Try werkzeug exception class for this code
                try:
                    from werkzeug.exceptions import default_exceptions
                    exc_class = default_exceptions.get(code)
                    if exc_class is not None:
                        handler = handlers.get(exc_class)
                        if handler:
                            return handler, code
                except ImportError:
                    pass

        return None, None

    def _process_response(self, response):
        """Run after_request handlers on a response."""
        from cruet.ctx import _request_ctx_var
        try:
            ctx = _request_ctx_var.get()
            for func in reversed(ctx._after_request_funcs):
                response = func(response) or response
        except LookupError:
            pass
        for func in reversed(self.after_request_funcs):
            response = func(response) or response
        return response

    def _clear_exc_on_ctx(self):
        """Clear the stored exception on the request context.

        Called when an exception is successfully handled by an error handler,
        so that teardown functions see None instead of the original exception.
        """
        from cruet.ctx import _request_ctx_var
        try:
            ctx = _request_ctx_var.get()
            ctx._exc = None
        except LookupError:
            pass

    def log_exception(self, exc):
        try:
            from cruet.globals import request as request_proxy
            self.logger.error(
                "Exception on %s [%s]",
                getattr(request_proxy, "path", "?"),
                getattr(request_proxy, "method", "?"),
                exc_info=exc,
            )
        except Exception:
            pass

    def _should_propagate(self, exc):
        """Check if exceptions should be propagated."""
        if self.testing:
            return True
        prop = self.config.get("PROPAGATE_EXCEPTIONS")
        if prop is not None:
            return prop
        if self.debug:
            return True
        return False

    def _is_trusted_host(self, host, trusted_list):
        if not host:
            return False
        host = host.split(":", 1)[0].lower()
        for pattern in trusted_list:
            if not pattern:
                continue
            pat = pattern.lower()
            if pat.startswith("."):
                suffix = pat[1:]
                if host == suffix or host.endswith(pat):
                    return True
            elif host == pat:
                return True
        return False

    def _is_valid_host(self, host):
        if not host:
            return True
        host = host.strip()
        if not host:
            return False
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
            try:
                import ipaddress
                ipaddress.ip_address(host)
                return True
            except Exception:
                return False
        host = host.split(":", 1)[0]
        for ch in host:
            o = ord(ch)
            if o < 32 or o == 127:
                return False
        try:
            host.encode("idna")
        except Exception:
            return False
        return True

    def wsgi_app(self, environ, start_response):
        """The actual WSGI application."""
        from cruet.sessions import save_session, NullSession

        ctx = RequestContext(self, environ)
        pushed = False
        try:
            ctx.push()
            pushed = True
        except Exception as exc:
            if self._should_propagate(exc):
                raise
            response = CResponse("Internal Server Error", status=500,
                                 content_type="text/plain")
            return response(environ, start_response)
        try:
            environ.setdefault("werkzeug.request", ctx.request)
        except Exception:
            pass

        error = None
        try:
            try:
                from cruet.signals import request_started
                request_started.send(self)
            except Exception:
                pass
            trusted = self.config.get("TRUSTED_HOSTS")
            if trusted:
                from cruet.globals import request as request_proxy
                if not self._is_trusted_host(getattr(request_proxy, "host", ""), trusted):
                    response = CResponse(
                        "Bad Request",
                        status=400,
                        content_type="text/html; charset=utf-8",
                    )
                    return response(environ, start_response)
            response = self.full_dispatch_request(environ)
            # Check if an exception was handled (stored on context)
            error = getattr(ctx, '_exc', None)
            # Save session onto response
            if ctx.session is None:
                ctx.session = NullSession()
            save_session(self, ctx.session, response)
            # For HEAD requests, return a wrapper that yields no body
            if environ.get("REQUEST_METHOD") == "HEAD":
                original_call = response.__call__
                def head_call(env, sr):
                    result = original_call(env, sr)
                    return [b""]
                return head_call(environ, start_response)
            try:
                from cruet.signals import request_finished
                request_finished.send(self, response=response)
            except Exception:
                pass
            return response(environ, start_response)
        except Exception as exc:
            error = exc
            try:
                from cruet.signals import got_request_exception
                got_request_exception.send(self, exception=exc)
            except Exception:
                pass
            if self._should_propagate(exc):
                ctx.pop(exc)
                raise
            tb = traceback.format_exc()
            response = CResponse("Internal Server Error", status=500,
                                 content_type="text/plain")
            return response(environ, start_response)
        finally:
            if pushed:
                if environ.get("cruet.preserve_context"):
                    environ["cruet.preserved_ctx"] = ctx
                else:
                    ctx.pop(error)

    def __call__(self, environ, start_response):
        """WSGI interface."""
        return self.wsgi_app(environ, start_response)

    def test_client(self, use_cookies=True, **kwargs):
        """Return a test client for this app."""
        from cruet.testing import FlaskClient
        return FlaskClient(self, use_cookies=use_cookies)

    def test_cli_runner(self, **kwargs):
        """Return a CLI runner for testing CLI commands."""
        runner_cls = getattr(self, "test_cli_runner_class", None)
        if runner_cls is None:
            from cruet.testing import FlaskCliRunner
            runner_cls = FlaskCliRunner
        return runner_cls(self, **kwargs)

    def app_context(self):
        """Create an application context."""
        return AppContext(self)

    def test_request_context(self, path="/", method="GET", **kwargs):
        """Create a request context for testing."""
        subdomain = kwargs.pop("subdomain", None)
        if "base_url" not in kwargs:
            server_name = self.config.get("SERVER_NAME") or "localhost"
            scheme = kwargs.get("url_scheme") or self.config.get("PREFERRED_URL_SCHEME") or "http"
            script_root = self.config.get("APPLICATION_ROOT") or ""
            if subdomain and server_name:
                kwargs["base_url"] = f"{scheme}://{subdomain}.{server_name}{script_root}"
            else:
                kwargs["base_url"] = f"{scheme}://{server_name}{script_root}"
        environ = _make_test_environ(path, method, **kwargs)
        return RequestContext(self, environ, match_request=True)

    def request_context(self, environ):
        """Create a request context from a WSGI environ dict or builder."""
        if hasattr(environ, "get_environ"):
            environ = environ.get_environ()
        return RequestContext(self, environ)

    def run(self, host=None, port=None, debug=None, **kwargs):
        """Run the development server."""
        if debug is not None:
            self.debug = debug
        # Ensure template auto-reload is updated for debug.
        if self._jinja_env is not None:
            auto_reload = self.config.get("TEMPLATES_AUTO_RELOAD")
            if auto_reload is not None:
                self._jinja_env.auto_reload = auto_reload
            else:
                self._jinja_env.auto_reload = self.debug
        if host is None:
            server_name = self.config.get("SERVER_NAME")
            if server_name:
                host = server_name.split(":", 1)[0]
            else:
                host = "127.0.0.1"
        if port is None:
            server_name = self.config.get("SERVER_NAME")
            if server_name and ":" in server_name:
                try:
                    port = int(server_name.rsplit(":", 1)[1])
                except Exception:
                    port = 8000
            else:
                port = 8000
        if os.environ.get("FLASK_RUN_FROM_CLI") == "true":
            return
        try:
            import werkzeug.serving as wz_serving
        except Exception:
            wz_serving = None
        if wz_serving is not None:
            return wz_serving.run_simple(host, port, self, **kwargs)
        from cruet.serving import run
        run(self, host=host, port=port, **kwargs)


try:
    from werkzeug.exceptions import NotFound, MethodNotAllowed
except ImportError:
    class NotFound(Exception):
        """404 Not Found."""
        code = 404

    class MethodNotAllowed(Exception):
        """405 Method Not Allowed."""
        code = 405


def _make_test_environ(path="/", method="GET", query_string="", body=b"",
                       content_type="", headers=None, host="localhost",
                       port=80, scheme="http", data=None,
                       environ_overrides=None, environ_base=None,
                       base_url=None, errors_stream=None, url_scheme=None):
    """Build a WSGI environ dict for testing."""
    if url_scheme:
        scheme = url_scheme
    # Parse base_url if provided
    if base_url:
        from urllib.parse import urlsplit
        parsed = urlsplit(base_url)
        scheme = parsed.scheme or scheme
        if parsed.hostname:
            host = parsed.hostname
        if parsed.port:
            port = parsed.port
        # base_url path acts as SCRIPT_NAME prefix
        script_name = (parsed.path or "").rstrip("/")
    else:
        script_name = ""

    if "?" in path:
        if query_string:
            raise ValueError(
                "Cannot provide query_string both in the path and as a keyword argument."
            )
        from urllib.parse import urlsplit
        split = urlsplit(path)
        path = split.path
        query_string = split.query
    if data is not None:
        body = data if isinstance(data, bytes) else data.encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "SERVER_NAME": host,
        "SERVER_PORT": str(port),
        "HTTP_HOST": f"{host}:{port}" if port != 80 else host,
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": scheme,
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "SCRIPT_NAME": script_name,
        "REMOTE_ADDR": "127.0.0.1",
    }
    if content_type:
        environ["CONTENT_TYPE"] = content_type
    if errors_stream is not None:
        environ["wsgi.errors"] = errors_stream
    if body:
        environ["CONTENT_LENGTH"] = str(len(body))
    # Apply environ_base (defaults from test client)
    if environ_base:
        environ.update(environ_base)
    if headers:
        if isinstance(headers, dict):
            header_items = headers.items()
        else:
            header_items = headers
        for key, value in header_items:
            key_upper = key.upper().replace("-", "_")
            if key_upper == "CONTENT_TYPE":
                environ["CONTENT_TYPE"] = value
            elif key_upper == "CONTENT_LENGTH":
                environ["CONTENT_LENGTH"] = value
            else:
                environ[f"HTTP_{key_upper}"] = value
    if environ_overrides:
        environ.update(environ_overrides)
    return environ


class TestClient:
    """Simple test client that simulates requests against the app."""

    def __init__(self, app, use_cookies=True):
        self.app = app
        self._cookies = {} if use_cookies else None
        self._use_cookies = use_cookies
        self.environ_base = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_USER_AGENT": f"Werkzeug/{importlib.metadata.version('werkzeug')}",
        }
        self._preserve_context = False
        self._context_stack = []
        self.allow_subdomain_redirects = False

    def _request(self, method, path, **kwargs):
        # Handle json kwarg → data + content_type
        if "json" in kwargs:
            import json as _json
            kwargs["data"] = _json.dumps(kwargs.pop("json")).encode()
            kwargs.setdefault("content_type", "application/json")

        # Handle data dict → form-encoded body
        if isinstance(kwargs.get("data"), dict):
            from urllib.parse import urlencode
            kwargs["data"] = urlencode(kwargs["data"]).encode()
            kwargs.setdefault("content_type", "application/x-www-form-urlencoded")

        follow_redirects = kwargs.pop("follow_redirects", False)
        base_url = kwargs.pop("base_url", None)
        url_scheme = kwargs.pop("url_scheme", None)
        subdomain = kwargs.pop("subdomain", None)
        original_data = kwargs.get("data")
        original_content_type = kwargs.get("content_type")

        # Inject stored cookies into the environ
        if self._use_cookies and self._cookies:
            cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            headers = kwargs.get("headers") or {}
            if isinstance(headers, dict):
                headers = dict(headers)
            else:
                headers = dict(headers)
            headers.setdefault("Cookie", cookie_header)
            kwargs["headers"] = headers

        # Merge environ_base
        kwargs.setdefault("environ_base", self.environ_base)

        # Handle full URL path
        if "://" in path:
            from urllib.parse import urlsplit
            parsed = urlsplit(path)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"

        # Handle subdomain with SERVER_NAME
        if subdomain:
            server_name = self.app.config.get("SERVER_NAME")
            if server_name:
                scheme = url_scheme or self.app.config.get("PREFERRED_URL_SCHEME") or "http"
                script_root = self.app.config.get("APPLICATION_ROOT") or ""
                base_url = f"{scheme}://{subdomain}.{server_name}{script_root}"

        if base_url is None:
            server_name = self.app.config.get("SERVER_NAME")
            if server_name:
                scheme = url_scheme or self.app.config.get("PREFERRED_URL_SCHEME") or "http"
                script_root = self.app.config.get("APPLICATION_ROOT") or ""
                base_url = f"{scheme}://{server_name}{script_root}"

        if base_url:
            kwargs["base_url"] = base_url
        if url_scheme:
            kwargs["scheme"] = url_scheme

        # Warn when subdomain matching is enabled but host doesn't match SERVER_NAME
        if self.app.subdomain_matching:
            try:
                import warnings
                from urllib.parse import urlsplit
                server_name = self.app.config.get("SERVER_NAME")
                if server_name:
                    host = None
                    if base_url:
                        host = urlsplit(base_url).netloc
                    elif "://" in path:
                        host = urlsplit(path).netloc
                    if host:
                        server_no_port = server_name.split(":", 1)[0]
                        host_no_port = host.split(":", 1)[0]
                        if not (host_no_port == server_no_port or host_no_port.endswith("." + server_no_port)):
                            warnings.warn(
                                f"Current server name '{host}' doesn't match configured server name '{server_name}'",
                                RuntimeWarning,
                            )
            except Exception:
                pass

        environ = _make_test_environ(path, method, **kwargs)
        if self._preserve_context:
            environ["cruet.preserve_context"] = True

        response = self._run_wsgi(environ)

        # Follow redirects
        if follow_redirects:
            max_redirects = 20
            for _ in range(max_redirects):
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                location = response.headers.get("Location")
                if not location:
                    break
                if self._preserve_context:
                    self._pop_contexts()
                if response.status_code in (301, 302) and method not in ("GET", "HEAD"):
                    raise AssertionError(f"canonical URL '{location}'")
                # For 307/308 preserve method, otherwise GET
                if response.status_code in (307, 308):
                    redirect_method = method
                else:
                    redirect_method = "GET"
                # Parse location for redirect
                from urllib.parse import urlsplit
                parsed = urlsplit(location)
                redirect_path = parsed.path or "/"
                if parsed.query:
                    redirect_path = f"{redirect_path}?{parsed.query}"
                redirect_kwargs = {"environ_base": self.environ_base}
                if redirect_method == method and original_data is not None:
                    redirect_kwargs["data"] = original_data
                    if original_content_type:
                        redirect_kwargs["content_type"] = original_content_type
                # Inject cookies for redirect
                if self._use_cookies and self._cookies:
                    cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
                    redirect_kwargs["headers"] = {"Cookie": cookie_header}
                redirect_environ = _make_test_environ(redirect_path, redirect_method, **redirect_kwargs)
                if self._preserve_context:
                    redirect_environ["cruet.preserve_context"] = True
                response = self._run_wsgi(redirect_environ)

        return response

    def _run_wsgi(self, environ):
        """Run the WSGI app and return a TestResponse."""
        status_holder = {}
        headers_holder = {}

        def start_response(status, headers):
            status_holder["status"] = status
            headers_holder["headers"] = headers

        body_parts = self.app(environ, start_response)

        body = b"".join(body_parts)

        # Parse status code
        status_str = status_holder.get("status", "500 Internal Server Error")
        status_code = int(status_str.split(" ", 1)[0])

        response = TestResponse(body, status_code, headers_holder.get("headers", []))
        preserved = environ.get("cruet.preserved_ctx")
        if preserved is not None:
            self._context_stack.append(preserved)
            response._client = self

        # Store cookies from Set-Cookie headers
        if self._use_cookies:
            for key, value in headers_holder.get("headers", []):
                if key.lower() == "set-cookie":
                    self._parse_set_cookie(value)

        return response

    def __enter__(self):
        self._preserve_context = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._preserve_context = False
        self._pop_contexts()
        return False

    def _pop_contexts(self):
        while self._context_stack:
            ctx = self._context_stack.pop()
            try:
                ctx.pop()
            except Exception:
                pass

    def open(self, *args, **kwargs):
        if args:
            obj = args[0]
            if hasattr(obj, "get_environ"):
                environ = obj.get_environ()
                environ.update(self.environ_base)
                if self._preserve_context:
                    environ["cruet.preserve_context"] = True
                return self._run_wsgi(environ)
            if isinstance(obj, dict):
                environ = dict(obj)
                environ.update(self.environ_base)
                if self._preserve_context:
                    environ["cruet.preserve_context"] = True
                return self._run_wsgi(environ)
            if isinstance(obj, str):
                if len(args) >= 2 and "method" not in kwargs:
                    kwargs["method"] = args[1]
                return self._request(kwargs.pop("method", "GET"), obj, **kwargs)
        path = kwargs.pop("path", "/")
        method = kwargs.pop("method", "GET")
        return self._request(method, path, **kwargs)

    def session_transaction(self):
        from contextlib import contextmanager
        from cruet.sessions import open_session, save_session, NullSession
        from cruet.wrappers import Response

        if not self._use_cookies:
            raise TypeError("Cookies are disabled.")

        @contextmanager
        def _ctx():
            try:
                from cruet.ctx import _request_ctx_var
                current_ctx = _request_ctx_var.get()
            except LookupError:
                current_ctx = None
            if current_ctx is not None:
                sess = current_ctx.session
                if isinstance(sess, NullSession):
                    raise RuntimeError("Session backend did not open a session.")
                yield sess
                return

            if self._context_stack:
                ctx = self._context_stack[-1]
                sess = ctx.session
                if isinstance(sess, NullSession):
                    raise RuntimeError("Session backend did not open a session.")
                yield sess
                resp = Response("")
                save_session(self.app, sess, resp)
                self._store_cookies_from_response(resp)
                return

            environ = _make_test_environ("/", "GET", environ_base=self.environ_base)
            if self._use_cookies and self._cookies:
                cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
                environ["HTTP_COOKIE"] = cookie_header
            ctx = RequestContext(self.app, environ)
            ctx.push()
            sess = open_session(self.app, ctx.request)
            if isinstance(sess, NullSession):
                ctx.pop()
                raise RuntimeError("Session backend did not open a session.")
            ctx.session = sess
            try:
                yield sess
                resp = Response("")
                save_session(self.app, sess, resp)
                self._store_cookies_from_response(resp)
            finally:
                ctx.pop()

        return _ctx()

    def _store_cookies_from_response(self, response):
        if not self._use_cookies:
            return
        if hasattr(response.headers, "items"):
            header_items = response.headers.items()
        else:
            header_items = list(response.headers)
        for key, value in header_items:
            if key.lower() == "set-cookie":
                self._parse_set_cookie(value)

    def _parse_set_cookie(self, header_value):
        """Parse a Set-Cookie header and store the cookie."""
        parts = header_value.split(";")
        if parts:
            name_value = parts[0].strip()
            if "=" in name_value:
                name, value = name_value.split("=", 1)
                self._cookies[name.strip()] = value.strip()

    def get(self, *args, **kwargs):
        return self._method_shortcut("GET", args, kwargs)

    def post(self, *args, **kwargs):
        return self._method_shortcut("POST", args, kwargs)

    def put(self, *args, **kwargs):
        return self._method_shortcut("PUT", args, kwargs)

    def delete(self, *args, **kwargs):
        return self._method_shortcut("DELETE", args, kwargs)

    def head(self, *args, **kwargs):
        return self._method_shortcut("HEAD", args, kwargs)

    def options(self, *args, **kwargs):
        return self._method_shortcut("OPTIONS", args, kwargs)

    def patch(self, *args, **kwargs):
        return self._method_shortcut("PATCH", args, kwargs)

    def trace(self, *args, **kwargs):
        return self._method_shortcut("TRACE", args, kwargs)

    def _method_shortcut(self, method, args, kwargs):
        if len(args) >= 2:
            kwargs['base_url'] = args[1]
            args = (args[0],)
        path = args[0] if args else "/"
        return self._request(method, path, **kwargs)


class TestHeaders:
    """Python wrapper around CHeaders that adds missing dict-like methods."""

    def __init__(self, cheaders):
        self._cheaders = cheaders

    def get(self, key, default=None):
        return self._cheaders.get(key, default)

    def set(self, key, value):
        return self._cheaders.set(key, value)

    def getlist(self, key):
        return self._cheaders.getlist(key)

    def get_all(self, key):
        return self._cheaders.getlist(key)

    def items(self):
        return list(self)

    def keys(self):
        return [k for k, v in self]

    def values(self):
        return [v for k, v in self]

    def __iter__(self):
        return iter(self._cheaders)

    def __getitem__(self, key):
        val = self._cheaders.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key, value):
        self._cheaders.set(key, value)

    def __contains__(self, key):
        return self._cheaders.get(key) is not None

    def __len__(self):
        return len(list(self._cheaders))

    def __repr__(self):
        return repr(list(self._cheaders))


class _HeaderSet:
    """Set-like wrapper around a specific response header."""

    def __init__(self, headers, header_name):
        self._headers = headers
        self._header = header_name

    def _get_items(self):
        current = self._headers.get(self._header, "")
        if not current:
            return set()
        return {v.strip() for v in current.split(",") if v.strip()}

    def add(self, value):
        items = self._get_items()
        items.add(value)
        self._headers.set(self._header, ", ".join(sorted(items)))

    def update(self, values):
        items = self._get_items()
        items.update(values)
        self._headers.set(self._header, ", ".join(sorted(items)))

    def discard(self, value):
        items = self._get_items()
        items.discard(value)
        if items:
            self._headers.set(self._header, ", ".join(sorted(items)))

    def __contains__(self, value):
        return value in self._get_items()

    def __iter__(self):
        return iter(self._get_items())

    def __len__(self):
        return len(self._get_items())


class TestResponse:
    """Response object returned by the test client."""

    def __init__(self, data, status_code, headers):
        self.data = data
        self.status_code = status_code
        self._headers = headers
        from cruet._cruet import CHeaders
        self.headers = TestHeaders(CHeaders(headers))

    @property
    def content_type(self):
        return self.headers.get("Content-Type", "")

    @property
    def mimetype(self):
        ct = self.content_type
        if ";" in ct:
            return ct.split(";", 1)[0].strip()
        return ct

    @property
    def status(self):
        _status_messages = {
            200: "OK", 201: "CREATED", 204: "NO CONTENT",
            301: "MOVED PERMANENTLY", 302: "FOUND", 304: "NOT MODIFIED",
            400: "BAD REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
            404: "NOT FOUND", 405: "METHOD NOT ALLOWED",
            500: "INTERNAL SERVER ERROR",
        }
        phrase = _status_messages.get(self.status_code, "UNKNOWN")
        return f"{self.status_code} {phrase}"

    @property
    def text(self):
        return self.data.decode("utf-8", errors="replace")

    @property
    def json(self):
        import json
        return json.loads(self.data)

    @property
    def is_json(self):
        ct = self.content_type
        if not ct:
            return False
        mt = ct.split(";", 1)[0].strip()
        return mt == "application/json" or (mt.startswith("application/") and mt.endswith("+json"))

    def get_json(self, force=False, silent=False):
        try:
            import json as _json
            return _json.loads(self.data)
        except Exception:
            if silent:
                return None
            raise

    def get_data(self, as_text=False):
        if as_text:
            return self.data.decode("utf-8", errors="replace")
        return self.data

    def close(self):
        client = getattr(self, "_client", None)
        if client is not None:
            client._pop_contexts()

    @property
    def allow(self):
        allow_header = self.headers.get("Allow", "")
        if not allow_header:
            return set()
        return {m.strip() for m in allow_header.split(",")}

    @property
    def content_length(self):
        val = self.headers.get("Content-Length")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def location(self):
        return self.headers.get("Location")

    @property
    def vary(self):
        return _HeaderSet(self.headers, "Vary")

    def close(self):
        pass

    def get_header(self, name):
        return self.headers.get(name)
