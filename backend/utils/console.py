"""Console configuration that keeps application output safe on Windows."""

import logging
import re
import sys

_MAX_RAW_ROUTE_SCAN = 1024
_MAX_ROUTE_LENGTH = 120
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_LOCAL_SESSION_RE = re.compile(r"(^|/)local-session/.*", re.IGNORECASE)
_UNSAFE_PATH_CHARS_RE = re.compile(r"[^A-Za-z0-9/._:{}-]")
_SAFE_METHOD_RE = re.compile(r"^[A-Z0-9_-]{1,16}$")
_SAFE_VERSION_RE = re.compile(r"^[0-9.]{1,8}$")


def sanitize_access_path(path: object) -> str:
    """Return a log-safe URL path without query strings, control chars, or IDs."""
    if not isinstance(path, str) or not path:
        return "[route]"
    route = path.split("?", 1)[0].split("#", 1)[0][:_MAX_RAW_ROUTE_SCAN]
    route = _CONTROL_CHARS_RE.sub("", route)
    if not route or not route.startswith("/"):
        return "[route]"
    route = _LOCAL_SESSION_RE.sub(r"\1local-session/{redacted}", route)
    route = _UUID_RE.sub("{id}", route)
    route = _UNSAFE_PATH_CHARS_RE.sub("_", route)
    if len(route) > _MAX_ROUTE_LENGTH:
        route = f"{route[:_MAX_ROUTE_LENGTH]}..."
    return route


def _sanitize_token(value: object, pattern: re.Pattern[str], fallback: str) -> str:
    if isinstance(value, str) and pattern.fullmatch(value):
        return value
    return fallback


class SafeAccessLog(logging.Filter):
    """Uvicorn access log filter: masks client IPs, query strings, and sensitive IDs."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            _client, method, path, version, status = record.args
            if not isinstance(status, int) or isinstance(status, bool):
                return False
            record.args = (
                "[client]",
                _sanitize_token(method, _SAFE_METHOD_RE, "[method]"),
                sanitize_access_path(path),
                _sanitize_token(version, _SAFE_VERSION_RE, "[version]"),
                status,
            )
        else:
            return False
        return True


def configure_console_output() -> None:
    """Keep unsupported console characters from interrupting flows."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SafeAccessLog) for f in access.filters):
        access.addFilter(SafeAccessLog())
    for name in ("httpx", "httpcore", "httpx2", "cohere", "googletrans"):
        sdk_logger = logging.getLogger(name)
        sdk_logger.handlers = [logging.NullHandler()]
        sdk_logger.propagate = False
        sdk_logger.setLevel(logging.WARNING)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError):
                pass
