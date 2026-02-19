"""Confirmation flow management: accept, reject, edit, timeout, cleanup."""

import asyncio
import discord
from typing import Dict
from ..logging_config import get_logger

logger = get_logger(__name__)


class ConfirmationManager:
    """Manages pending confirmations for OCR and bulk scan flows.

    The pending_confirmations and timeout_tasks dicts live on the bot instance
    (since commands.py accesses them directly). This class provides methods
    that operate on those dicts.
    """

    def __init__(self, bot):
        self.bot = bot

    async def handle_reaction(self, reaction, user):
        """Route reaction events to the appropriate handler."""
        if user == self.bot.user:
            return

        message_id = str(reaction.message.id)

        if message_id not in self.bot.pending_confirmations:
            return

        confirmation_data = self.bot.pending_confirmations[message_id]

        if user.id != confirmation_data['user_id']:
            return

        if str(reaction.emoji) == "\u2705":
            await self.handle_accept(reaction.message, confirmation_data)
        elif str(reaction.emoji) == "\u274c":
            await self.handle_reject(reaction.message, confirmation_data)
        elif str(reaction.emoji) == "\u270f\ufe0f":
            await self.handle_edit(reaction.message, confirmation_data)

    async def handle_accept(self, message: discord.Message, confirmation_data: Dict):
        """Handle accepted confirmation - routes to appropriate handler."""
        try:
            confirmation_type = confirmation_data.get('type', 'standard')

            if confirmation_type == 'bulk_scan_confirmation':
                await self.bot.bulk_scan_handler.handle_processing(message, confirmation_data)
                return

            if confirmation_type == 'bulk_results_confirmation':
                await self.bot.bulk_scan_handler.handle_results_save(message, confirmation_data)
                return

            results = confirmation_data['results']

            if confirmation_type == 'ocr_war_submission':
                await self.bot.ocr_handler.handle_war_submission(message, confirmation_data)
                return

            # Standard race results handling
            for result in results:
                result['message_id'] = confirmation_data['original_message_id']

            guild_id = message.guild.id if message.guild else None
            if not guild_id:
                logger.error("Cannot save race results: guild_id is None")
                await message.channel.send("\u274c **Error:** Could not determine guild ID.")
                return

            success = self.bot.db.add_race_results(results, guild_id=guild_id)

            if success:
                embed = discord.Embed(
                    title="\u2705 Results Saved Successfully!",
                    description=f"Saved results for {len(results)} clan members.",
                    color=0x00ff00,
                )

                results_text = ""
                for result in results:
                    results_text += f"**{result['name']}**: {result['score']}\n"

                embed.add_field(name="Saved Results", value=results_text, inline=False)
                embed.set_footer(text="Results have been added to the database and averages updated.")
            else:
                embed = discord.Embed(
                    title="\u274c Database Error",
                    description="Failed to save results to database. Please try again.",
                    color=0xff0000,
                )

            await message.edit(embed=embed)
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass

            self.cleanup(str(message.id))
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed))

        except Exception as e:
            logger.error(f"Error handling confirmation accept: {e}")
            embed = discord.Embed(
                title="\u274c Error",
                description=f"An error occurred while saving results: {str(e)}",
                color=0xff0000,
            )
            await message.edit(embed=embed)
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed))

    async def handle_reject(self, message: discord.Message, confirmation_data: Dict):
        """Handle rejected confirmation."""
        if 'original_message_obj' in confirmation_data:
            try:
                await confirmation_data['original_message_obj'].add_reaction("\u274c")
            except discord.errors.NotFound:
                logger.debug("Skipping reaction for deleted message")
            except Exception as e:
                logger.warning(f"Failed to add reaction to original message: {e}")

        embed = discord.Embed(
            title="\u274c Results Cancelled",
            description="Results were not saved to the database.\n\n\U0001f4a1 **Found an issue with OCR detection?**\nYou can report it below to help improve accuracy.",
            color=0xff6600,
        )

        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:
            pass

        # Create a report view for the rejection message
        from ..bot import ReportIssueView

        class TempOCRView:
            def __init__(self, conf_data):
                self.guild_id = conf_data.get('guild_id')
                self.user_id = conf_data.get('user_id')
                self.original_message_obj = conf_data.get('original_message_obj')
                self.results = conf_data.get('results', [])
                self.bot = None

        temp_view = TempOCRView(confirmation_data)
        temp_view.bot = self.bot

        report_view = ReportIssueView(temp_view)
        report_view.message = message

        await message.edit(embed=embed, view=report_view)
        self.cleanup(str(message.id))

    async def handle_edit(self, message: discord.Message, confirmation_data: Dict):
        """Handle manual edit request."""
        results = confirmation_data['results']

        embed = discord.Embed(
            title="\u270f\ufe0f Manual Edit Mode",
            description="Edit the results below using the commands:",
            color=0x9932cc,
        )

        current_results = ""
        for i, result in enumerate(results, 1):
            current_results += f"{i}. **{result['name']}**: {result['score']}\n"

        embed.add_field(
            name="\U0001f4ca Current Results",
            value=current_results or "No results",
            inline=False,
        )

        embed.add_field(
            name="\U0001f527 Edit Commands",
            value="Manual editing is no longer supported.\nUse `/addwar` command to add war results manually.",
            inline=False,
        )

        embed.set_footer(text="Use /addwar command for manual entry instead")

        await message.edit(embed=embed)
        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:
            pass

        edit_session_data = {
            'results': confirmation_data['results'].copy(),
            'original_message_id': confirmation_data['original_message_id'],
            'user_id': confirmation_data['user_id'],
            'channel_id': confirmation_data['channel_id'],
            'edit_message_id': str(message.id),
        }

        if not hasattr(self.bot, 'edit_sessions'):
            self.bot.edit_sessions = {}
        self.bot.edit_sessions[confirmation_data['user_id']] = edit_session_data

        self.cleanup(str(message.id))

    async def handle_timeout(self, message: discord.Message):
        """Handle confirmation timeout."""
        embed = discord.Embed(
            title="\u23f0 Confirmation Expired",
            description="Results were not saved due to timeout.",
            color=0x999999,
        )
        await message.edit(embed=embed)
        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:
            pass

        self.cleanup(str(message.id))

    def cleanup(self, message_id: str):
        """Clean up confirmation data and cancel any associated timeout tasks."""
        if message_id in self.bot.pending_confirmations:
            del self.bot.pending_confirmations[message_id]

        if message_id in self.bot.timeout_tasks:
            task = self.bot.timeout_tasks[message_id]
            if not task.done():
                task.cancel()
            del self.bot.timeout_tasks[message_id]
