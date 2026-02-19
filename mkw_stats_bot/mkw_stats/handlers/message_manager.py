"""Message lifecycle management: auto-delete, countdown timers, cleanup."""

import asyncio
import discord
from ..logging_config import get_logger

logger = get_logger(__name__)


class MessageManager:
    """Handles message deletion, countdown timers, and auto-cleanup."""

    def __init__(self, bot):
        self.bot = bot

    async def auto_delete(self, message: discord.Message, delay_seconds: int):
        """Auto-delete a message after the specified delay."""
        await asyncio.sleep(delay_seconds)
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass
        except discord.errors.Forbidden:
            pass

    async def countdown_and_delete_message(
        self,
        message: discord.Message,
        embed: discord.Embed,
        countdown_seconds: int = 30,
    ):
        """Show countdown timer and delete message (for regular discord messages)."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:
                try:
                    await message.edit(embed=embed, content=f"Disappearing in {remaining} seconds...")
                except:
                    pass

        try:
            await message.delete()
        except:
            pass

    async def countdown_and_delete_interaction(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        countdown_seconds: int = 30,
    ):
        """Show countdown timer and delete interaction response (for slash command responses)."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:
                try:
                    await interaction.edit_original_response(
                        embed=embed,
                        content=f"Disappearing in {remaining} seconds...",
                    )
                except:
                    pass

        try:
            await interaction.delete_original_response()
        except:
            pass
