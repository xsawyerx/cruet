"""Jinja2 template rendering, compatible with Flask's API."""
import os

try:
    import jinja2
    has_jinja2 = True
    try:
        from markupsafe import Markup
    except ImportError:
        Markup = jinja2.Markup
    Environment = jinja2.Environment
except ImportError:
    jinja2 = None
    has_jinja2 = False
    Markup = None
    Environment = None


def _htmlsafe_dumps(dumps_func, obj, **kwargs):
    """JSON-dump and replace HTML-unsafe characters with Unicode escapes."""
    rv = dumps_func(obj, **kwargs)
    return Markup(
        rv.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )


def _tojson_filter_factory(app):
    """Create a tojson filter for the given app."""
    def tojson_filter(obj, **kwargs):
        return _htmlsafe_dumps(app.json.dumps, obj, **kwargs)
    return tojson_filter


# Module-level export for test compatibility
def tojson_filter(obj, **kwargs):
    """Module-level tojson filter (uses current_app)."""
    from cruet.globals import current_app
    app = current_app._get_current_object()
    return _htmlsafe_dumps(app.json.dumps, obj, **kwargs)


def _get_template_folder(app):
    """Resolve the template folder path relative to the app's root_path."""
    folder = getattr(app, "template_folder", "templates")
    if folder is None:
        return None

    if os.path.isabs(folder):
        return folder

    return os.path.join(app.root_path, folder)


def _create_jinja_env(app):
    """Create a Jinja2 Environment for the app."""
    if not has_jinja2:
        raise RuntimeError(
            "Jinja2 is required for template rendering. "
            "Install it with: pip install jinja2"
        )

    # Collect template loaders
    loaders = []

    # App template folder or custom loader
    custom_loader = None
    if hasattr(app, "create_global_jinja_loader"):
        try:
            custom_loader = app.create_global_jinja_loader()
        except Exception:
            custom_loader = None
    if custom_loader is not None:
        loaders.append(custom_loader)
    else:
        folder = _get_template_folder(app)
        if folder and os.path.isdir(folder):
            loaders.append(jinja2.FileSystemLoader(folder))

    # Blueprint template folders
    for bp_name, bp in app.blueprints.items():
        bp_folder = getattr(bp, 'template_folder', None)
        if bp_folder:
            if not os.path.isabs(bp_folder):
                bp_root = getattr(bp, 'root_path', None)
                if bp_root:
                    bp_folder = os.path.join(bp_root, bp_folder)
            if os.path.isdir(bp_folder):
                loaders.append(jinja2.FileSystemLoader(bp_folder))

    if loaders:
        if len(loaders) == 1:
            loader = loaders[0]
        else:
            loader = jinja2.ChoiceLoader(loaders)
    else:
        loader = jinja2.BaseLoader()

    # Get jinja_options from app
    options = dict(getattr(app, 'jinja_options', {}))
    options.setdefault('autoescape', jinja2.select_autoescape(["html", "htm", "xml"]))
    options['loader'] = loader
    options.setdefault('extensions', ['jinja2.ext.do'])

    env_cls = getattr(app, "jinja_environment", None) or jinja2.Environment
    try:
        env = env_cls(**options)
    except TypeError:
        env = env_cls(app, **options)

    # Apply deferred template filters, tests, globals
    for name, func in getattr(app, '_template_filters', {}).items():
        env.filters[name] = func
    for name, func in getattr(app, '_template_tests', {}).items():
        env.tests[name] = func
    for name, func in getattr(app, '_template_globals', {}).items():
        env.globals[name] = func

    # Register tojson filter
    env.filters['tojson'] = _tojson_filter_factory(app)

    # Handle auto_reload config
    auto_reload = app.config.get("TEMPLATES_AUTO_RELOAD")
    if auto_reload is not None:
        env.auto_reload = auto_reload
    else:
        env.auto_reload = app.debug

    # Configure template loading explanation (handled on failure in render_template).

    return env


def _get_jinja_env(app):
    """Get or create the Jinja2 Environment for the app (lazy, cached)."""
    env = getattr(app, "_jinja_env", None)
    if env is None:
        env = _create_jinja_env(app)
        app._jinja_env = env
    return env


def _describe_loader(loader):
    if isinstance(loader, jinja2.FileSystemLoader):
        return f"FileSystemLoader({loader.searchpath})"
    return loader.__class__.__name__


