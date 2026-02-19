"""OCR processing handler: image scanning, war submission, and reporting."""

import asyncio
import os
import tempfile
import discord
from typing import Optional, Dict, List, Tuple, Union

from .. import config
from ..logging_config import get_logger

logger = get_logger(__name__)


class OCRHandler:
    """Handles all OCR-related processing flows.

    Responsible for:
    - Shared OCR image processing (auto-scan + manual scan)
    - Automatic race results image processing from channel messages
    - War submission from interactive view and reaction-based flows
    - OCR issue reporting to admin
    - Enhanced confirmation formatting
    """

    def __init__(self, bot):
        self.bot = bot

    async def process_image(
        self, temp_path: str, guild_id: int, filename: str, original_message
    ) -> Tuple[bool, discord.Embed, Optional[List[Dict]]]:
        """Shared OCR processing logic for both automatic and manual scanning.

        Returns:
            Tuple of (success, embed, processed_results)
        """
        try:
            ocr = self.bot.ocr

            ocr_result = ocr.perform_ocr_on_file(temp_path)

            if not ocr_result["success"]:
                embed = discord.Embed(
                    title="\u274c OCR Failed",
                    description=f"OCR processing failed: {ocr_result.get('error', 'Unknown error')}",
                    color=0xff4444,
                )
                return False, embed, None

            if not ocr_result["text"].strip():
                embed = discord.Embed(
                    title="\u274c No Text Detected",
                    description="OCR completed, but no text was detected in the image.",
                    color=0xff4444,
                )
                return False, embed, None

            extracted_texts = [{'text': ocr_result["text"], 'confidence': 0.9}]
            processed_results = ocr._parse_mario_kart_results(extracted_texts, guild_id)

            if processed_results:
                embed = discord.Embed(
                    title="\U0001f3c1 Mario Kart Results Detected",
                    description=f"Found {len(processed_results)} players in {filename}",
                    color=0x00ff00,
                )

                players_text = "\n".join([
                    f"\u2022 {result['name']}"
                    + (f" ({result.get('races', 12)})" if result.get('races', 12) != 12 else "")
                    + f": {result['score']} points"
                    for result in processed_results
                ])

                embed.add_field(name="\U0001f4ca Detected Players", value=players_text, inline=False)
                embed.add_field(
                    name="\u2753 Confirmation Required",
                    value="React with \u2705 to save these results or \u274c to cancel.",
                    inline=False,
                )
                embed.set_footer(text="This confirmation expires in 60 seconds")

                return True, embed, processed_results
            else:
                embed = discord.Embed(
                    title="\u274c No Results Found",
                    description=f"No clan members detected in {filename}",
                    color=0xff4444,
                )
                embed.add_field(
                    name="Try:",
                    value="\u2022 Make sure the image shows a clear results table\n\u2022 Check that player names match your roster\n\u2022 Use `/addwar` for manual entry",
                    inline=False,
                )
                return False, embed, None

        except Exception as e:
            logger.error(f"Error in shared OCR processing: {e}")
            embed = discord.Embed(
                title="\u274c Processing Error",
                description=f"An error occurred while processing the image: {str(e)}",
                color=0xff4444,
            )
            return False, embed, None

    async def process_race_results(self, message: discord.Message, attachment: discord.Attachment):
        """Process an image attachment for Mario Kart race results using shared OCR logic."""
        try:
            processing_msg = await message.channel.send("\U0001f50d Processing race results image...")

            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                    await attachment.save(temp_file.name)
                    temp_file_path = temp_file.name

                guild_id = message.guild.id if message.guild else None
                if not guild_id:
                    await processing_msg.edit(content="\u274c **Error:** Could not determine guild ID.")
                    return

                configured_channel_id = self.bot.db.get_ocr_channel(guild_id)
                if not configured_channel_id:
                    embed = discord.Embed(
                        title="\u274c No OCR Channel Set",
                        description="You need to configure an OCR channel before automatic image scanning will work.",
                        color=0xff4444,
                    )
                    embed.add_field(
                        name="\U0001f527 Setup Required",
                        value="Use `/setchannel #your-channel` to enable automatic OCR processing in that channel.",
                        inline=False,
                    )
                    embed.add_field(
                        name="\U0001f4d6 How it works",
                        value="\u2022 Run `/setchannel #results` to set your OCR channel\n\u2022 Upload images there for automatic scanning\n\u2022 Use `/scanimage` in that channel as backup",
                        inline=False,
                    )
                    await processing_msg.edit(content="", embed=embed)
                    return

                if message.channel.id != configured_channel_id:
                    configured_channel = self.bot.get_channel(configured_channel_id)
                    channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"

                    embed = discord.Embed(
                        title="\u274c Wrong Channel for OCR",
                        description=f"Automatic image scanning only works in {channel_mention}",
                        color=0xff4444,
                    )
                    embed.add_field(
                        name="\U0001f527 Options",
                        value=f"\u2022 Upload your image to {channel_mention} for automatic processing\n\u2022 Use `/scanimage` in {channel_mention} for manual scanning\n\u2022 Change OCR channel with `/setchannel #new-channel`",
                        inline=False,
                    )
                    await processing_msg.edit(content="", embed=embed)
                    return

                success, embed, processed_results = await self.process_image(
                    temp_file_path, guild_id, attachment.filename, message
                )

                if not success:
                    await processing_msg.edit(content="", embed=embed)
                    asyncio.create_task(self.bot.messages.countdown_and_delete_message(processing_msg, embed, 5))
                    return

                # Success - create interactive view for confirmation
                from ..bot import OCRConfirmationView

                view = OCRConfirmationView(
                    results=processed_results,
                    guild_id=guild_id,
                    user_id=message.author.id,
                    original_message_obj=message,
                    bot=self.bot,
                )

                view.message = processing_msg
                embed = view.create_embed()
                await processing_msg.edit(content="", embed=embed, view=view)

            finally:
                if temp_file and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        except Exception as e:
            logger.error(f"Error processing race results image: {e}")
            await message.channel.send(f"\u274c **Error processing image:** {str(e)}")

    async def handle_war_submission_from_view(self, interaction: discord.Interaction, view):
        """Handle OCR war submission from interactive view."""
        await interaction.response.defer()

        try:
            results = view.results
            guild_id = view.guild_id

            if not results:
                raise Exception("No valid players found for war submission")

            total_race_count = max(r.get('races', 12) for r in results)

            submission = self.bot.war_service.submit_war(results, total_race_count, guild_id)

            if submission.success:
                try:
                    await view.original_message_obj.add_reaction("\u2705")
                except discord.errors.NotFound:
                    logger.debug("Skipping reaction for deleted message")
                except Exception as e:
                    logger.warning(f"Failed to add reaction to original message: {e}")

                embed = discord.Embed(
                    title="\u2705 War Results Saved!",
                    description=f"Successfully saved war results for {len(results)} players.",
                    color=0x00ff00,
                )

                results_text = "\n".join([
                    f"**{r['name']}**: {r['score']} points" for r in results
                ])

                embed.add_field(
                    name=f"\U0001f4ca War Results ({len(results)} players)",
                    value=results_text,
                    inline=False,
                )
                embed.add_field(
                    name="\U0001f4c8 Database Updated",
                    value="Player statistics and averages have been updated.",
                    inline=False,
                )
                embed.set_footer(text=f"War added via OCR \u2022 Type: 6v6 \u2022 Races: {total_race_count}")
            else:
                embed = discord.Embed(
                    title="\u274c Database Error",
                    description=f"Failed to save war to database. {submission.error or 'Please try manual submission.'}",
                    color=0xff0000,
                )

            await interaction.edit_original_response(embed=embed, view=None)
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(view.message, embed))

        except Exception as e:
            logger.error(f"Error handling OCR war submission from view: {e}")
            embed = discord.Embed(
                title="\u274c Error",
                description=f"An error occurred while saving results: {str(e)}",
                color=0xff0000,
            )
            await interaction.edit_original_response(embed=embed, view=None)
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(view.message, embed))

    async def handle_war_submission(self, message: discord.Message, confirmation_data: Dict):
        """Handle OCR war submission to database (reaction-based flow)."""
        try:
            results = confirmation_data['results']
            guild_id = confirmation_data['guild_id']

            if not results:
                raise Exception("No valid players found for war submission")

            total_race_count = max(r.get('races', 12) for r in results)

            submission = self.bot.war_service.submit_war(results, total_race_count, guild_id)

            if submission.success:
                if 'original_message_obj' in confirmation_data:
                    try:
                        await confirmation_data['original_message_obj'].add_reaction("\u2705")
                    except discord.errors.NotFound:
                        logger.debug("Skipping reaction for deleted message")
                    except Exception as e:
                        logger.warning(f"Failed to add reaction to original message: {e}")

                embed = discord.Embed(
                    title="\u2705 War Results Saved!",
                    description=f"Successfully saved war results for {len(results)} players.",
                    color=0x00ff00,
                )

                results_text = "\n".join([
                    f"**{r['name']}**: {r['score']} points" for r in results
                ])

                embed.add_field(
                    name=f"\U0001f4ca War Results ({len(results)} players)",
                    value=results_text,
                    inline=False,
                )
                embed.add_field(
                    name="\U0001f4c8 Database Updated",
                    value="Player statistics and averages have been updated.",
                    inline=False,
                )
                embed.set_footer(text=f"War added via OCR \u2022 Type: 6v6 \u2022 Races: {total_race_count}")
            else:
                embed = discord.Embed(
                    title="\u274c Database Error",
                    description=f"Failed to save war to database. {submission.error or 'Please try manual submission.'}",
                    color=0xff0000,
                )

            await message.edit(embed=embed)
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass

            self.bot.confirmations.cleanup(str(message.id))
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed))

        except Exception as e:
            logger.error(f"Error in OCR war submission: {e}")
            embed = discord.Embed(
                title="\u274c Submission Error",
                description=f"Failed to submit war: {str(e)}",
                color=0xff0000,
            )
            await message.edit(embed=embed)
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass
            self.bot.confirmations.cleanup(str(message.id))
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed))

    async def send_report(
        self,
        guild_id: int,
        user: discord.User,
        original_image: Optional[discord.Attachment],
        ocr_results: List[Dict],
        user_description: str,
    ) -> None:
        """Send OCR issue report to admin via DM and admin logging channel."""
        try:
            admin_user_id = config.ADMIN_USER_ID
            admin_logging_channel_id = config.ADMIN_LOGGING_CHANNEL_ID

            if not admin_user_id or not admin_logging_channel_id:
                logger.warning("Admin user ID or logging channel ID not configured in config")
                return

            report_embed = discord.Embed(
                title="\U0001f6a9 OCR Issue Report",
                description="User reported an issue with OCR scanning results.",
                color=0xff6600,
            )

            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"Guild ID: {guild_id}"

            report_embed.add_field(
                name="\U0001f4cb Report Details",
                value=f"**Guild**: {guild_name}\n**User**: {user.mention} ({user.name}#{user.discriminator})\n**Timestamp**: <t:{int(discord.utils.utcnow().timestamp())}:f>",
                inline=False,
            )

            report_embed.add_field(
                name="\U0001f50d User's Description",
                value=user_description[:1024],
                inline=False,
            )

            if ocr_results:
                results_text = "\n".join([
                    f"\u2022 **{result['name']}**: {result['score']} pts (confidence: {result.get('confidence', 'N/A')})"
                    for result in ocr_results
                ])
                report_embed.add_field(
                    name="\U0001f4ca OCR Results",
                    value=results_text[:1024],
                    inline=False,
                )

            if original_image:
                report_embed.add_field(
                    name="\U0001f5bc\ufe0f Original Image",
                    value=f"**Filename**: {original_image.filename}\n**Size**: {original_image.size} bytes\n**URL**: [View Image]({original_image.url})",
                    inline=False,
                )

            report_embed.set_footer(text="Use /debugocr to investigate this issue")

            try:
                admin_user = await self.bot.fetch_user(admin_user_id)
                await admin_user.send(embed=report_embed)
                logger.info(f"Sent OCR report to admin user {admin_user_id}")
            except Exception as e:
                logger.warning(f"Failed to send OCR report DM to admin: {e}")

            try:
                admin_channel = self.bot.get_channel(admin_logging_channel_id)
                if admin_channel and isinstance(admin_channel, discord.TextChannel):
                    if original_image:
                        await admin_channel.send(embed=report_embed, file=await original_image.to_file())
                    else:
                        await admin_channel.send(embed=report_embed)
                    logger.info(f"Sent OCR report to admin channel {admin_logging_channel_id}")
                else:
                    logger.warning(f"Admin logging channel {admin_logging_channel_id} not found or is not a text channel")
            except Exception as e:
                logger.warning(f"Failed to send OCR report to admin channel: {e}")

        except Exception as e:
            logger.error(f"Error sending OCR report: {e}")

    def format_enhanced_confirmation(
        self, results: List[Dict], validation: Dict, war_metadata: Dict = None
    ) -> str:
        """Format extracted results with validation info and war metadata for confirmation."""
        if not results:
            return "No results found."

        formatted = "\U0001f3c1 **War Results Detected:**\n\n"

        if war_metadata:
            formatted += "\U0001f4c5 **War Information:**\n"
            if war_metadata.get('date'):
                formatted += f"\u2022 **Date**: {war_metadata['date']}\n"
            if war_metadata.get('time'):
                formatted += f"\u2022 **Time**: {war_metadata['time']}\n"
            formatted += f"\u2022 **Races**: {war_metadata.get('race_count', config.DEFAULT_RACE_COUNT)}\n"
            formatted += f"\u2022 **Format**: {war_metadata.get('war_type', '6v6')}\n"
            formatted += "\n"

        if validation.get('warnings'):
            formatted += "\u26a0\ufe0f **Warnings:**\n"
            for warning in validation['warnings']:
                formatted += f"\u2022 {warning}\n"
            formatted += "\n"

        expected = config.EXPECTED_PLAYERS_PER_TEAM
        actual = len(results)
        formatted += f"\U0001f4ca **Player Scores ({actual}/{expected} players):**\n"

        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result['name']}**: {result['score']}\n"

        formatted += "\n**Please verify this war data is correct:**"
        formatted += "\n\u2705 = Save to database | \u274c = Cancel | \u270f\ufe0f = Edit manually"

        return formatted
