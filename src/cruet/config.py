"""Flask-compatible Config class."""
import os


class Config(dict):
    """A dict subclass for app configuration, compatible with Flask's Config.

    Supports loading from Python objects, mappings, and environment variables.
    Keys are always uppercase strings (by convention, not enforced).
    """

    def __init__(self, root_path=None, defaults=None):
        if defaults is None and root_path is not None and not isinstance(
            root_path, (str, bytes, os.PathLike)
        ):
            defaults = root_path
            root_path = None
        self.root_path = os.fspath(root_path) if root_path else os.getcwd()
        super().__init__(defaults or {})

    def from_mapping(self, mapping=None, **kwargs):
        """Update config from a mapping or keyword arguments.

        Returns True (for consistency with Flask).
        """
        if mapping is not None:
            if hasattr(mapping, "items"):
                for key, value in mapping.items():
                    self[key] = value
            else:
                for key, value in mapping:
                    self[key] = value
        for key, value in kwargs.items():
            self[key] = value
        return True

    def from_object(self, obj):
        """Update config from an object's uppercase attributes.

        The object can be a module, a class, or any object with attributes.
        Only attributes with UPPERCASE names are loaded (matching Flask).

        Returns True (for consistency with Flask).
        """
        if isinstance(obj, str):
            import importlib
            obj = importlib.import_module(obj)
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)
        return True

    def from_envvar(self, variable_name, silent=False):
        """Load config from a file path specified by an environment variable.

        Args:
            variable_name: Name of the environment variable containing the path.
            silent: If True, silently ignore if the variable is not set.

        Returns True on success, False if silent and variable not set.
        """
        rv = os.environ.get(variable_name)
        if not rv:
            if silent:
                return False
            raise RuntimeError(
                f"The environment variable {variable_name!r} is not set and "
                "as such configuration could not be loaded. Set this variable "
                "and make it point to a configuration file."
            )
        return self.from_pyfile(rv, silent=silent)

    def from_pyfile(self, filename, silent=False):
        """Update config from a Python file.

        The file is executed as Python code and all uppercase variables
        are loaded into the config (matching Flask's behavior).

        Args:
            filename: Path to a .py file.
            silent: If True, silently ignore missing files.

        Returns True on success, False if silent and file not found.
        """
        filename = os.fspath(filename)
        if not os.path.isabs(filename):
            filename = os.path.join(self.root_path, filename)
        try:
            d = {"__file__": filename, "__name__": "__config__"}
            with open(filename, "rb") as f:
                exec(compile(f.read(), filename, "exec"), d)  # noqa: S102
        except FileNotFoundError:
            if silent:
                return False
            raise OSError(
                f"[Errno 2] Unable to load configuration file"
                f" (No such file or directory): {filename!r}"
            )
        for key, value in d.items():
            if key.isupper():
                self[key] = value
        return True

    def from_file(self, filename, load, silent=False, text=True):
        """Update config from a file using a custom loader.

        Flask 2.0+ API. Load a file (e.g. JSON, TOML) using the
        provided `load` callable.

        Usage::

            import json
            app.config.from_file("config.json", load=json.load)

            import tomllib
            app.config.from_file("config.toml", load=tomllib.load, text=False)

        Args:
            filename: Path to the config file.
            load: Callable that takes a file object and returns a dict.
            silent: If True, silently ignore missing files.
            text: If True, open in text mode; if False, open in binary mode.

        Returns True on success, False if silent and file not found.
        """
        filename = os.fspath(filename)
        if not os.path.isabs(filename):
            filename = os.path.join(self.root_path, filename)
        try:
            mode = "r" if text else "rb"
            with open(filename, mode) as f:
                obj = load(f)
        except FileNotFoundError:
            if silent:
                return False
            raise OSError(
                f"[Errno 2] Unable to load configuration file"
                f" (No such file or directory): {filename!r}"
            )
        return self.from_mapping(obj)

    def from_prefixed_env(self, prefix="FLASK", loads=None):
        """Update config from environment variables with the given prefix.

        For example, with prefix="FLASK", the env var FLASK_DEBUG
        sets config["DEBUG"].

        Values are always deserialized via ``loads`` (default: ``json.loads``).
        If deserialization fails, the raw string value is kept.
        """
        import json as _json
        if loads is None:
            loads = _json.loads
        prefix = prefix + "_"
        plen = len(prefix)
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[plen:]
                try:
                    value = loads(value)
                except Exception:
                    pass
                if "__" in config_key:
                    parts = config_key.split("__")
                    current = self
                    for part in parts[:-1]:
                        if part not in current or not isinstance(current[part], dict):
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = value
                else:
                    self[config_key] = value

    def get_namespace(self, namespace, lowercase=True, trim_namespace=True):
        """Return a dict of config keys that start with the given namespace.

        For example, get_namespace("SQLALCHEMY_") returns all keys starting
        with SQLALCHEMY_, optionally stripping the prefix and lowercasing.
        """
        result = {}
        for key, value in self.items():
            if not key.startswith(namespace):
                continue
            if trim_namespace:
                key = key[len(namespace):]
            if lowercase:
                key = key.lower()
            result[key] = value
        return result

    def __repr__(self):
        return f"<Config {dict.__repr__(self)}>"
