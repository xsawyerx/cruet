"""Flask-compatible CLI support for Cruet."""
from __future__ import annotations

import ast
import importlib.metadata
import inspect
import os
import platform
import re
import sys
import traceback
import typing as t
from functools import update_wrapper
from operator import itemgetter

import click
from click.core import ParameterSource
from werkzeug.utils import import_string

from cruet.globals import current_app

if t.TYPE_CHECKING:
    import ssl
    from types import ModuleType
    from cruet.app import Cruet as Flask


class NoAppException(click.UsageError):
    """Raised if an application cannot be found or loaded."""


def _called_with_wrong_args(f: t.Callable[..., t.Any]) -> bool:
    tb = sys.exc_info()[2]
    try:
        while tb is not None:
            if tb.tb_frame.f_code is f.__code__:
                return False
            tb = tb.tb_next
        return True
    finally:
        del tb


def find_best_app(module: ModuleType) -> Flask:
    from cruet import Cruet as Flask

    for attr_name in ("app", "application"):
        app = getattr(module, attr_name, None)
        if isinstance(app, Flask):
            return app

    matches = [v for v in module.__dict__.values() if isinstance(v, Flask)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise NoAppException(
            "Detected multiple Flask applications in module"
            f" '{module.__name__}'. Use '{module.__name__}:name'"
            " to specify the correct one."
        )

    for attr_name in ("create_app", "make_app"):
        app_factory = getattr(module, attr_name, None)
        if callable(app_factory):
            try:
                app = app_factory()
                if isinstance(app, Flask):
                    return app
            except TypeError as e:
                if not _called_with_wrong_args(app_factory):
                    raise
                raise NoAppException(
                    f"Detected factory '{attr_name}' in module '{module.__name__}',"
                    " but could not call it without arguments. Use"
                    f" '{module.__name__}:{attr_name}(args)'"
                    " to specify arguments."
                ) from e

    raise NoAppException(
        "Failed to find Flask application or factory in module"
        f" '{module.__name__}'. Use '{module.__name__}:name'"
        " to specify one."
    )


def find_app_by_string(module: ModuleType, app_name: str) -> Flask:
    from cruet import Cruet as Flask

    try:
        expr = ast.parse(app_name.strip(), mode="eval").body
    except SyntaxError:
        raise NoAppException(
            f"Failed to parse {app_name!r} as an attribute name or function call."
        ) from None

    if isinstance(expr, ast.Name):
        name = expr.id
        args: list[t.Any] = []
        kwargs: dict[str, t.Any] = {}
    elif isinstance(expr, ast.Call):
        if not isinstance(expr.func, ast.Name):
            raise NoAppException(
                f"Function reference must be a simple name: {app_name!r}."
            )
        name = expr.func.id
        try:
            args = [ast.literal_eval(arg) for arg in expr.args]
            kwargs = {
                kw.arg: ast.literal_eval(kw.value)
                for kw in expr.keywords
                if kw.arg is not None
            }
        except ValueError:
            raise NoAppException(
                f"Failed to parse arguments as literal values: {app_name!r}."
            ) from None
    else:
        raise NoAppException(
            f"Failed to parse {app_name!r} as an attribute name or function call."
        )

    try:
        attr = getattr(module, name)
    except AttributeError as e:
        raise NoAppException(
            f"Failed to find attribute {name!r} in {module.__name__!r}."
        ) from e

    if inspect.isfunction(attr):
        try:
            app = attr(*args, **kwargs)
        except TypeError as e:
            if not _called_with_wrong_args(attr):
                raise
            raise NoAppException(
                f"The factory {app_name!r} in module"
                f" {module.__name__!r} could not be called with the"
                " specified arguments."
            ) from e
    else:
        app = attr

    if isinstance(app, Flask):
        return app

    raise NoAppException(
        "A valid Flask application was not obtained from"
        f" '{module.__name__}:{app_name}'."
    )


def prepare_import(path: str) -> str:
    path = os.path.realpath(path)
    fname, ext = os.path.splitext(path)
    if ext == ".py":
        path = fname
    if os.path.basename(path) == "__init__":
        path = os.path.dirname(path)

    module_name: list[str] = []
    while True:
        path, name = os.path.split(path)
        module_name.append(name)
        if not os.path.exists(os.path.join(path, "__init__.py")):
            break

    if sys.path[0] != path:
        sys.path.insert(0, path)

    return ".".join(module_name[::-1])


def locate_app(
    module_name: str, app_name: str | None, raise_if_not_found: bool = True
) -> Flask | None:
    try:
        __import__(module_name)
    except ImportError:
        if sys.exc_info()[2].tb_next:  # type: ignore[union-attr]
            raise NoAppException(
                f"While importing {module_name!r}, an ImportError was"
                f" raised:\n\n{traceback.format_exc()}"
            ) from None
        if raise_if_not_found:
            raise NoAppException(f"Could not import {module_name!r}.") from None
        return None

    module = sys.modules[module_name]
    if app_name is None:
        return find_best_app(module)
    return find_app_by_string(module, app_name)


def get_version(ctx: click.Context, param: click.Parameter, value: t.Any) -> None:
    if not value or ctx.resilient_parsing:
        return
    flask_version = importlib.metadata.version("flask")
    werkzeug_version = importlib.metadata.version("werkzeug")
    click.echo(
        f"Python {platform.python_version()}\n"
        f"Flask {flask_version}\n"
        f"Werkzeug {werkzeug_version}",
        color=ctx.color,
    )
    ctx.exit()


version_option = click.Option(
    ["--version"],
    help="Show the Flask version.",
    expose_value=False,
    callback=get_version,
    is_flag=True,
    is_eager=True,
)


def get_debug_flag() -> bool:
    val = os.environ.get("FLASK_DEBUG")
    if val is None:
        return False
    val = val.strip().lower()
    return val in {"1", "true", "t", "yes", "y", "on"}


def get_load_dotenv(default: bool) -> bool:
    if not default:
        return False
    return not bool(os.environ.get("FLASK_SKIP_DOTENV"))


class ScriptInfo:
    def __init__(
        self,
        app_import_path: str | None = None,
        create_app: t.Callable[..., Flask] | None = None,
        set_debug_flag: bool = True,
        load_dotenv_defaults: bool = True,
    ) -> None:
        self.app_import_path = app_import_path
        self.create_app = create_app
        self.data: dict[t.Any, t.Any] = {}
        self.set_debug_flag = set_debug_flag
        self.load_dotenv_defaults = get_load_dotenv(load_dotenv_defaults)
        self._loaded_app: Flask | None = None

    def load_app(self) -> Flask:
        if self._loaded_app is not None:
            return self._loaded_app

        app: Flask | None = None
        if self.create_app is not None:
            app = self.create_app()
        else:
            if self.app_import_path:
                path, name = (
                    re.split(r":(?![\\/])", self.app_import_path, maxsplit=1) + [None]
                )[:2]
                import_name = prepare_import(path)
                app = locate_app(import_name, name)
            else:
                for path in ("wsgi.py", "app.py"):
                    import_name = prepare_import(path)
                    app = locate_app(import_name, None, raise_if_not_found=False)
                    if app is not None:
                        break

        if app is None:
            raise NoAppException(
                "Could not locate a Flask application. Use the"
                " 'flask --app' option, 'FLASK_APP' environment"
                " variable, or a 'wsgi.py' or 'app.py' file in the"
                " current directory."
            )

        if self.set_debug_flag:
            app.debug = get_debug_flag()

        self._loaded_app = app
        return app


pass_script_info = click.make_pass_decorator(ScriptInfo, ensure=True)

F = t.TypeVar("F", bound=t.Callable[..., t.Any])


def with_appcontext(f: F) -> F:
    @click.pass_context
    def decorator(ctx: click.Context, /, *args: t.Any, **kwargs: t.Any) -> t.Any:
        if not current_app:
            app = ctx.ensure_object(ScriptInfo).load_app()
            ctx.with_resource(app.app_context())
        return ctx.invoke(f, *args, **kwargs)

    return update_wrapper(decorator, f)  # type: ignore[return-value]


class AppGroup(click.Group):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)
        import weakref
        self._app_ref = None

    def command(  # type: ignore[override]
        self, *args: t.Any, **kwargs: t.Any
    ) -> t.Callable[[t.Callable[..., t.Any]], click.Command]:
        wrap_for_ctx = kwargs.pop("with_appcontext", True)

        def decorator(f: t.Callable[..., t.Any]) -> click.Command:
            if wrap_for_ctx:
                app = self._app_ref() if self._app_ref is not None else None
                if app is not None:
                    orig = f
                    @click.pass_context
                    def _wrapped(ctx: click.Context, /, *a: t.Any, **kw: t.Any) -> t.Any:
                        if not current_app:
                            info = ctx.ensure_object(ScriptInfo)
                            if info.create_app is not None and info._loaded_app is None:
                                info.load_app()
                            with app.app_context():
                                return ctx.invoke(orig, *a, **kw)
                        return ctx.invoke(orig, *a, **kw)
                    f = update_wrapper(_wrapped, orig)
                else:
                    f = with_appcontext(f)
            return super(AppGroup, self).command(*args, **kwargs)(f)  # type: ignore[no-any-return]

        return decorator

    def group(  # type: ignore[override]
        self, *args: t.Any, **kwargs: t.Any
    ) -> t.Callable[[t.Callable[..., t.Any]], click.Group]:
        kwargs.setdefault("cls", AppGroup)
        decorator = super().group(*args, **kwargs)  # type: ignore[no-any-return]
        def _decorator(f: t.Callable[..., t.Any]) -> click.Group:
            grp = decorator(f)
            if isinstance(grp, AppGroup):
                grp._app_ref = self._app_ref
            return grp
        return _decorator

    def __contains__(self, name: str) -> bool:
        return name in self.commands

    def __getitem__(self, name: str) -> click.Command:
        return self.commands[name]

    @property
    def _group(self) -> "AppGroup":
        return self

    def list_commands(self, ctx: click.Context | None = None) -> list[str]:  # type: ignore[override]
        return sorted(self.commands)

    def main(self, *args: t.Any, **kwargs: t.Any) -> t.Any:  # type: ignore[override]
        return super().main(*args, **kwargs)


