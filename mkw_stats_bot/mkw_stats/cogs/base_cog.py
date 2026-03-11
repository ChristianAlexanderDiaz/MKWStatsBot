"""Shared base cog with decorators, helpers, and autocomplete methods."""

import functools
import logging
import time
from collections.abc import Callable, Coroutine
from typing import (
    Any,
    cast,
    overload,
)

from ..logging_config import LogBlock

import discord
from discord import app_commands
from discord.ext import commands

try:
    from typing import ParamSpec, TypeVar
except ImportError:
    from typing_extensions import ParamSpec, TypeVar  # type: ignore[assignment]

from ..constants import MEMBER_STATUSES

P = ParamSpec("P")
R = TypeVar("R")


# Member status choices - centralized definition
MEMBER_STATUS_CHOICES = [
    app_commands.Choice(name=status.capitalize(), value=status)
    for status in MEMBER_STATUSES
]


def get_member_status_text() -> str:
    """Get formatted member status text for help documentation."""
    return "/".join(choice.name for choice in MEMBER_STATUS_CHOICES)


@overload
def require_guild_setup(
    func: Callable[..., Coroutine[Any, Any, R]],
) -> Callable[..., Coroutine[Any, Any, R]]: ...


@overload
def require_guild_setup(
    func: None = None,
    *,
    defer: bool = ...,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, R]]],
    Callable[P, Coroutine[Any, Any, R]],
]: ...


def require_guild_setup(
    func: Callable[P, Coroutine[Any, Any, R]] | None = None,
    *,
    defer: bool = False,
) -> Callable[..., Coroutine[Any, Any, R]] | Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Decorator to ensure guild is initialized before running slash commands.

    Usage:
        @require_guild_setup              # no defer (light commands)
        @require_guild_setup(defer=True)  # defer first (heavy DB commands)

    When defer=True, calls interaction.response.defer() before the guild-check
    DB call so the 3-second Discord deadline is always met. All responses in
    deferred commands must use followup.send() instead of response.send_message().
    """

    def decorator(
        fn: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(fn)
        async def wrapper(
            self, interaction: discord.Interaction, *args: P.args, **kwargs: P.kwargs
        ) -> R:
            cmd_name = fn.__name__.removesuffix("_slash")
            user_name = getattr(interaction.user, "display_name", None) or getattr(interaction.user, "name", "Unknown")
            guild_name = interaction.guild.name if interaction.guild else "DM"

            # Format slash-command parameters for the log header
            param_parts: list[str] = []
            for key, val in kwargs.items():
                s = str(val)
                if len(s) > 30:
                    s = s[:27] + "..."
                param_parts.append(f'{key}="{s}"')
            param_str = " ".join(param_parts)
            if param_str:
                param_str = " " + param_str

            interaction_age = time.time() - interaction.created_at.timestamp()
            guild_id = self.get_guild_id_from_interaction(interaction)
            logging.debug(
                "/%s: DIAG handler_start age=%.2fs guild_id=%s guild=%s",
                cmd_name, interaction_age, guild_id, guild_name,
            )

            if defer:
                try:
                    t0 = time.monotonic()
                    await interaction.response.defer()
                    defer_ms = (time.monotonic() - t0) * 1000
                    logging.debug("/%s: DIAG defer_ok %.0fms", cmd_name, defer_ms)
                except discord.errors.NotFound:
                    defer_ms = (time.monotonic() - t0) * 1000
                    logging.warning(
                        "/%s: DIAG defer_EXPIRED age=%.2fs defer_took=%.0fms",
                        cmd_name, interaction_age, defer_ms,
                    )
                    try:
                        if interaction.channel is not None:
                            await interaction.channel.send(
                                f"{interaction.user.mention} Your `/{cmd_name}` didn't go through "
                                f"— the bot was briefly unresponsive. Please try again.",
                                delete_after=10,
                            )
                        else:
                            logging.debug(f"/{cmd_name}: no channel available for fallback, attempting DM")
                            try:
                                await interaction.user.send(
                                    f"Your `/{cmd_name}` didn't go through "
                                    f"— the bot was briefly unresponsive. Please try again.",
                                )
                            except Exception as dm_err:
                                logging.debug(f"/{cmd_name}: DM fallback also failed: {dm_err}")
                    except Exception as fallback_err:
                        logging.debug(f"/{cmd_name}: could not send fallback message to channel: {fallback_err}")
                    return  # type: ignore[return-value]

            try:
                t0 = time.monotonic()
                initialized = await self.is_guild_initialized(guild_id)
                check_ms = (time.monotonic() - t0) * 1000
                logging.debug(
                    "/%s: DIAG guild_check guild_id=%s result=%s took=%.0fms",
                    cmd_name, guild_id, initialized, check_ms,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "DB error during guild init check for guild %s", guild_id
                )
                msg = "❌ Database temporarily unavailable, please try again in a moment."
                if defer:
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return  # type: ignore[return-value]

            if not initialized:
                logging.warning(
                    "/%s: DIAG guild_NOT_initialized guild_id=%s — sending 'not set up' to user",
                    cmd_name, guild_id,
                )
                msg = "❌ Guild not set up! Please run `/setup` first to initialize your clan."
                if defer:
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return  # type: ignore[return-value]

            async with LogBlock(f"/{cmd_name}{param_str} [{user_name} · {guild_name}]"):
                return await fn(self, interaction, *args, **kwargs)  # type: ignore[return-value]

        return wrapper  # type: ignore[return-value]

    if func is not None:
        # Called as @require_guild_setup (no parentheses)
        return decorator(func)
    # Called as @require_guild_setup(defer=True)
    return decorator


def require_moderator():
    """Decorator to require user to have Manage Channels, Manage Server, or Administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        member = cast(discord.Member, interaction.user)
        perms = member.guild_permissions
        return perms.administrator or perms.manage_guild or perms.manage_channels
    return app_commands.check(predicate)


