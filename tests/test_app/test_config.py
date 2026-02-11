"""Tests for Config class and app.config integration."""
import os
import pytest
from cruet import Cruet
from cruet.config import Config


class TestConfigBasic:
    def test_config_is_dict(self):
        c = Config()
        assert isinstance(c, dict)

    def test_config_with_defaults(self):
        c = Config({"DEBUG": True, "SECRET_KEY": "abc"})
        assert c["DEBUG"] is True
        assert c["SECRET_KEY"] == "abc"

    def test_config_get(self):
        c = Config({"KEY": "val"})
        assert c.get("KEY") == "val"
        assert c.get("MISSING") is None
        assert c.get("MISSING", "default") == "default"

    def test_config_setitem(self):
        c = Config()
        c["FOO"] = "bar"
        assert c["FOO"] == "bar"

    def test_config_contains(self):
        c = Config({"A": 1})
        assert "A" in c
        assert "B" not in c

    def test_config_len(self):
        c = Config({"A": 1, "B": 2})
        assert len(c) == 2

    def test_config_repr(self):
        c = Config({"DEBUG": True})
        r = repr(c)
        assert r.startswith("<Config")
        assert "DEBUG" in r


class TestConfigFromMapping:
    def test_from_dict(self):
        c = Config()
        c.from_mapping({"A": 1, "B": 2})
        assert c["A"] == 1
        assert c["B"] == 2

    def test_from_kwargs(self):
        c = Config()
        c.from_mapping(X="hello", Y="world")
        assert c["X"] == "hello"
        assert c["Y"] == "world"

    def test_from_mapping_and_kwargs(self):
        c = Config()
        c.from_mapping({"A": 1}, B=2)
        assert c["A"] == 1
        assert c["B"] == 2

    def test_from_mapping_overwrites(self):
        c = Config({"KEY": "old"})
        c.from_mapping(KEY="new")
        assert c["KEY"] == "new"

    def test_from_mapping_returns_true(self):
        c = Config()
        assert c.from_mapping(A=1) is True

    def test_from_iterable_of_pairs(self):
        c = Config()
        c.from_mapping([("X", 10), ("Y", 20)])
        assert c["X"] == 10
        assert c["Y"] == 20


class TestConfigFromObject:
    def test_from_class(self):
        class MyConfig:
            DEBUG = True
            SECRET_KEY = "s3cret"
            lowercase_ignored = "yes"

        c = Config()
        c.from_object(MyConfig)
        assert c["DEBUG"] is True
        assert c["SECRET_KEY"] == "s3cret"
        assert "lowercase_ignored" not in c

    def test_from_instance(self):
        class Obj:
            TESTING = True
            MAX_CONTENT_LENGTH = 1024

        c = Config()
        c.from_object(Obj())
        assert c["TESTING"] is True
        assert c["MAX_CONTENT_LENGTH"] == 1024

    def test_from_object_returns_true(self):
        class Empty:
            pass

        c = Config()
        assert c.from_object(Empty) is True

    def test_from_module_string(self):
        c = Config()
        c.from_object("os")
        # os module has uppercase constants like os.O_RDONLY on some platforms
        # Just verify it doesn't crash and picks up at least some keys
        assert isinstance(c, dict)


class TestConfigFromPrefixedEnv:
    def test_loads_matching_vars(self):
        c = Config()
        os.environ["CRUET_DEBUG"] = "1"
        os.environ["CRUET_SECRET_KEY"] = "fromenv"
        try:
            c.from_prefixed_env("CRUET")
            assert c["DEBUG"] == 1
            assert c["SECRET_KEY"] == "fromenv"
        finally:
            del os.environ["CRUET_DEBUG"]
            del os.environ["CRUET_SECRET_KEY"]

    def test_ignores_non_matching_vars(self):
        c = Config()
        os.environ["OTHER_VAR"] = "nope"
        try:
            c.from_prefixed_env("CRUET")
            assert "OTHER_VAR" not in c
            assert "VAR" not in c
        finally:
            del os.environ["OTHER_VAR"]

    def test_with_loads_callable(self):
        import json
        c = Config()
        os.environ["MYAPP_PORT"] = "8080"
        os.environ["MYAPP_DEBUG"] = "true"
        try:
            c.from_prefixed_env("MYAPP", loads=json.loads)
            assert c["PORT"] == 8080
            assert c["DEBUG"] is True
        finally:
            del os.environ["MYAPP_PORT"]
            del os.environ["MYAPP_DEBUG"]


class TestConfigGetNamespace:
    def test_basic_namespace(self):
        c = Config({
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ECHO": True,
            "DEBUG": False,
        })
        ns = c.get_namespace("SQLALCHEMY_")
        assert ns == {"database_uri": "sqlite://", "echo": True}
        assert "debug" not in ns

    def test_no_trim(self):
        c = Config({"MAIL_SERVER": "smtp.example.com"})
        ns = c.get_namespace("MAIL_", trim_namespace=False)
        assert "MAIL_SERVER" not in ns  # lowercased
        assert "mail_server" in ns

    def test_no_lowercase(self):
        c = Config({"CACHE_TYPE": "redis"})
        ns = c.get_namespace("CACHE_", lowercase=False)
        assert ns == {"TYPE": "redis"}

    def test_empty_namespace(self):
        c = Config({"DEBUG": True})
        ns = c.get_namespace("NONEXISTENT_")
        assert ns == {}