def _set_app(ctx: click.Context, param: click.Option, value: str | None) -> str | None:
    if value is None:
        return None
    info = ctx.ensure_object(ScriptInfo)
    info.app_import_path = value
    return value


_app_option = click.Option(
    ["-A", "--app"],
    metavar="IMPORT",
    help=(
        "The Flask application or factory function to load, in the form 'module:name'."
        " Module can be a dotted import or file path. Name is not required if it is"
        " 'app', 'application', 'create_app', or 'make_app', and can be 'name(args)' to"
        " pass arguments."
    ),
    is_eager=True,
    expose_value=False,
    callback=_set_app,
)


def _set_debug(ctx: click.Context, param: click.Option, value: bool) -> bool | None:
    source = ctx.get_parameter_source(param.name)  # type: ignore[arg-type]
    if source is not None and source in (
        ParameterSource.DEFAULT,
        ParameterSource.DEFAULT_MAP,
    ):
        return None
    os.environ["FLASK_DEBUG"] = "1" if value else "0"
    return value


_debug_option = click.Option(
    ["--debug/--no-debug"],
    help="Set debug mode.",
    expose_value=False,
    callback=_set_debug,
)


def _env_file_callback(
    ctx: click.Context, param: click.Option, value: str | None
) -> str | None:
    try:
        import dotenv  # noqa: F401
    except ImportError:
        if value is not None:
            raise click.BadParameter(
                "python-dotenv must be installed to load an env file.",
                ctx=ctx,
                param=param,
            ) from None

    if value is not None or ctx.obj.load_dotenv_defaults:
        load_dotenv(value, load_defaults=ctx.obj.load_dotenv_defaults)

    return value