def _find_loader_label(app, loader):
    base = app.jinja_env.loader
    if isinstance(base, jinja2.ChoiceLoader):
        loaders = list(base.loaders)
    else:
        loaders = [base]
    if loader in loaders:
        if loader is loaders[0]:
            return f"trying loader of application '{app.import_name}'"
        idx = loaders.index(loader) + 1
        bp_list = list(app.blueprints.items())
        bp_index = idx - 2
        if 0 <= bp_index < len(bp_list):
            bp_name, bp = bp_list[bp_index]
            return f"trying loader of blueprint '{bp_name}' ({bp.import_name})"
    return f"trying loader {loader.__class__.__name__}"


def _log_template_loading_failure(app, template_name):
    if not has_jinja2:
        return
    if not getattr(app, "logger", None):
        return

    name = template_name if isinstance(template_name, str) else template_name[0]
    lines = []
    lines.append(f"Locating template '{name}':")
    lines.append(f"    1: trying loader of application '{app.name}'")
    idx = 2
    for bp_name, bp in app.blueprints.items():
        lines.append(
            f"    {idx}: trying loader of blueprint '{bp_name}' ({bp.import_name})"
        )
        idx += 1
    lines.append("Error: the template could not be found.")
    try:
        from cruet.globals import request as request_proxy
        bp = getattr(request_proxy, "blueprint", None)
    except Exception:
        bp = None
    if bp:
        lines.append(
            "The template was looked up from an endpoint that belongs to the"
            f" blueprint '{bp}'."
        )
    lines.append("See https://flask.palletsprojects.com/blueprints/#templates")
    app.logger.info("\n".join(lines))


def _make_context(app, kwargs):
    """Build the template context with auto-injected globals."""
    from cruet.globals import _request_ctx_var, _app_ctx_var

    ctx = {}

    # Run context processors first (lowest priority)
    for func in getattr(app, "template_context_processors", []):
        rv = func()
        if rv:
            ctx.update(rv)

    # Inject standard Flask template globals
    ctx.setdefault("config", app.config)

    try:
        req_ctx = _request_ctx_var.get()
        ctx.setdefault("request", req_ctx.request)
        ctx.setdefault("session", req_ctx.session)
    except LookupError:
        pass

    try:
        app_ctx = _app_ctx_var.get()
        ctx.setdefault("g", app_ctx.g)
    except LookupError:
        pass

    from cruet.helpers import url_for, get_flashed_messages
    ctx.setdefault("url_for", url_for)
    ctx.setdefault("get_flashed_messages", get_flashed_messages)

    # Explicit kwargs override everything
    ctx.update(kwargs)

    return ctx


def render_template(template_name, **context):
    """Render a template file by name with the given context."""
    from cruet.globals import _app_ctx_var
    from cruet.signals import before_render_template, template_rendered
    app = _app_ctx_var.get().app

    env = _get_jinja_env(app)
    try:
        if isinstance(template_name, (list, tuple)):
            template = env.select_template(template_name)
        else:
            template = env.get_template(template_name)
    except jinja2.TemplateNotFound:
        if app.config.get("EXPLAIN_TEMPLATE_LOADING"):
            _log_template_loading_failure(app, template_name)
        raise
    ctx = _make_context(app, context)
    try:
        before_render_template.send(app, template=template, context=ctx)
    except Exception:
        pass
    rv = template.render(ctx)
    try:
        template_rendered.send(app, template=template, context=ctx)
    except Exception:
        pass
    return rv


def render_template_string(source, **context):
    """Render a template from a string with the given context."""
    from cruet.globals import _app_ctx_var
    from cruet.signals import before_render_template, template_rendered
    app = _app_ctx_var.get().app

    env = _get_jinja_env(app)
    template = env.from_string(source)
    ctx = _make_context(app, context)
    try:
        before_render_template.send(app, template=template, context=ctx)
    except Exception:
        pass
    rv = template.render(ctx)
    try:
        template_rendered.send(app, template=template, context=ctx)
    except Exception:
        pass
    return rv


def stream_template(template_name, **context):
    """Render a template by name with streaming."""
    from cruet.globals import _app_ctx_var
    app = _app_ctx_var.get().app

    env = _get_jinja_env(app)
    template = env.get_template(template_name)
    ctx = _make_context(app, context)
    return template.stream(ctx)


def stream_template_string(source, **context):
    """Render a template string with streaming."""
    from cruet.globals import _app_ctx_var
    app = _app_ctx_var.get().app

    env = _get_jinja_env(app)
    template = env.from_string(source)
    ctx = _make_context(app, context)
    return template.stream(ctx)


def get_template_attribute(template_name, attribute):
    """Get an attribute from a template (e.g. a macro)."""
    from cruet.globals import _app_ctx_var
    app = _app_ctx_var.get().app

    env = _get_jinja_env(app)
    template = env.get_template(template_name)
    return getattr(template.module, attribute)
