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
import threading
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
# LogBlock  (deferred header + empty-block collapse)
# ---------------------------------------------------------------------------

# Thread-local stack of active blocks so the filter can find the current one.
_local = threading.local()


def _active_blocks() -> list["LogBlock"]:
    """Return the per-thread block stack (lazily created)."""
    if not hasattr(_local, "blocks"):
        _local.blocks: list[LogBlock] = []
    return _local.blocks


class _LogBlockFilter(logging.Filter):
    """Intercepts log records on the stdout handler.

    When a LogBlock is active and its header hasn't been emitted yet, this
    filter emits the header *before* the first real log line inside the block.
    A recursion guard prevents the header emission from re-triggering itself.
    """

    def __init__(self) -> None:
        super().__init__()
        self._emitting_header = threading.local()

    def filter(self, record: logging.LogRecord) -> bool:
        # Recursion guard — don't intercept while we're emitting a header
        if getattr(self._emitting_header, "active", False):
            return True

        stack = _active_blocks()
        if not stack:
            return True

        block = stack[-1]
        if not block._header_emitted:
            block._header_emitted = True
            self._emitting_header.active = True
            try:
                block._logger.info(block._header())
            finally:
                self._emitting_header.active = False

        return True


class LogBlock:
    """Context manager that wraps a group of log lines in a bordered block.

    The header is *deferred* — it only appears when the first real log line
    is emitted inside the block.  If the block produces no log output the
    header and footer collapse into a compact one-liner:

        HH:MM:SS | INFO  | ── /wars [Cynical · BOT] (214ms)

    Blocks that do produce output look like before:

        HH:MM:SS | INFO  | ── /addwar player_scores="…" [Cynical · BOT] ──────
        HH:MM:SS | INFO  | Player resolution: 'Cynical' -> Cynical
        HH:MM:SS | INFO  | ──────────────────────────────────────────────  (292ms)
    """

    def __init__(self, title: str, logger: logging.Logger | None = None) -> None:
        self.title = title
        self._logger = logger or logging.getLogger("mkw_stats")
        self._start: float | None = None
        self._header_emitted: bool = False

    def _header(self) -> str:
        inner = f" {self.title} "
        dashes = "─" * max(0, BORDER_WIDTH - len(inner) - 3)
        return f"──{inner}" + dashes

    def _footer(self, elapsed_ms: float) -> str:
        return "─" * BORDER_WIDTH + f"  ({elapsed_ms:.0f}ms)"

    def _oneliner(self, elapsed_ms: float) -> str:
        return f"── {self.title} ({elapsed_ms:.0f}ms)"

    def __enter__(self) -> "LogBlock":
        self._start = time.monotonic()
        self._header_emitted = False
        _active_blocks().append(self)
        return self

    def __exit__(self, *_: object) -> bool:
        stack = _active_blocks()
        # Locate and remove self from the stack.  Normally we're on top,
        # but out-of-order exits (e.g. exceptions) could leave us deeper.
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] is self:
                if i != len(stack) - 1:
                    self._logger.warning(
                        "LogBlock %r exited out of order (index %d of %d)",
                        self.title, i, len(stack),
                    )
                stack.pop(i)
                break

        elapsed_ms = (time.monotonic() - (self._start or 0)) * 1000
        if self._header_emitted:
            self._logger.info(self._footer(elapsed_ms))
        else:
            # No log output inside the block — collapse to one line
            self._logger.info(self._oneliner(elapsed_ms))
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
    handler.addFilter(_LogBlockFilter())
    root.addHandler(handler)

    # Silence noisy third-party libraries
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a module (use __name__)."""
    return logging.getLogger(name)