_env_file_option = click.Option(
    ["-e", "--env-file"],
    type=click.Path(exists=True, dir_okay=False),
    help=(
        "Load environment variables from this file, taking precedence over"
        " those set by '.env' and '.flaskenv'. Variables set directly in the"
        " environment take highest precedence. python-dotenv must be installed."
    ),
    is_eager=True,
    expose_value=False,
    callback=_env_file_callback,
)


class FlaskGroup(AppGroup):
    def __init__(
        self,
        add_default_commands: bool = True,
        create_app: t.Callable[..., Flask] | None = None,
        add_version_option: bool = True,
        load_dotenv: bool = True,
        set_debug_flag: bool = True,
        **extra: t.Any,
    ) -> None:
        params: list[click.Parameter] = list(extra.pop("params", None) or ())
        params.extend((_env_file_option, _app_option, _debug_option))
        if add_version_option:
            params.append(version_option)
        if "context_settings" not in extra:
            extra["context_settings"] = {}
        extra["context_settings"].setdefault("auto_envvar_prefix", "FLASK")
        super().__init__(params=params, **extra)

        self.create_app = create_app
        self.load_dotenv = get_load_dotenv(load_dotenv)
        self.set_debug_flag = set_debug_flag

        if add_default_commands:
            self.add_command(run_command)
            self.add_command(routes_command)

        self._loaded_plugin_commands = False

    def _load_plugin_commands(self) -> None:
        if self._loaded_plugin_commands:
            return
        for ep in importlib.metadata.entry_points(group="flask.commands"):
            self.add_command(ep.load(), ep.name)
        self._loaded_plugin_commands = True

    def get_command(self, ctx: click.Context, name: str) -> click.Command | None:
        self._load_plugin_commands()
        rv = super().get_command(ctx, name)
        if rv is not None:
            return rv

        info = ctx.ensure_object(ScriptInfo)
        try:
            app = info.load_app()
        except NoAppException as e:
            click.secho(f"Error: {e.format_message()}\n", err=True, fg="red")
            return None

        if not current_app or current_app._get_current_object() is not app:
            ctx.with_resource(app.app_context())

        return app.cli.get_command(ctx, name)

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._load_plugin_commands()
        rv = set(super().list_commands(ctx))
        info = ctx.ensure_object(ScriptInfo)
        try:
            rv.update(info.load_app().cli.list_commands(ctx))
        except NoAppException as e:
            click.secho(f"Error: {e.format_message()}\n", err=True, fg="red")
        except Exception:
            click.secho(f"{traceback.format_exc()}\n", err=True, fg="red")
        return sorted(rv)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: t.Any,
    ) -> click.Context:
        os.environ["FLASK_RUN_FROM_CLI"] = "true"
        if "obj" not in extra and "obj" not in self.context_settings:
            extra["obj"] = ScriptInfo(
                create_app=self.create_app,
                set_debug_flag=self.set_debug_flag,
                load_dotenv_defaults=self.load_dotenv,
            )
        return super().make_context(info_name, args, parent=parent, **extra)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if (not args and self.no_args_is_help) or (
            len(args) == 1 and args[0] in self.get_help_option_names(ctx)
        ):
            _env_file_option.handle_parse_result(ctx, {}, [])
            _app_option.handle_parse_result(ctx, {}, [])
        return super().parse_args(ctx, args)


