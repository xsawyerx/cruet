"""Minimal signal implementation for Cruet."""
import contextlib


class Signal:
    def __init__(self):
        self._receivers = []

    def connect(self, receiver, sender=None):
        self._receivers.append((receiver, sender))

    def disconnect(self, receiver, sender=None):
        self._receivers = [
            (r, s) for r, s in self._receivers if r is not receiver or s is not sender
        ]

    def send(self, sender=None, **kwargs):
        for receiver, expected_sender in list(self._receivers):
            if expected_sender is None or expected_sender is sender:
                receiver(sender, **kwargs)

    @contextlib.contextmanager
    def connected_to(self, receiver, sender=None):
        self.connect(receiver, sender=sender)
        try:
            yield
        finally:
            self.disconnect(receiver, sender=sender)


appcontext_pushed = Signal()
appcontext_popped = Signal()
appcontext_tearing_down = Signal()
request_started = Signal()
request_finished = Signal()
got_request_exception = Signal()
template_rendered = Signal()
before_render_template = Signal()
message_flashed = Signal()

__all__ = [
    "Signal",
    "appcontext_pushed",
    "appcontext_popped",
    "appcontext_tearing_down",
    "request_started",
    "request_finished",
    "got_request_exception",
    "template_rendered",
    "before_render_template",
    "message_flashed",
]
