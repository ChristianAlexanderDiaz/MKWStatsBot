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
            start = time.monotonic()
            cmd_name = fn.__name__
            if defer:
                try:
                    await interaction.response.defer()
                except discord.errors.NotFound:
                    logging.warning(f"/{cmd_name}: interaction expired before defer()")
                    return  # type: ignore[return-value]
            guild_id = self.get_guild_id_from_interaction(interaction)
            if not self.is_guild_initialized(guild_id):
                msg = "❌ Guild not set up! Please run `/setup` first to initialize your clan."
                if defer:
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return  # type: ignore[return-value]
            setup_ms = (time.monotonic() - start) * 1000
            result = await fn(self, interaction, *args, **kwargs)
            total_ms = (time.monotonic() - start) * 1000
            deferred_tag = " [deferred]" if defer else ""
            logging.info(
                f"⏱️ /{cmd_name}: guild_check={setup_ms:.0f}ms "
                f"total={total_ms:.0f}ms{deferred_tag}"
            )
            return result

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

    def get_guild_id(self, ctx_or_interaction) -> int:
        """Helper method to get guild ID from context or interaction."""
        if hasattr(ctx_or_interaction, 'guild') and ctx_or_interaction.guild:
            return ctx_or_interaction.guild.id
        return 0

    def get_guild_id_from_interaction(self, interaction: discord.Interaction) -> int:
        """Get guild ID from interaction."""
        return interaction.guild.id if interaction.guild else 0

    def is_guild_initialized(self, guild_id: int) -> bool:
        """Check if guild is properly initialized."""
        try:
            with self.bot.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM guild_configs WHERE guild_id = %s AND is_active = TRUE", (guild_id,))
                return cursor.fetchone()[0] > 0
        except Exception:
            return False

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