def load_dotenv(
    path: str | os.PathLike[str] | None = None, load_defaults: bool = True
) -> bool:
    try:
        import dotenv
    except ImportError:
        return False

    data: dict[str, str | None] = {}
    if load_defaults:
        for default_name in (".flaskenv", ".env"):
            default_path = dotenv.find_dotenv(default_name, usecwd=True)
            if not default_path:
                continue
            data |= dotenv.dotenv_values(default_path, encoding="utf-8")

    if path is not None and os.path.isfile(path):
        data |= dotenv.dotenv_values(path, encoding="utf-8")

    for key, value in data.items():
        if key in os.environ or value is None:
            continue
        os.environ[key] = value

    return bool(data)


class CertParamType(click.ParamType):
    name = "path"

    def __init__(self) -> None:
        self.path_type = click.Path(exists=True, dir_okay=False, resolve_path=True)

    def convert(
        self, value: t.Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> t.Any:
        try:
            import ssl
        except ImportError:
            raise click.BadParameter(
                'Using "--cert" requires Python to be compiled with SSL support.',
                ctx,
                param,
            ) from None
        if ssl is None:
            raise click.BadParameter(
                'Using "--cert" requires Python to be compiled with SSL support.',
                ctx,
                param,
            ) from None

        try:
            return self.path_type(value, param, ctx)
        except click.BadParameter:
            value = click.STRING(value, param, ctx).lower()
            if value == "adhoc":
                try:
                    import cryptography  # noqa: F401
                except ImportError:
                    raise click.BadParameter(
                        "Using ad-hoc certificates requires the cryptography library.",
                        ctx,
                        param,
                    ) from None
                return value

            obj = import_string(value, silent=True)
            if isinstance(obj, ssl.SSLContext):
                return obj
            raise


class SeparatedPathType(click.Path):
    def convert(
        self, value: t.Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> t.Any:
        items = self.split_envvar_value(value)
        super_convert = super().convert
        return [super_convert(item, param, ctx) for item in items]


class RunCommand(click.Command):
    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        rv = super().parse_args(ctx, args)
        cert = ctx.params.get("cert")
        key = ctx.params.get("key")
        is_adhoc = cert == "adhoc"
        try:
            import ssl
        except ImportError:
            is_context = False
        else:
            is_context = isinstance(cert, ssl.SSLContext)

        if key is not None:
            if is_adhoc:
                raise click.BadParameter(
                    'When "--cert" is "adhoc", "--key" is not used.', ctx=ctx
                )
            if is_context:
                raise click.BadParameter(
                    'When "--cert" is an SSLContext object, "--key" is not used.',
                    ctx=ctx,
                )
            if not cert:
                raise click.BadParameter('"--cert" must also be specified.', ctx=ctx)
            ctx.params["cert"] = cert, key
        else:
            if cert and not (is_adhoc or is_context):
                raise click.BadParameter('Required when using "--cert".', ctx=ctx)
        return rv


@click.command("run", short_help="Run a local development server.", cls=RunCommand)
@click.option(
    "--cert",
    type=CertParamType(),
    default=None,
    help="SSL certificate file.",
)
@click.option(
    "--key",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    default=None,
    help="SSL key file.",
)
@click.option(
    "--exclude-patterns",
    default=None,
    type=SeparatedPathType(),
    help=(
        "Files matching these fnmatch patterns will not trigger a reload"
        " on change. Multiple patterns are separated by"
        f" {os.path.pathsep!r}."
    ),
)
@pass_script_info
def run_command(
    info: ScriptInfo,
    cert: ssl.SSLContext | tuple[str, str | None] | t.Literal["adhoc"] | None,
    key: str | None,
    exclude_patterns: list[str] | None,
) -> None:
    return None


run_command.params.insert(0, _debug_option)


@click.command("routes", short_help="Show the routes for the app.")
@click.option(
    "--sort",
    "-s",
    type=click.Choice(("endpoint", "methods", "domain", "rule", "match")),
    default="endpoint",
    help=(
        "Method to sort routes by. 'match' is the order that Flask will match routes"
        " when dispatching a request."
    ),
)
@click.option("--all-methods", is_flag=True, help="Show HEAD and OPTIONS methods.")
@with_appcontext
def routes_command(sort: str, all_methods: bool) -> None:
    rules = list(current_app.url_map.iter_rules())
    if not rules:
        click.echo("No routes were registered.")
        return

    ignored_methods = set() if all_methods else {"HEAD", "OPTIONS"}
    host_matching = getattr(current_app.url_map, "host_matching", False)
    def _rule_domain(rule):
        if host_matching:
            return getattr(rule, "host", None)
        return getattr(rule, "subdomain", None)
    has_domain = any(_rule_domain(rule) for rule in rules)
    rows = []

    for rule in rules:
        methods = getattr(rule, "methods", None) or set()
        row = [
            rule.endpoint,
            ", ".join(sorted(methods - ignored_methods)),
        ]
        if has_domain:
            row.append(_rule_domain(rule) or "")
        row.append(rule.rule)
        rows.append(row)

    headers = ["Endpoint", "Methods"]
    sorts = ["endpoint", "methods"]
    if has_domain:
        headers.append("Host" if host_matching else "Subdomain")
        sorts.append("domain")
    headers.append("Rule")
    sorts.append("rule")

    try:
        rows.sort(key=itemgetter(sorts.index(sort)))
    except ValueError:
        pass

    rows.insert(0, headers)
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    rows.insert(1, ["-" * w for w in widths])
    template = "  ".join(f"{{{i}:<{w}}}" for i, w in enumerate(widths))
    for row in rows:
        click.echo(template.format(*row))


cli = FlaskGroup(
    name="flask",
    help=(
        "A general utility script for Flask applications.\n\n"
        "An application to load must be given with the '--app' option,\n"
        "'FLASK_APP' environment variable, or with a 'wsgi.py' or 'app.py' file\n"
        "in the current directory."
    ),
)
