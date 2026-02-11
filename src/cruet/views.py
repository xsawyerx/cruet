"""Class-based views compatible with Flask's flask.views."""
from functools import update_wrapper
from werkzeug.exceptions import MethodNotAllowed


class View:
    methods = None
    decorators = []
    init_every_request = True

    @classmethod
    def as_view(cls, name, *class_args, **class_kwargs):
        _instance = None
        _instance_class = None

        def view(*args, **kwargs):
            nonlocal _instance, _instance_class
            view_class = view.view_class
            if view_class.init_every_request:
                self = view_class(*class_args, **class_kwargs)
                return self.dispatch_request(*args, **kwargs)
            if _instance is None or _instance_class is not view_class:
                _instance = view_class(*class_args, **class_kwargs)
                _instance_class = view_class
            return _instance.dispatch_request(*args, **kwargs)

        if cls.decorators:
            for decorator in cls.decorators:
                view = decorator(view)

        view.view_class = cls
        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        if cls.methods is not None:
            view.methods = cls.methods
        if getattr(cls, "provide_automatic_options", None) is not None:
            view.provide_automatic_options = cls.provide_automatic_options
        update_wrapper(view, cls, updated=())
        view.__name__ = name
        view.__qualname__ = name
        return view

    def dispatch_request(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError()


class MethodView(View):
    methods = None

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "methods" in cls.__dict__ and cls.__dict__["methods"] is not None:
            cls.methods = set(m.upper() for m in cls.__dict__["methods"])
            return
        methods = set()
        for base in cls.__mro__:
            for name in ("get", "post", "put", "delete", "patch", "options", "head", "trace", "propfind"):
                if name in base.__dict__:
                    methods.add(name.upper())
        if methods:
            cls.methods = methods

    def dispatch_request(self, *args, **kwargs):
        from cruet.globals import request
        method = request.method.lower()
        view = getattr(self, method, None)
        if view is None and method == "head":
            view = getattr(self, "get", None)
        if view is None:
            raise MethodNotAllowed()
        return view(*args, **kwargs)
