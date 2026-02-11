"""cruet — High-performance Flask-compatible web framework with C extensions."""

from cruet._cruet import __version__
from cruet.app import Cruet as Flask
from cruet.app import Cruet
from cruet.config import Config
from cruet.wrappers import Request, Response
from cruet.globals import (
    request, g, current_app, session,
    has_request_context, has_app_context,
    after_this_request,
)
from cruet.ctx import copy_current_request_context
from cruet.blueprints import Blueprint
from cruet.helpers import (
    jsonify, redirect, abort, url_for, make_response,
    send_file, send_from_directory,
    flash, get_flashed_messages,
    stream_with_context,
)
from cruet.templating import (
    render_template, render_template_string,
    stream_template, stream_template_string,
    get_template_attribute,
)
from cruet.json_provider import DefaultJSONProvider
from cruet.signals import (
    appcontext_popped,
    appcontext_pushed,
    appcontext_tearing_down,
    request_started,
    request_finished,
    got_request_exception,
    template_rendered,
    before_render_template,
    message_flashed,
)

__all__ = [
    "__version__",
    "Flask",
    "Cruet",
    "Config",
    "Request",
    "Response",
    "request",
    "g",
    "current_app",
    "session",
    "Blueprint",
    "jsonify",
    "redirect",
    "abort",
    "url_for",
    "make_response",
    "send_file",
    "send_from_directory",
    "flash",
    "get_flashed_messages",
    "stream_with_context",
    "render_template",
    "render_template_string",
    "stream_template",
    "stream_template_string",
    "get_template_attribute",
    "has_request_context",
    "has_app_context",
    "after_this_request",
    "copy_current_request_context",
    "DefaultJSONProvider",
    "appcontext_popped",
    "appcontext_pushed",
    "appcontext_tearing_down",
    "request_started",
    "request_finished",
    "got_request_exception",
    "template_rendered",
    "before_render_template",
    "message_flashed",
]
