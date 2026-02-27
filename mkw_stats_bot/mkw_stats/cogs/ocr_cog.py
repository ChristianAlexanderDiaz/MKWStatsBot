"""OCR image scanning commands."""

import asyncio
import logging
import os
import tempfile
import traceback

import aiofiles
import aiofiles.tempfile
import discord
from discord import app_commands

from ..database import DatabaseManager
from .base_cog import BaseCog, require_guild_setup


def _log_task_error(t: asyncio.Task) -> None:
    if t.cancelled():
        return
    exc = t.exception()
    if exc:
        logging.error("Background task failed", exc_info=exc)


class OCRCog(BaseCog):
    """OCR image scanning commands."""

    async def _add_ocr_confirmation(self, message, processed_results, guild_id: int, user_id: int, original_message):
        """Add confirmation reactions to OCR results for database submission."""
        try:
            await message.add_reaction("✅")
            await message.add_reaction("❌")

            confirmation_data = {
                'type': 'ocr_war_submission',
                'results': processed_results,
                'guild_id': guild_id,
                'user_id': user_id,
                'channel_id': message.channel.id,
                'original_message_obj': original_message
            }

            self.bot.pending_confirmations[str(message.id)] = confirmation_data

            # Start timeout task in background and track it
            timeout_task = asyncio.create_task(self._handle_ocr_confirmation_timeout(message.id, 60))
            self.bot.timeout_tasks[str(message.id)] = timeout_task

        except Exception as e:
            logging.error(f"Error adding OCR confirmation: {e}")

    async def _handle_ocr_confirmation_timeout(self, message_id: int, timeout_seconds: int):
        """Handle timeout for OCR confirmation."""
        try:
            await asyncio.sleep(timeout_seconds)

            # Check if still pending
            message_id_str = str(message_id)
            if message_id_str in self.bot.pending_confirmations:
                confirmation_data = self.bot.pending_confirmations[message_id_str]
                channel_id = confirmation_data.get('channel_id')

                # Clean up the confirmation
                self.bot.cleanup_confirmation(message_id_str)

                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)
                        expired_embed = discord.Embed(
                            title="⏰ Confirmation Expired",
                            description="The confirmation period has expired. Results were not saved.",
                            color=0x808080
                        )
                        await message.edit(embed=expired_embed)
                        await message.clear_reactions()
                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to update expired confirmation: {e}")
        except asyncio.CancelledError:
            raise

    async def _countdown_and_delete_confirmation(self, message: discord.Message, embed: discord.Embed, countdown_seconds: int = 60):
        """Countdown and delete confirmation message for bulk scan."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:  # Only show countdown for last 5 seconds
                try:
                    embed_copy = embed.copy()
                    embed_copy.set_footer(text=f"This confirmation expires in {remaining} seconds")
                    await message.edit(embed=embed_copy)
                except (discord.errors.NotFound, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to update countdown: {e}")

        # Clean up and delete
        try:
            message_id = str(message.id)
            self.bot.pending_confirmations.pop(message_id, None)
            await message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException) as e:
            logging.debug(f"Failed to delete message: {e}")

    @app_commands.command(name="scanimage", description="Manually scan the most recent image in this channel (backup for when automatic OCR misses)")
    @require_guild_setup
    async def scanimage(self, interaction: discord.Interaction):
        """Manually scan the most recent image uploaded to the channel."""
        await interaction.response.defer(thinking=True)

        try:
            guild_id = self.get_guild_id(interaction)
            logging.info(f"🔍 Starting manual image scan for user {interaction.user.name}")

            # Check if an OCR channel is configured for this guild
            configured_channel_id = self.bot.db.guilds.get_ocr_channel(guild_id)
            if not configured_channel_id:
                embed = discord.Embed(
                    title="❌ No OCR Channel Set",
                    description="You need to configure an OCR channel before using image scanning.",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Setup Required",
                    value="Use `/setchannel #your-channel` to enable automatic and manual OCR processing.",
                    inline=False
                )
                embed.add_field(
                    name="📖 How it works",
                    value="• Set a channel with `/setchannel`\n• Upload images there for automatic scanning\n• Use `/scanimage` in that channel as backup",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Check if current channel is the configured OCR channel (bypass for bot owner)
            if interaction.channel.id != configured_channel_id and not DatabaseManager.is_bot_owner(interaction.user.id):
                configured_channel = self.bot.get_channel(configured_channel_id)
                channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"

                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Image scanning is only available in {channel_mention}",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Options",
                    value=f"• Use `/scanimage` in {channel_mention}\n• Change OCR channel with `/setchannel #new-channel`",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Search for the most recent image in the channel
            recent_image = None
            original_message = None
            async for message in interaction.channel.history(limit=50):
                for attachment in message.attachments:
                    if attachment.filename.lower().endswith('.png'):
                        recent_image = attachment
                        original_message = message
                        logging.info(f"✅ Found image: {attachment.filename}")
                        break
                if recent_image:
                    break

            if not recent_image:
                await interaction.followup.send("❌ No recent images found in this channel (checked last 50 messages). Try uploading an image with the command!")
                return

            # Download image
            try:
                async with self.bot.http_session.get(recent_image.url) as response:
                    if response.status != 200:
                        await interaction.followup.send(f"❌ Failed to download image: HTTP {response.status}")
                        return

                    async with aiofiles.tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                        temp_path = temp_file.name
                        image_data = await response.read()
                        await temp_file.write(image_data)
                        logging.info(f"✅ Image downloaded to: {temp_path}")
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to download image: {str(e)}")
                return

            try:
                # Use shared OCR processing logic
                guild_id = self.get_guild_id_from_interaction(interaction)

                success, embed, processed_results = await self.bot.process_ocr_image(
                    temp_path, guild_id, recent_image.filename, original_message
                )

                if not success:
                    error_msg = await interaction.followup.send(embed=embed)
                    _task = asyncio.create_task(self.bot._countdown_and_delete_message(error_msg, embed, 5))
                    _task.add_done_callback(_log_task_error)
                    return

                # Success - create interactive view for confirmation
                from mkw_stats.bot import OCRConfirmationView

                view = OCRConfirmationView(
                    results=processed_results,
                    guild_id=guild_id,
                    user_id=interaction.user.id,
                    original_message_obj=original_message,
                    bot=self.bot
                )

                embed = view.create_embed()
                response_msg = await interaction.followup.send(embed=embed, view=view)

                # Store message reference in view immediately after send
                view.message = response_msg

            finally:
                try:
                    os.unlink(temp_path)
                except OSError as e:
                    logging.debug(f"Failed to delete temporary file: {e}")

        except Exception as e:
            logging.error(f"Error in scanimage command: {e}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")

    @app_commands.command(name="bulkscanimage", description="Scan all images in this channel and create individual war entries")
    @app_commands.describe(limit="Maximum number of images to process (default: all images)")
    @require_guild_setup
    async def bulkscanimage(self, interaction: discord.Interaction, limit: int = None):
        """Bulk scan all images in the channel and process them sequentially."""
        await interaction.response.defer(thinking=True)

        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            logging.info(f"🔍 Starting bulk image scan for user {interaction.user.name} with limit: {limit}")

            # Check if an OCR channel is configured for this guild
            configured_channel_id = self.bot.db.guilds.get_ocr_channel(guild_id)
            if not configured_channel_id:
                embed = discord.Embed(
                    title="❌ No OCR Channel Set",
                    description="You need to configure an OCR channel before using bulk image scanning.",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Setup Required",
                    value="Use `/setchannel #your-channel` to enable bulk OCR processing.",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Check if current channel is the configured OCR channel (bypass for bot owner)
            if interaction.channel.id != configured_channel_id and not DatabaseManager.is_bot_owner(interaction.user.id):
                configured_channel = self.bot.get_channel(configured_channel_id)
                channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"

                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Bulk image scanning is only available in {channel_mention}",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Options",
                    value=f"• Use `/bulkscanimage` in {channel_mention}\n• Change OCR channel with `/setchannel #new-channel`",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Search for images in the channel
            images_found = []
            oldest_image_msg = None
            newest_image_msg = None

            search_limit = None if limit is None else limit * 10

            async for message in interaction.channel.history(limit=search_limit):
                for attachment in message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        if newest_image_msg is None:
                            newest_image_msg = message
                        oldest_image_msg = message

                        images_found.append({
                            'message': message,
                            'attachment': attachment
                        })

                        if limit and len(images_found) >= limit:
                            break

                if limit and len(images_found) >= limit:
                    break

            # Reverse the list so we process oldest images first (chronological order)
            images_found.reverse()

            if not images_found:
                await interaction.followup.send("❌ No images found in this channel (searched recent messages). Try uploading images first!")
                return

            # Create confirmation embed with date range
            embed = discord.Embed(
                title="🔍 Bulk Image Scan Ready",
                description=f"Found {len(images_found)} image{'s' if len(images_found) != 1 else ''} to process" +
                           (" (limited from channel total)" if limit and len(images_found) == limit else ""),
                color=0x00ff00
            )

            # Format date range
            if oldest_image_msg and newest_image_msg:
                oldest_time = discord.utils.format_dt(oldest_image_msg.created_at, style='f')
                newest_time = discord.utils.format_dt(newest_image_msg.created_at, style='f')

                embed.add_field(
                    name="📅 Date Range",
                    value=f"• **Oldest**: {oldest_time}\n• **Newest**: {newest_time}",
                    inline=False
                )

            # Time estimation
            estimated_seconds = len(images_found) * 5  # ~5 seconds per image

            hours = estimated_seconds // 3600
            minutes = (estimated_seconds % 3600) // 60
            seconds = estimated_seconds % 60

            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds > 0 or not time_parts:
                time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

            time_str = "~" + ", ".join(time_parts)

            embed.add_field(
                name="⏱️ Estimated Time",
                value=time_str,
                inline=True
            )

            embed.add_field(
                name="❓ Confirmation",
                value=f"✅ Process {len(images_found)} image{'s' if len(images_found) != 1 else ''} | ❌ Cancel",
                inline=False
            )

            embed.set_footer(text="Each image will create a separate war entry • React below to confirm or cancel")

            # Send confirmation and add reactions
            confirmation_msg = await interaction.followup.send(embed=embed)
            await confirmation_msg.add_reaction("✅")
            await confirmation_msg.add_reaction("❌")

            # Store bulk scan data for confirmation handling
            bulk_scan_data = {
                'type': 'bulk_scan_confirmation',
                'images_found': images_found,
                'guild_id': guild_id,
                'user_id': interaction.user.id,
                'channel_id': interaction.channel.id,
                'limit': limit
            }

            self.bot.pending_confirmations[str(confirmation_msg.id)] = bulk_scan_data

        except Exception as e:
            logging.error(f"Error in bulkscanimage command: {e}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")

    @app_commands.command(name="debugocr", description="Debug OCR processing with detailed output file (does NOT save to database)")
    @app_commands.describe(limit="Maximum number of images to process (default: all images)")
    @require_guild_setup
    async def debugocr(self, interaction: discord.Interaction, limit: int = None):
        """Debug OCR processing with detailed output file."""
        await interaction.response.defer(thinking=True)

        debug_output_path = None  # Track the debug output file for cleanup

        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            logging.info(f"[DEBUG-OCR] Debug scan started by {interaction.user.name} (limit: {limit})")

            # Check if an OCR channel is configured for this guild
            configured_channel_id = self.bot.db.guilds.get_ocr_channel(guild_id)
            if not configured_channel_id:
                embed = discord.Embed(
                    title="❌ No OCR Channel Set",
                    description="You need to configure an OCR channel before using debug OCR.",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Setup Required",
                    value="Use `/setchannel #your-channel` to enable OCR processing.",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Check if current channel is the configured OCR channel (bypass for bot owner)
            if interaction.channel.id != configured_channel_id and not DatabaseManager.is_bot_owner(interaction.user.id):
                configured_channel = self.bot.get_channel(configured_channel_id)
                channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"

                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Debug OCR is only available in {channel_mention}",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Options",
                    value=f"• Use `/debugocr` in {channel_mention}\n• Change OCR channel with `/setchannel #new-channel`",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Search for images in the channel
            images_found = []
            search_limit = None if limit is None else limit * 10

            async for message in interaction.channel.history(limit=search_limit):
                for attachment in message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        images_found.append({
                            'message': message,
                            'attachment': attachment
                        })

                        if limit and len(images_found) >= limit:
                            break

                if limit and len(images_found) >= limit:
                    break

            # Reverse the list so we process oldest images first (chronological order)
            images_found.reverse()

            if not images_found:
                await interaction.followup.send("❌ No images found in this channel (searched recent messages). Try uploading images first!")
                return

            # Send initial status message
            status_embed = discord.Embed(
                title="🔍 Debug OCR Processing Started",
                description=f"Processing {len(images_found)} image{'s' if len(images_found) != 1 else ''}...\n\n**This will NOT save results to the database.**\n**Detailed output will be provided in a text file.**",
                color=0x3498db
            )
            status_msg = await interaction.followup.send(embed=status_embed)

            # Initialize debug output buffer
            from datetime import datetime
            debug_lines = []
            debug_lines.append(f"Debug OCR Scan | User: {interaction.user.name} | Limit: {limit if limit else 'all'} | Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            debug_lines.append("")

            # Custom logging handler to capture OCR processing logs
            class DebugLogHandler(logging.Handler):
                def __init__(self):
                    super().__init__()
                    self.messages = []

                def emit(self, record):
                    try:
                        msg = record.getMessage()
                        self.messages.append(msg)
                    except Exception:  # noqa: S110 - logging handlers must not raise
                        pass

            # Process each image with detailed logging
            results_summary = []

            for idx, img_data in enumerate(images_found):
                message = img_data['message']
                attachment = img_data['attachment']

                debug_lines.append(f"[Image {idx + 1}/{len(images_found)}: {attachment.filename}]")

                temp_path = None
                cropped_path = None
                visual_path = None

                debug_handler = DebugLogHandler()
                debug_handler.setLevel(logging.DEBUG)

                try:
                    # Download image to temp file
                    async with self.bot.http_session.get(attachment.url) as resp:
                        if resp.status == 200:
                            suffix = os.path.splitext(attachment.filename)[1]
                            fd, temp_path = tempfile.mkstemp(suffix=suffix)
                            os.close(fd)
                            async with aiofiles.open(temp_path, 'wb') as tmp_file:
                                await tmp_file.write(await resp.read())

                    if not temp_path:
                        error_msg = "Failed to download image"
                        debug_lines.append(f"ERROR: {error_msg}")
                        debug_lines.append("")
                        results_summary.append({
                            'filename': attachment.filename,
                            'success': False,
                            'error': error_msg,
                            'players_found': 0
                        })
                        continue

                    # Get image dimensions
                    from PIL import Image
                    with Image.open(temp_path) as img:
                        img_width, img_height = img.size

                    # Perform OCR with detailed logging
                    ocr = self.bot.ocr

                    # Add handler to capture all OCR processing logs
                    logging.getLogger().addHandler(debug_handler)

                    # Step 1: Crop and detect format
                    cropped_path, visual_path, crop_coords = ocr.crop_image_to_target_region(temp_path)
                    table_format = ocr.detect_table_format(img_width, img_height)
                    debug_lines.append(f"Dim: {img_width}x{img_height} | Format: {table_format.value} | Crop: {crop_coords}")

                    # Step 2: Perform OCR
                    ocr_result = ocr.perform_ocr_on_file(temp_path)

                    if not ocr_result["success"]:
                        error_msg = ocr_result.get('error', 'Unknown error')
                        debug_lines.append(f"OCR Failed: {error_msg}")
                        debug_lines.append("")
                        results_summary.append({
                            'filename': attachment.filename,
                            'success': False,
                            'error': error_msg,
                            'players_found': 0
                        })
                        continue

                    # Step 3: Log raw OCR text
                    raw_text = ocr_result.get("text", "")
                    debug_lines.append(f"OCR:\n{raw_text if raw_text.strip() else '(empty)'}")

                    # Step 4: Log OCR tokens
                    tokens = raw_text.split()
                    debug_lines.append(f"Tokens[{len(tokens)}]: {tokens}")

                    # Step 5: Parse results with detailed logging
                    extracted_texts = [{'text': raw_text, 'confidence': 0.9}]
                    processed_results = ocr._parse_mario_kart_results(extracted_texts, guild_id)

                    # Step 6: Log player extraction results
                    if processed_results:
                        player_strs = []
                        for result in processed_results:
                            races = result.get('races', 12)
                            player_strs.append(f"{result['name']}({result['score']}pts,{races}r)")
                        debug_lines.append(f"Players[{len(processed_results)}]: {' | '.join(player_strs)}")
                    else:
                        debug_lines.append("Players[0]: none")

                    # Step 7: Log validation
                    validation = ocr._validate_results(processed_results, guild_id) if processed_results else None
                    if validation:
                        valid_str = "true" if validation.get('is_valid', False) else "false"
                        errors_str = ", ".join(validation['errors']) if validation.get('errors') else "none"
                        warnings_str = ", ".join(validation['warnings']) if validation.get('warnings') else "none"
                        debug_lines.append(f"Valid: {valid_str} | Errors: {errors_str} | Warnings: {warnings_str}")
                    else:
                        debug_lines.append("Valid: false | Errors: no results | Warnings: none")

                    # Step 8: Add captured internal logs
                    if debug_handler.messages:
                        debug_lines.append("")
                        debug_lines.append("Processing Details:")
                        for log_msg in debug_handler.messages:
                            if any(marker in log_msg for marker in ['🔍', '📊', '✅', '🎯', '🔀', '⚠️', '🏁', '✂️', '❌', '[DEBUG-OCR]', 'OCR', 'guild', 'score', 'player', 'team', 'split']):
                                clean_msg = log_msg.replace('[DEBUG-OCR] ', '')
                                debug_lines.append(f"  {clean_msg}")

                    debug_lines.append("")

                    # Add to summary
                    results_summary.append({
                        'filename': attachment.filename,
                        'success': True if processed_results else False,
                        'error': None if processed_results else 'No players detected',
                        'players_found': len(processed_results) if processed_results else 0,
                        'players': [r['name'] for r in processed_results] if processed_results else []
                    })

                except Exception as e:
                    error_msg = str(e)
                    debug_lines.append(f"ERROR: {error_msg}")
                    debug_lines.append(f"Traceback: {traceback.format_exc()}")
                    debug_lines.append("")
                    results_summary.append({
                        'filename': attachment.filename,
                        'success': False,
                        'error': error_msg,
                        'players_found': 0
                    })

                finally:
                    try:
                        logging.getLogger().removeHandler(debug_handler)
                    except Exception:  # noqa: S110 - handler removal is best-effort
                        pass

                    try:
                        if temp_path and os.path.exists(temp_path):
                            os.unlink(temp_path)
                        if cropped_path and os.path.exists(cropped_path):
                            os.unlink(cropped_path)
                        if visual_path and os.path.exists(visual_path):
                            os.unlink(visual_path)
                    except OSError as e:
                        logging.debug(f"[DEBUG-OCR] Failed to delete temporary file: {e}")

            # Write debug output to file
            fd, debug_output_path = tempfile.mkstemp(suffix='.txt', prefix='debug_ocr_')
            os.close(fd)

            async with aiofiles.open(debug_output_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(debug_lines))

            logging.info("[DEBUG-OCR] Debug scan completed")

            # Create summary embed
            summary_embed = discord.Embed(
                title="🔍 Debug OCR Processing Complete",
                description=f"Processed {len(images_found)} image{'s' if len(images_found) != 1 else ''}\n\n**Results NOT saved to database** (debug mode only)",
                color=0x00ff00
            )

            success_count = sum(1 for r in results_summary if r['success'])
            fail_count = len(results_summary) - success_count

            summary_embed.add_field(
                name="📊 Summary",
                value=f"✅ Successful: {success_count}\n❌ Failed: {fail_count}",
                inline=False
            )

            results_text = []
            for result in results_summary[:10]:
                status = "✅" if result['success'] else "❌"
                players_info = f" ({result['players_found']} players)" if result['success'] else ""
                error_info = f" - {result['error']}" if result.get('error') else ""
                results_text.append(f"{status} `{result['filename']}`{players_info}{error_info}")

            if len(results_summary) > 10:
                results_text.append(f"\n_...and {len(results_summary) - 10} more (see attached file)_")

            summary_embed.add_field(
                name="📁 Images Processed",
                value="\n".join(results_text) if results_text else "None",
                inline=False
            )

            summary_embed.add_field(
                name="📋 Debug Output",
                value="**See attached file for complete details:**\n"
                      "• Image dimensions and crop coordinates\n"
                      "• Raw OCR text and tokens\n"
                      "• Player name resolution\n"
                      "• Validation results",
                inline=False
            )

            summary_embed.set_footer(text="Debug mode - no changes made to database")

            from datetime import datetime
            debug_file = discord.File(debug_output_path, filename=f"debug_ocr_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt")
            await status_msg.edit(embed=summary_embed, attachments=[debug_file])

        except Exception as e:
            logging.error(f"[DEBUG-OCR] Error in debugocr command: {e}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")

        finally:
            try:
                if debug_output_path and os.path.exists(debug_output_path):
                    os.unlink(debug_output_path)
            except OSError as e:
                logging.debug(f"[DEBUG-OCR] Failed to delete debug output file: {e}")


async def setup(bot):
    await bot.add_cog(OCRCog(bot))