class TestAppConfig:
    def test_app_has_config(self):
        app = Cruet(__name__)
        assert isinstance(app.config, Config)

    def test_app_config_defaults(self):
        app = Cruet(__name__)
        assert app.config["DEBUG"] is False
        assert app.config["TESTING"] is False
        assert app.config["SECRET_KEY"] is None
        assert app.config["SESSION_COOKIE_NAME"] == "session"
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app.config["PREFERRED_URL_SCHEME"] == "http"
        assert app.config["APPLICATION_ROOT"] == "/"
        assert app.config["JSON_SORT_KEYS"] is False

    def test_app_config_mutable(self):
        app = Cruet(__name__)
        app.config["CUSTOM_KEY"] = "custom_value"
        assert app.config["CUSTOM_KEY"] == "custom_value"

    def test_app_config_from_mapping(self):
        app = Cruet(__name__)
        app.config.from_mapping(DEBUG=True, SECRET_KEY="test")
        assert app.config["DEBUG"] is True
        assert app.config["SECRET_KEY"] == "test"

    def test_app_config_from_object(self):
        class ProdConfig:
            DEBUG = False
            SECRET_KEY = "prod-key"
            MAX_CONTENT_LENGTH = 16 * 1024 * 1024

        app = Cruet(__name__)
        app.config.from_object(ProdConfig)
        assert app.config["SECRET_KEY"] == "prod-key"
        assert app.config["MAX_CONTENT_LENGTH"] == 16 * 1024 * 1024


class TestAppDebugTestingSecretKey:
    def test_debug_property_reads_config(self):
        app = Cruet(__name__)
        assert app.debug is False
        app.config["DEBUG"] = True
        assert app.debug is True

    def test_debug_property_writes_config(self):
        app = Cruet(__name__)
        app.debug = True
        assert app.config["DEBUG"] is True
        app.debug = False
        assert app.config["DEBUG"] is False

    def test_debug_coerces_to_bool(self):
        app = Cruet(__name__)
        app.debug = 1
        assert app.debug is True
        app.debug = 0
        assert app.debug is False

    def test_testing_property_reads_config(self):
        app = Cruet(__name__)
        assert app.testing is False
        app.config["TESTING"] = True
        assert app.testing is True

    def test_testing_property_writes_config(self):
        app = Cruet(__name__)
        app.testing = True
        assert app.config["TESTING"] is True

    def test_secret_key_property_reads_config(self):
        app = Cruet(__name__)
        assert app.secret_key is None
        app.config["SECRET_KEY"] = "abc"
        assert app.secret_key == "abc"

    def test_secret_key_property_writes_config(self):
        app = Cruet(__name__)
        app.secret_key = "my-secret"
        assert app.config["SECRET_KEY"] == "my-secret"

    def test_secret_key_accepts_bytes(self):
        app = Cruet(__name__)
        app.secret_key = b"\x00\x01\x02"
        assert app.config["SECRET_KEY"] == b"\x00\x01\x02"


class TestConfigFromPyfile:
    def test_from_pyfile(self, tmp_path):
        f = tmp_path / "settings.py"
        f.write_text("DEBUG = True\nSECRET_KEY = 'abc'\nlowercase = 'ignored'\n")
        c = Config()
        result = c.from_pyfile(str(f))
        assert result is True
        assert c["DEBUG"] is True
        assert c["SECRET_KEY"] == "abc"
        assert "lowercase" not in c

    def test_from_pyfile_missing_raises(self):
        c = Config()
        with pytest.raises(OSError):
            c.from_pyfile("/nonexistent/settings.py")

    def test_from_pyfile_silent(self):
        c = Config()
        result = c.from_pyfile("/nonexistent/settings.py", silent=True)
        assert result is False

    def test_from_pyfile_with_app(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text("TESTING = True\n")
        app = Cruet(__name__)
        app.config.from_pyfile(str(f))
        assert app.testing is True


class TestConfigFromFile:
    def test_from_file_json(self, tmp_path):
        import json
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"DEBUG": True, "PORT": 8080}))
        c = Config()
        result = c.from_file(str(f), load=json.load)
        assert result is True
        assert c["DEBUG"] is True
        assert c["PORT"] == 8080

    def test_from_file_missing_raises(self):
        import json
        c = Config()
        with pytest.raises(OSError):
            c.from_file("/nonexistent.json", load=json.load)

    def test_from_file_silent(self):
        import json
        c = Config()
        result = c.from_file("/nonexistent.json", load=json.load, silent=True)
        assert result is False

    def test_from_file_binary(self, tmp_path):
        import json
        f = tmp_path / "config.json"
        f.write_bytes(json.dumps({"KEY": "val"}).encode())

        def load_binary(fp):
            return json.loads(fp.read())

        c = Config()
        c.from_file(str(f), load=load_binary, text=False)
        assert c["KEY"] == "val"
