"""Structured logging with a hard rule: chunk text never enters a log record."""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

FORBIDDEN_KEYS = {"text_content", "text", "chunk_text", "context", "answer"}


def _strip_content(_logger: Any, _name: str, event: dict) -> dict:
    """Drop payload text if a caller passes it by habit.

    A leak into logs is a leak. This processor makes the safe thing the default
    rather than relying on every call site to remember.
    """
    for key in list(event):
        if key in FORBIDDEN_KEYS:
            value = event.pop(key)
            event[f"{key}_len"] = len(value) if isinstance(value, str) else None
    return event


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _strip_content,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
