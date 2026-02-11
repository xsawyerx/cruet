"""Blueprint system for modular application organization."""
import os
import warnings

from cruet.cli import AppGroup

_sentinel = object()


def _merge_blueprint_prefix(prefix, rule):
    """Merge a blueprint URL prefix and a route rule, normalizing slashes."""
    if not prefix or prefix == "/":
        return rule or "/"
    if rule is None or rule == "":
        return prefix
    # rule == "/" means "the root of this prefix" → keep trailing slash
    merged = prefix.rstrip("/") + "/" + rule.lstrip("/")
    while "//" in merged:
        merged = merged.replace("//", "/")
    return merged or "/"


def _merge_subdomain(child, parent):
    if child and parent:
        return f"{child}.{parent}"
    if child:
        return child
    return parent


class Blueprint:
    """A blueprint for organizing routes and handlers."""

    def __init__(self, name, import_name, url_prefix=None,
                 template_folder=None, static_folder=None,
                 static_url_path=None, subdomain=None,
                 url_defaults=None, root_path=None, cli_group=_sentinel):
        if "." in name:
            raise ValueError("'name' may not contain a dot '.' character.")
        if not name:
            raise ValueError("'name' may not be empty.")
        self.name = name
        self.import_name = import_name
        self.url_prefix = url_prefix
        self.template_folder = template_folder
        self.static_folder = static_folder
        if static_folder is not None and static_url_path is None:
            static_url_path = "/static"
        self.static_url_path = static_url_path
        self.subdomain = subdomain
        self.url_defaults_mapping = url_defaults or {}
        self._deferred_actions = []
        self.before_request_funcs = []
        self.after_request_funcs = []
        self.teardown_request_funcs = []
        self.error_handlers = {}
        self.template_context_processors = []
        self._blueprints = []  # child blueprints
        self._registered_names = set()
        self.cli_group = cli_group
        self.cli = AppGroup()
        self.cli.name = self.name

        if root_path is not None:
            self.root_path = root_path
        elif import_name:
            import sys
            mod = sys.modules.get(import_name)
            if mod and hasattr(mod, "__file__") and mod.__file__:
                self.root_path = os.path.dirname(os.path.abspath(mod.__file__))
            else:
                self.root_path = os.getcwd()
        else:
            self.root_path = os.getcwd()

    def route(self, rule_str, **options):
        """Decorator to register a view function on this blueprint."""
        def decorator(f):
            endpoint = options.pop("endpoint", f.__name__)
            methods = options.pop("methods", None)
            strict_slashes = options.pop("strict_slashes", True)
            defaults = options.pop("defaults", None)
            self.add_url_rule(rule_str, endpoint, f, methods=methods,
                              strict_slashes=strict_slashes, defaults=defaults)
            return f
        return decorator

    def add_url_rule(self, rule_str, endpoint=None, view_func=None,
                     methods=None, strict_slashes=True, defaults=None,
                     subdomain=None):
        """Add a URL rule to this blueprint."""
        if endpoint is None and view_func is not None:
            endpoint = view_func.__name__

        if endpoint and "." in endpoint:
            raise ValueError(
                f"The endpoint name {endpoint!r} should not contain a dot."
            )

        def deferred_action(app, bp_prefix, bp_name, bp_url_defaults=None, bp_subdomain=None):
            full_endpoint = f"{bp_name}.{endpoint}"
            full_rule = _merge_blueprint_prefix(bp_prefix, rule_str)
            merged_defaults = dict(bp_url_defaults or {})
            if defaults:
                merged_defaults.update(defaults)
            effective_subdomain = subdomain if subdomain is not None else self.subdomain
            effective_subdomain = _merge_subdomain(effective_subdomain, bp_subdomain)
            app.add_url_rule(full_rule, full_endpoint, view_func,
                             methods=methods, strict_slashes=strict_slashes,
                             defaults=merged_defaults or None,
                             subdomain=effective_subdomain)

        self._deferred_actions.append(deferred_action)

    def get(self, rule_str, **options):
        options["methods"] = ["GET"]
        return self.route(rule_str, **options)

    def post(self, rule_str, **options):
        options["methods"] = ["POST"]
        return self.route(rule_str, **options)

    def put(self, rule_str, **options):
        options["methods"] = ["PUT"]
        return self.route(rule_str, **options)

    def delete(self, rule_str, **options):
        options["methods"] = ["DELETE"]
        return self.route(rule_str, **options)

    def patch(self, rule_str, **options):
        options["methods"] = ["PATCH"]
        return self.route(rule_str, **options)

    def before_request(self, f):
        """Register a before_request handler scoped to this blueprint."""
        self.before_request_funcs.append(f)
        return f

    def after_request(self, f):
        """Register an after_request handler scoped to this blueprint."""
        self.after_request_funcs.append(f)
        return f

    def teardown_request(self, f):
        """Register a teardown handler scoped to this blueprint."""
        self.teardown_request_funcs.append(f)
        return f

    def errorhandler(self, code_or_exception):
        """Register an error handler scoped to this blueprint."""
        def decorator(f):
            self.error_handlers[code_or_exception] = f
            return f
        return decorator

    def context_processor(self, f):
        """Register a template context processor for this blueprint."""
        self.template_context_processors.append(f)
        return f

    def app_context_processor(self, f):
        """Register a template context processor on the entire app."""
        def deferred_action(app, bp_prefix, bp_name):
            app.template_context_processors.append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def before_app_request(self, f):
        """Register a before_request handler on the entire app."""
        def deferred_action(app, bp_prefix, bp_name):
            app.before_request_funcs.append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def after_app_request(self, f):
        """Register an after_request handler on the entire app."""
        def deferred_action(app, bp_prefix, bp_name):
            app.after_request_funcs.append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def teardown_app_request(self, f):
        """Register a teardown handler on the entire app."""
        def deferred_action(app, bp_prefix, bp_name, bp_url_defaults=None):
            app.teardown_request_funcs.append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def app_errorhandler(self, code_or_exception):
        """Register an error handler on the entire app."""
        def decorator(f):
            def deferred_action(app, bp_prefix, bp_name):
                app._register_error_handler(None, code_or_exception, f)
            self._deferred_actions.append(deferred_action)
            return f
        return decorator

    def app_template_filter(self, name=None):
        """Register a template filter on the app via blueprint."""
        def decorator(f):
            def deferred_action(app, bp_prefix, bp_name):
                app.add_template_filter(f, name)
            self._deferred_actions.append(deferred_action)
            return f
        if callable(name):
            func = name
            name = None
            return decorator(func)
        return decorator

    def add_app_template_filter(self, f, name=None):
        """Non-decorator version of app_template_filter."""
        def deferred_action(app, bp_prefix, bp_name):
            app.add_template_filter(f, name)
        self._deferred_actions.append(deferred_action)

    def app_template_test(self, name=None):
        """Register a template test on the app via blueprint."""
        def decorator(f):
            def deferred_action(app, bp_prefix, bp_name):
                app.add_template_test(f, name)
            self._deferred_actions.append(deferred_action)
            return f
        if callable(name):
            func = name
            name = None
            return decorator(func)
        return decorator

    def add_app_template_test(self, f, name=None):
        """Non-decorator version of app_template_test."""
        def deferred_action(app, bp_prefix, bp_name):
            app.add_template_test(f, name)
        self._deferred_actions.append(deferred_action)

    def app_template_global(self, name=None):
        """Register a template global on the app via blueprint."""
        def decorator(f):
            def deferred_action(app, bp_prefix, bp_name):
                app.add_template_global(f, name)
            self._deferred_actions.append(deferred_action)
            return f
        if callable(name):
            func = name
            name = None
            return decorator(func)
        return decorator

    def add_app_template_global(self, f, name=None):
        """Non-decorator version of app_template_global."""
        def deferred_action(app, bp_prefix, bp_name):
            app.add_template_global(f, name)
        self._deferred_actions.append(deferred_action)

    def app_url_defaults(self, f):
        """Register a URL defaults function on the app via blueprint."""
        def deferred_action(app, bp_prefix, bp_name):
            app.url_default_functions.setdefault(None, []).append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def app_url_value_preprocessor(self, f):
        """Register a URL value preprocessor on the app via blueprint."""
        def deferred_action(app, bp_prefix, bp_name):
            app.url_value_preprocessors.setdefault(None, []).append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def url_defaults(self, f):
        """Register a URL defaults function scoped to this blueprint."""
        def deferred_action(app, bp_prefix, bp_name):
            app.url_default_functions.setdefault(bp_name, []).append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def url_value_preprocessor(self, f):
        """Register a URL value preprocessor scoped to this blueprint."""
        def deferred_action(app, bp_prefix, bp_name):
            app.url_value_preprocessors.setdefault(bp_name, []).append(f)
        self._deferred_actions.append(deferred_action)
        return f

    def endpoint(self, endpoint_name):
        """Decorator to register a view function for an endpoint on the blueprint."""
        def decorator(f):
            def deferred_action(app, bp_prefix, bp_name):
                app.view_functions[endpoint_name] = f
            self._deferred_actions.append(deferred_action)
            return f
        return decorator

    def register_error_handler(self, code_or_exception, f):
        """Non-decorator version of errorhandler()."""
        self.error_handlers[code_or_exception] = f

    def register_blueprint(self, blueprint, **options):
        """Register a child blueprint for nesting."""
        if blueprint is self:
            raise ValueError("Cannot register a blueprint on itself.")
        self._blueprints.append((blueprint, options))

    def _register(self, app, options):
        """Register this blueprint on an application (called by app.register_blueprint)."""
        name = options.get("name", self.name)
        url_prefix = options.get("url_prefix")
        if url_prefix is None:
            url_prefix = self.url_prefix
        if url_prefix is None:
            url_prefix = ""
        url_defaults = options.get("url_defaults")
        bp_subdomain = options.get("subdomain")

        # Raise on duplicate registration
        if name in app.blueprints:
            raise ValueError(
                f"The name '{name}' is already registered for a different"
                " blueprint. Use 'name=' to provide a unique name."
            )

        app.blueprints[name] = self
        self._do_register(app, name, url_prefix, url_defaults, bp_subdomain)
        self._register_cli(app, options)

    def _do_register(self, app, name, url_prefix, url_defaults=None, bp_subdomain=None):
        """Execute deferred registrations with resolved name and prefix."""
        # Execute deferred actions
        for action in self._deferred_actions:
            try:
                action(app, url_prefix, name, url_defaults, bp_subdomain)
            except TypeError:
                action(app, url_prefix, name)

        bp_name = name
        effective_subdomain = _merge_subdomain(self.subdomain, bp_subdomain)

        # Register blueprint static route, if any.
        if self.static_folder is not None:
            static_path = self.static_url_path or "/static"
            static_path = _merge_blueprint_prefix(url_prefix, static_path)
            app.add_url_rule(
                static_path.rstrip("/") + "/<path:filename>",
                endpoint=f"{bp_name}.static",
                view_func=self.send_static_file,
                methods=["GET"],
                subdomain=effective_subdomain,
            )

        # Register blueprint-scoped before_request handlers
        for func in self.before_request_funcs:
            def make_scoped_before(f, bn):
                def scoped_before():
                    from cruet.globals import request as req_proxy
                    bp = getattr(req_proxy, 'blueprint', None)
                    if bp is not None and (bp == bn or bp.startswith(bn + ".")):
                        return f()
                return scoped_before
            app.before_request_funcs.append(make_scoped_before(func, bp_name))

        for func in self.after_request_funcs:
            def make_scoped_after(f, bn):
                def scoped_after(response):
                    from cruet.globals import request as req_proxy
                    bp = getattr(req_proxy, 'blueprint', None)
                    if bp is not None and (bp == bn or bp.startswith(bn + ".")):
                        return f(response)
                    return response
                return scoped_after
            app.after_request_funcs.append(make_scoped_after(func, bp_name))

        for func in self.teardown_request_funcs:
            def make_scoped_teardown(f, bn):
                def scoped_teardown(exc):
                    from cruet.globals import request as req_proxy
                    try:
                        bp = getattr(req_proxy, 'blueprint', None)
                        if bp is not None and (bp == bn or bp.startswith(bn + ".")):
                            f(exc)
                    except Exception:
                        pass
                return scoped_teardown
            app.teardown_request_funcs.append(make_scoped_teardown(func, bp_name))

        # Blueprint context processors
        for func in self.template_context_processors:
            def make_scoped_ctx_proc(f, bn):
                def scoped_ctx_proc():
                    from cruet.globals import request as req_proxy
                    bp = getattr(req_proxy, 'blueprint', None)
                    if bp is not None and (bp == bn or bp.startswith(bn + ".")):
                        return f()
                    return {}
                return scoped_ctx_proc
            app.template_context_processors.append(make_scoped_ctx_proc(func, bp_name))

        # Register blueprint-scoped error handlers on the app
        for key, handler in self.error_handlers.items():
            app._register_error_handler(bp_name, key, handler)

        # Register child blueprints
        for child_bp, child_options in self._blueprints:
            child_name = child_options.get("name", child_bp.name)
            child_prefix = child_options.get("url_prefix")
            if child_prefix is None:
                child_prefix = child_bp.url_prefix
            if child_prefix is None:
                child_prefix = ""
            child_reg_subdomain = child_options.get("subdomain")
            merged_subdomain = _merge_subdomain(child_reg_subdomain, effective_subdomain)
            merged_prefix = _merge_blueprint_prefix(url_prefix, child_prefix)
            merged_name = f"{name}.{child_name}"

            app.blueprints[merged_name] = child_bp
            child_bp._do_register(app, merged_name, merged_prefix, None, merged_subdomain)

    def _register_cli(self, app, options):
        if not getattr(self.cli, "commands", None):
            return
        cli_group = options.get("cli_group", self.cli_group)
        if cli_group is _sentinel:
            cli_group = self.name
        if cli_group is None:
            for name, cmd in self.cli.commands.items():
                app.cli.add_command(cmd, name)
            return
        self.cli.name = cli_group
        app.cli.add_command(self.cli, cli_group)

    # Keep backward compatibility
    def register(self, app):
        """Legacy register method."""
        self._register(app, {})

    def get_send_file_max_age(self, filename):
        from cruet.globals import current_app
        return current_app.get_send_file_max_age(filename)

    def send_static_file(self, filename):
        if self.static_folder is None:
            from cruet.app import NotFound
            raise NotFound()
        directory = self.static_folder
        if not os.path.isabs(directory):
            directory = os.path.join(self.root_path, directory)
        from cruet.helpers import send_from_directory
        max_age = self.get_send_file_max_age(filename)
        return send_from_directory(directory, filename, max_age=max_age)
