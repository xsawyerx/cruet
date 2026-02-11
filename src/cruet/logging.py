"""Flask-compatible logging helpers."""
import logging
import sys
import io


class _WSGIErrorsStream:
    def _get_current_object(self):
        from cruet.globals import request
        try:
            return request.environ["wsgi.errors"]
        except (RuntimeError, LookupError, KeyError):
            return sys.stderr

    def write(self, data):
        stream = self._get_current_object()
        if isinstance(stream, (io.BytesIO,)):
            if isinstance(data, str):
                data = data.encode("utf-8")
        return stream.write(data)

    def flush(self):
        return self._get_current_object().flush()


wsgi_errors_stream = _WSGIErrorsStream()

default_handler = logging.StreamHandler(wsgi_errors_stream)
default_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
)


def has_level_handler(logger):
    level = logger.getEffectiveLevel()
    current = logger
    while current:
        if any(handler.level <= level for handler in current.handlers):
            return True
        if not current.propagate:
            break
        current = current.parent
    return False


def create_logger(app):
    logger = logging.getLogger(app.import_name or __name__)
    if app.debug and not logger.level:
        logger.setLevel(logging.DEBUG)
    if not has_level_handler(logger):
        logger.addHandler(default_handler)
    return logger