def require_admin():
    """Decorator to require user to have Manage Server or Administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        member = cast(discord.Member, interaction.user)
        perms = member.guild_permissions
        return perms.administrator or perms.manage_guild
    return app_commands.check(predicate)


class BaseCog(commands.Cog):
    """Base cog with shared helpers used by all domain cogs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    def get_guild_id(self, ctx_or_interaction: "commands.Context | discord.Interaction") -> int:
        """Helper method to get guild ID from context or interaction."""
        if hasattr(ctx_or_interaction, 'guild') and ctx_or_interaction.guild:
            return ctx_or_interaction.guild.id
        return 0

    def get_guild_id_from_interaction(self, interaction: discord.Interaction) -> int:
        """Get guild ID from interaction."""
        return interaction.guild.id if interaction.guild else 0

    # Intentionally class-level: shared singleton cache across all cog instances
    # guild_id -> (result, expiry_timestamp)
    _guild_init_cache: dict[int, tuple[bool, float]] = {}
    _POSITIVE_TTL = 300  # 5 min — guild init status rarely changes
    _NEGATIVE_TTL = 10   # 10 sec — so /setup takes effect quickly

    async def is_guild_initialized(self, guild_id: int) -> bool:
        """Check if guild is properly initialized (async).

        Uses a simple TTL cache to reduce pool pressure.  On DB error, returns
        a cached value if one exists; otherwise re-raises so the caller can
        show an appropriate message.
        """
        now = time.monotonic()
        cached = self._guild_init_cache.get(guild_id)
        if cached is not None:
            value, expiry = cached
            if now < expiry:
                return value

        try:
            async with self.bot.db.get_connection() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM guild_configs WHERE guild_id = $1 AND is_active = TRUE",
                    guild_id,
                )
                result = count > 0
                if not result:
                    logging.getLogger(__name__).warning(
                        "Guild %s failed init check: query returned count=%s (cache_had=%s)",
                        guild_id, count, cached[0] if cached else "no_cache"
                    )
        except Exception:
            # Return stale True to avoid false "not set up" errors,
            # but never stale False — re-raise so caller shows "DB unavailable"
            if cached is not None and cached[0] is True:
                logging.getLogger(__name__).warning(
                    "DB error during guild init check for guild %s; "
                    "returning stale cached True (expired %.0fs ago)",
                    guild_id,
                    now - cached[1],
                )
                return True
            raise

        ttl = self._POSITIVE_TTL if result else self._NEGATIVE_TTL
        self._guild_init_cache[guild_id] = (result, now + ttl)
        return result

    @classmethod
    def invalidate_guild_cache(cls, guild_id: int) -> None:
        """Remove a guild's cached initialization status."""
        cls._guild_init_cache.pop(guild_id, None)

    def _format_error_for_user(self, error: Exception, context: str = "") -> str:
        """Convert exception to user-friendly message with technical details."""
        error_type = type(error).__name__
        error_msg = str(error)

        if len(error_msg) > 150:
            error_msg = error_msg[:150] + "..."

        if context:
            return f"❌ {context}: {error_type} - {error_msg}"
        else:
            return f"❌ {error_type}: {error_msg}"
