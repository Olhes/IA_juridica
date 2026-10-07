"""Console configuration that keeps application output safe on Windows."""

import sys
import logging


class SafeAccessLog(logging.Filter):
    """Uvicorn's access log must never retain OAuth codes in query strings."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            record.args = ("[client]", method, "[route]", version, status)
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
