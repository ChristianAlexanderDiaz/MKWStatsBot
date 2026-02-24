"""Shared base cog with decorators, helpers, and autocomplete methods."""

import functools
import logging
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from ..constants import MEMBER_STATUSES


# Member status choices - centralized definition
MEMBER_STATUS_CHOICES = [
    app_commands.Choice(name=status.capitalize(), value=status)
    for status in MEMBER_STATUSES
]


def get_member_status_text() -> str:
    """Get formatted member status text for help documentation."""
    return "/".join(choice.name for choice in MEMBER_STATUS_CHOICES)


def require_guild_setup(func):
    """Decorator to ensure guild is initialized before running slash commands."""
    @functools.wraps(func)
    async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
        guild_id = self.get_guild_id_from_interaction(interaction)
        if not self.is_guild_initialized(guild_id):
            await interaction.response.send_message(
                "❌ Guild not set up! Please run `/setup` first to initialize your clan.",
                ephemeral=True
            )
            return
        return await func(self, interaction, *args, **kwargs)
    return wrapper


def require_moderator():
    """Decorator to require user to have Manage Channels, Manage Server, or Administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        perms = interaction.user.guild_permissions
        return perms.administrator or perms.manage_guild or perms.manage_channels
    return app_commands.check(predicate)


def require_admin():
    """Decorator to require user to have Manage Server or Administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        perms = interaction.user.guild_permissions
        return perms.administrator or perms.manage_guild
    return app_commands.check(predicate)


class BaseCog(commands.Cog):
    """Base cog with shared helpers used by all domain cogs."""

    def __init__(self, bot):
        self.bot = bot

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
