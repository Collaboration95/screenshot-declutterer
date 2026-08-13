"""Logging configuration: import-time setup, request correlation IDs, access log.

Issue #85: the app previously only configured logging inside ``__main__``,
so imported contexts (tests, ``flask run``, WSGI servers) had no handlers
and no way to correlate a sequence of API calls to a single user action.

Design: stdlib ``logging`` only (no new deps). A root-level config with a
console handler plus a rotating file handler at ``~/.ss-dcl/app.log``
(override ``SS_DCL_LOG_FILE``). Every record carries ``request_id`` (from a
``ContextVar`` set by the Flask ``before_request`` middleware) via a logging
``Filter``, so all log lines — app, access, and library-level — are
correlatable.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import uuid
from contextvars import ContextVar
from pathlib import Path

DEFAULT_LOG_FILE = str(Path.home() / ".ss-dcl" / "app.log")
DEFAULT_LOG_LEVEL = "INFO"

_configured = False

request_id_var: ContextVar[str] = ContextVar("ss_dcl_request_id", default="")


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def new_request_id() -> str:
    """Generate a fresh correlation id for a request (12 hex chars)."""
    return uuid.uuid4().hex[:12]


def _build_handler(level: int) -> tuple[logging.Handler, ...]:
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    filter_ = RequestIdFilter()
    handlers: list[logging.Handler] = []
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    console.addFilter(filter_)
    handlers.append(console)
    file_path = os.environ.get("SS_DCL_LOG_FILE") or DEFAULT_LOG_FILE
    file_handler = logging.handlers.RotatingFileHandler(
        file_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    file_handler.addFilter(filter_)
    handlers.append(file_handler)
    return tuple(handlers)


def configure_logging(level: str | None = None, force: bool = False) -> None:
    """Configure the root logger with console + rotating file handlers.

    Called at import time by ``ss_dcl.app`` so every entry point (CLI,
    ``flask run``, WSGI, tests) gets the same config. Idempotent unless
    *force* is set; level from ``SS_DCL_LOG_LEVEL`` env var (default INFO).
    """
    global _configured
    if _configured and not force:
        return
    level_name = (level or os.environ.get("SS_DCL_LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper()
    level_value = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level_value)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in _build_handler(level_value):
        root.addHandler(handler)
    _configured = True
