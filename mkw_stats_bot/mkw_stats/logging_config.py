#!/usr/bin/env python3
"""Centralized logging configuration for MKW Stats Bot.

Railway / container logging principles:
- stdout only  (Railway captures stdout; file handlers waste ephemeral disk)
- Single line per event  (multi-line SQL errors are truncated to the first line)
- No ANSI colors on Railway  (auto-detected via sys.stdout.isatty())
- Named loggers everywhere  (not root — tells you *where* the log came from)
- Third-party noise suppressed  (paddle, PIL, urllib3, etc. silenced to WARNING)
- LogBlock context manager wraps each event (command, OCR scan, etc.) in
  bordered blocks so Railway's log stream is scannable at a glance.
"""

import logging
import os
import sys
import time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BORDER_WIDTH = 62

_LEVEL_MAP: dict[str, str] = {
    "DEBUG":    "DEBUG",
    "INFO":     "INFO ",
    "WARNING":  "WARN ",
    "ERROR":    "ERROR",
    "CRITICAL": "CRIT ",
}

_USE_COLOR: bool = sys.stdout.isatty()

_ANSI: dict[str, str] = {
    "DEBUG": "\033[36m",   # Cyan
    "INFO ": "\033[32m",   # Green
    "WARN ": "\033[33m",   # Yellow
    "ERROR": "\033[31m",   # Red
    "CRIT ": "\033[41m",   # Red background
    "RESET": "\033[0m",
}

# Third-party loggers that produce too much noise at INFO
_QUIET_LOGGERS = [
    "paddle",
    "ppocr",
    "PIL",
    "urllib3",
    "aiohttp.access",
    "discord.http",
]


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

class _Formatter(logging.Formatter):
    """Single-line formatter with short level labels and optional ANSI color."""

    def format(self, record: logging.LogRecord) -> str:
        # Remap level names to fixed 5-char labels
        original_levelname = record.levelname
        short = _LEVEL_MAP.get(record.levelname, record.levelname[:5].ljust(5))

        if _USE_COLOR:
            color = _ANSI.get(short, "")
            record.levelname = f"{color}{short}{_ANSI['RESET']}"
        else:
            record.levelname = short

        result = super().format(record)
        record.levelname = original_levelname  # Restore for other handlers
        return result

    def formatMessage(self, record: logging.LogRecord) -> str:
        # Truncate multi-line messages to the first line.
        # This removes the "LINE N: ..." SQL context that psycopg2 appends.
        original_message = getattr(record, "message", None)
        try:
            if original_message and "\n" in original_message:
                record.message = original_message.split("\n")[0].strip()
            return super().formatMessage(record)
        finally:
            record.message = original_message


# ---------------------------------------------------------------------------
# LogBlock
# ---------------------------------------------------------------------------

class LogBlock:
    """Context manager that wraps a group of log lines in a bordered block.

    Usage (sync or async):
        with LogBlock("/addwar [Cynical · YourClan]"):
            ...

        async with LogBlock("OCR AUTO-SCAN [#results · YourClan]"):
            ...

    Produces:
        HH:MM:SS | INFO  | ── /addwar [Cynical · YourClan] ──────────────
        HH:MM:SS | INFO  | War #1 saved — stats updated for 1 player
        HH:MM:SS | INFO  | ──────────────────────────────────────────────  (241ms)
    """

    def __init__(self, title: str, logger: logging.Logger | None = None) -> None:
        self.title = title
        self._logger = logger or logging.getLogger("mkw_stats")
        self._start: float | None = None

    def _header(self) -> str:
        inner = f" {self.title} "
        dashes = "─" * max(0, BORDER_WIDTH - len(inner) - 3)
        return f"──{inner}" + dashes

    def _footer(self, elapsed_ms: float) -> str:
        return "─" * BORDER_WIDTH + f"  ({elapsed_ms:.0f}ms)"

    def __enter__(self) -> "LogBlock":
        self._start = time.monotonic()
        self._logger.info(self._header())
        return self

    def __exit__(self, *_: object) -> bool:
        elapsed_ms = (time.monotonic() - (self._start or 0)) * 1000
        self._logger.info(self._footer(elapsed_ms))
        return False  # Never suppress exceptions

    async def __aenter__(self) -> "LogBlock":
        return self.__enter__()

    async def __aexit__(self, *args: object) -> bool:
        return self.__exit__(*args)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(log_level: str | None = None) -> logging.Logger:
    """Configure the root logger: stdout only, auto-color, suppress third-party noise.

    Call once at startup (bot.py already does this).
    """
    level_name = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        _Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)

    # Silence noisy third-party libraries
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a module (use __name__)."""
    return logging.getLogger(name)
