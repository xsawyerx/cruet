"""Type stubs for the cruet._cruet C extension module."""

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)


# ---------------------------------------------------------------------------
# Module-level attributes
# ---------------------------------------------------------------------------

__version__: str


def version() -> str:
    """Return the cruet C extension version string."""
    ...


# ---------------------------------------------------------------------------
# URL Routing
# ---------------------------------------------------------------------------

class Rule:
    """A URL rule that maps a URL pattern to an endpoint.

    Equivalent to ``werkzeug.routing.Rule``.
    """

    rule: str
    endpoint: Optional[str]
    methods: frozenset[str]
    strict_slashes: bool

    def __init__(
        self,
        rule: str,
        *,
        endpoint: Optional[str] = None,
        methods: Optional[Sequence[str]] = None,
        strict_slashes: bool = True,
    ) -> None: ...


class MapAdapter:
    """Adapter returned by ``Map.bind()`` for matching and building URLs."""

    def match(
        self,
        path: str,
        method: str = "GET",
    ) -> Tuple[str, Dict[str, Any]]:
        """Match a URL path and method, returning ``(endpoint, values)``.

        Raises ``LookupError`` if no rule matches.
        """
        ...

    def build(
        self,
        endpoint: str,
        values: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build a URL for the given endpoint and values."""
        ...


class Map:
    """A collection of URL rules.

    Equivalent to ``werkzeug.routing.Map``.
    """

    def __init__(self, rules: Optional[Sequence[Rule]] = None) -> None: ...

    def add(self, rule: Rule) -> None:
        """Add a rule to the map."""
        ...

    def bind(
        self,
        server_name: str,
        script_name: str = "",
        url_scheme: str = "http",
    ) -> MapAdapter:
        """Bind the map to a server name and return a ``MapAdapter``."""
        ...


# Built-in converter types registered by default.
converters: Dict[str, Type[Any]]


# ---------------------------------------------------------------------------
# HTTP Headers
# ---------------------------------------------------------------------------

class CHeaders:
    """Fast HTTP headers container (case-insensitive)."""

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a header value by name (case-insensitive)."""
        ...

    def set(self, key: str, value: str) -> None:
        """Set a header value."""
        ...

    def items(self) -> List[Tuple[str, str]]:
        """Return all headers as a list of ``(name, value)`` pairs."""
        ...

    def __getitem__(self, key: str) -> str: ...
    def __setitem__(self, key: str, value: str) -> None: ...
    def __contains__(self, key: object) -> bool: ...
    def __iter__(self) -> Any: ...
    def __len__(self) -> int: ...


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class CRequest:
    """WSGI request wrapper implemented in C.

    Parses the WSGI environ dict and provides fast attribute access.
    """

    method: str
    path: str
    query_string: str
    content_type: str
    content_length: int
    data: bytes
    args: Dict[str, str]
    form: Dict[str, str]
    headers: CHeaders
    host: str
    scheme: str
    url: str

    def __init__(self, environ: Dict[str, Any]) -> None: ...


class CResponse:
    """HTTP response object implemented in C.

    Can be called as a WSGI application.
    """

    status_code: int
    headers: CHeaders
    data: bytes

    def __init__(
        self,
        body: Union[str, bytes] = b"",
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
    ) -> None: ...

    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: Optional[int] = None,
        path: str = "/",
        domain: Optional[str] = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Optional[str] = None,
    ) -> None:
        """Set a cookie on the response."""
        ...

    def delete_cookie(self, key: str, path: str = "/", domain: Optional[str] = None) -> None:
        """Delete a cookie by setting its max_age to 0."""
        ...

    def __call__(
        self,
        environ: Dict[str, Any],
        start_response: Callable[..., Any],
    ) -> List[bytes]:
        """WSGI interface -- call as a WSGI app."""
        ...


# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

def parse_qs(query_string: str) -> Dict[str, str]:
    """Parse a query string into a dict.

    Unlike ``urllib.parse.parse_qs``, values are single strings (last wins).
    """
    ...


def parse_cookies(cookie_header: str) -> Dict[str, str]:
    """Parse a ``Cookie`` header into a dict of name-value pairs."""
    ...


def parse_multipart(
    body: bytes,
    content_type: str,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Parse a multipart/form-data body.

    Returns ``(form_fields, files)`` where *files* values contain
    ``filename``, ``content_type``, and ``data`` keys.
    """
    ...


def parse_http_request(data: bytes) -> Optional[Dict[str, Any]]:
    """Parse raw HTTP request bytes.

    Returns a dict with keys: ``method``, ``path``, ``version``,
    ``query_string``, ``headers``, ``body``, ``keep_alive``.
    Returns ``None`` if the request is incomplete or malformed.
    """
    ...
