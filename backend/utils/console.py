"""Console configuration that keeps application output safe on Windows."""

import sys


def configure_console_output() -> None:
    """Keep unsupported console characters from interrupting flows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError):
                pass
