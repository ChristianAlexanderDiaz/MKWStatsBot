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

import asyncio
import logging
import os
import sys
import traceback as _traceback_mod
import threading
import time
from typing import Any

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
# Discord Webhook Handler
# ---------------------------------------------------------------------------

_webhook_handler: "DiscordWebhookHandler | None" = None


class _QuietLoggerFilter(logging.Filter):
    """Reject log records from noisy third-party loggers."""

    def __init__(self, prefixes: tuple[str, ...]) -> None:
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(self._prefixes)


class DiscordWebhookHandler(logging.Handler):
    """Forwards WARNING+ log records to a Discord webhook as batched embeds.

    ``emit()`` is synchronous (Python logging requirement) — it appends
    records to a thread-safe queue.  A background asyncio task flushes the
    queue every 5 seconds as a single Discord embed, staying well within
    Discord's webhook rate limit.
    """

    _FLUSH_INTERVAL = 5  # seconds
    _MAX_EMBED_LEN = 4000  # Discord embed description limit (4096), leave margin
    _POST_TIMEOUT = 10  # seconds — total timeout for webhook POST requests

    def __init__(self, webhook_url: str) -> None:
        super().__init__(level=logging.WARNING)
        self._webhook_url = webhook_url
        self._queue: list[logging.LogRecord] = []
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._session: Any = None  # aiohttp.ClientSession, created in start()

        # Filter out noisy third-party loggers
        self.addFilter(_QuietLoggerFilter(tuple(_QUIET_LOGGERS)))

    def emit(self, record: logging.LogRecord) -> None:
        """Thread-safe enqueue (called by Python logging from any thread)."""
        try:
            with self._lock:
                self._queue.append(record)
        except Exception:  # noqa: S110 — never risk recursive logging
            pass

    # ── Async lifecycle (called from bot.py) ──────────────────────────

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the background flush loop.  Called once the event loop is running."""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=self._POST_TIMEOUT)
        self._session = aiohttp.ClientSession(timeout=timeout)
        self._flush_task = loop.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Detach from logger, cancel flush task, deliver remaining records, and close session."""
        # Detach so no new records arrive after final flush
        logging.getLogger().removeHandler(self)
        if self._flush_task:
            self._flush_task.cancel()
            # gather with return_exceptions avoids swallowing CancelledError (SonarCloud S7497)
            await asyncio.gather(self._flush_task, return_exceptions=True)
        # Final flush
        await self._flush_once()
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Internal ──────────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._FLUSH_INTERVAL)
            await self._flush_once()

    @staticmethod
    def _format_record(record: logging.LogRecord) -> str:
        """Format a single log record as a Discord-flavored markdown line."""
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        short_level = _LEVEL_MAP.get(record.levelname, record.levelname[:5])
        msg = record.getMessage()
        if len(msg) > 300:
            msg = msg[:297] + "..."
        line = f"`{ts}` **{short_level}** {msg}"
        if record.exc_info and record.exc_info[1]:
            tb = "".join(_traceback_mod.format_exception(*record.exc_info))
            if len(tb) > 500:
                tb = tb[:497] + "..."
            line += f"\n```\n{tb}\n```"
        return line

    def _build_embed_payload(self, batch: list[logging.LogRecord]) -> dict:
        """Build a Discord embed payload from a batch of log records."""
        level_colors = {"WARNING": 0xFFA500, "ERROR": 0xFF0000, "CRITICAL": 0x8B0000}
        highest_level = logging.WARNING
        lines: list[str] = []
        for record in batch:
            if record.levelno > highest_level:
                highest_level = record.levelno
            lines.append(self._format_record(record))

        description = "\n".join(lines)
        if len(description) > self._MAX_EMBED_LEN:
            description = description[: self._MAX_EMBED_LEN - 3] + "..."

        color = level_colors.get(logging.getLevelName(highest_level), 0xFFA500)
        return {
            "embeds": [{
                "title": f"Bot Log ({len(batch)} record{'s' if len(batch) != 1 else ''})",
                "description": description,
                "color": color,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }]
        }

    async def _handle_post_response(
        self, resp: Any, batch: list[logging.LogRecord],
    ) -> None:
        """Handle the HTTP response from a webhook POST."""
        if resp.status == 429:
            retry_after = (await resp.json()).get("retry_after", 5)
            await asyncio.sleep(retry_after)
            with self._lock:
                self._queue = batch + self._queue
        elif 400 <= resp.status < 500:
            print(
                f"DiscordWebhookHandler: webhook returned {resp.status} "
                f"— check LOG_WEBHOOK_URL (dropped {len(batch)} records)",
                file=sys.stderr,
            )
        elif 500 <= resp.status < 600:
            print(
                f"DiscordWebhookHandler: webhook returned {resp.status} "
                f"— re-queuing {len(batch)} records for retry",
                file=sys.stderr,
            )
            with self._lock:
                self._queue = batch + self._queue

    async def _flush_once(self) -> None:
        with self._lock:
            batch, self._queue = self._queue, []
        if not batch or not self._session:
            return

        payload = self._build_embed_payload(batch)
        try:
            async with self._session.post(self._webhook_url, json=payload) as resp:
                await self._handle_post_response(resp, batch)
        except Exception as exc:
            print(
                f"DiscordWebhookHandler flush error: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_webhook_handler() -> "DiscordWebhookHandler | None":
    """Return the active webhook handler (if any), for lifecycle management."""
    return _webhook_handler


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

    # Discord webhook handler (if configured)
    global _webhook_handler
    webhook_url = os.getenv("LOG_WEBHOOK_URL")
    if webhook_url:
        _webhook_handler = DiscordWebhookHandler(webhook_url)
        root.addHandler(_webhook_handler)

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a module (use __name__)."""
    return logging.getLogger(name)
