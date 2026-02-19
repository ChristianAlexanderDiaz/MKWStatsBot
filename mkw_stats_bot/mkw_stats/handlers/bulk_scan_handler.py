"""Bulk scan processing: multi-image OCR, dashboard integration, and result saving."""

import asyncio
import os
import tempfile
import aiohttp
import discord
from typing import Dict, List

from ..dashboard_client import dashboard_client
from ..logging_config import get_logger

logger = get_logger(__name__)


class BulkScanHandler:
    """Handles bulk image scan processing, confirmation, and saving.

    Responsible for:
    - Processing multiple images sequentially with progress updates
    - Creating dashboard review sessions
    - Saving confirmed bulk results to database via WarService
    - Building result/confirmation embeds
    """

    def __init__(self, bot):
        self.bot = bot

    async def handle_processing(self, message: discord.Message, confirmation_data: Dict):
        """Handle bulk scan processing after user confirms."""
        try:
            images_found = confirmation_data['images_found']
            guild_id = confirmation_data['guild_id']
            total_images = len(images_found)

            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass

            embed = discord.Embed(
                title="\U0001f504 Processing Bulk Image Scan",
                description=f"Processing {total_images} image{'s' if total_images != 1 else ''}...",
                color=0x00ff00,
            )
            embed.add_field(name="\u23f3 Status", value="Starting image processing...", inline=False)
            embed.set_footer(text="This may take several minutes \u2022 Processing images sequentially")
            await message.edit(embed=embed)

            successful_wars = []
            failed_images = []

            for i, image_data in enumerate(images_found, 1):
                try:
                    progress_embed = discord.Embed(
                        title="\U0001f504 Processing Bulk Image Scan",
                        description=f"Processing image {i}/{total_images}: {image_data['attachment'].filename}",
                        color=0x00ff00,
                    )
                    progress_embed.add_field(
                        name="\u23f3 Progress",
                        value=f"{'▓' * (i * 20 // total_images)}{'░' * (20 - (i * 20 // total_images))} {i}/{total_images}",
                        inline=False,
                    )
                    progress_embed.set_footer(text=f"Estimated time remaining: ~{(total_images - i) * 5} seconds")
                    await message.edit(embed=progress_embed)

                    temp_file_path = None
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(image_data['attachment'].url) as response:
                                if response.status == 200:
                                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                                        temp_file_path = temp_file.name
                                        image_bytes = await response.read()
                                        temp_file.write(image_bytes)
                                else:
                                    raise Exception(f"Failed to download: HTTP {response.status}")

                        if hasattr(self.bot.ocr, 'process_image_async'):
                            result = await self.bot.ocr.process_image_async(
                                temp_file_path,
                                guild_id,
                                image_data['message'].author.id,
                                image_data['message'].created_at,
                            )
                            success = result.get('success', False)
                            processed_results = result.get('results', [])
                        else:
                            success, _, processed_results = await self.bot.ocr_handler.process_image(
                                temp_file_path, guild_id, image_data['attachment'].filename, image_data['message']
                            )

                        if success and processed_results:
                            parsed_results = []
                            for result in processed_results:
                                parsed_results.append({
                                    'name': result['name'],
                                    'original_name': result.get('raw_name', result['name']),
                                    'score': result['score'],
                                    'races': result.get('races', 12),
                                })

                            if parsed_results:
                                total_race_count = max(r['races'] for r in parsed_results)
                                successful_wars.append({
                                    'filename': image_data['attachment'].filename,
                                    'players': parsed_results,
                                    'total_race_count': total_race_count,
                                    'message': image_data['message'],
                                })
                            else:
                                failed_images.append({
                                    'filename': image_data['attachment'].filename,
                                    'error': 'No valid players found',
                                    'message': image_data['message'],
                                })
                        else:
                            failed_images.append({
                                'filename': image_data['attachment'].filename,
                                'error': 'OCR processing failed',
                                'message': image_data['message'],
                            })

                    finally:
                        if temp_file_path and os.path.exists(temp_file_path):
                            try:
                                os.unlink(temp_file_path)
                            except:
                                pass

                    await asyncio.sleep(1)

                except Exception as e:
                    failed_images.append({
                        'filename': image_data['attachment'].filename,
                        'error': str(e),
                        'message': image_data['message'],
                    })
                    logger.error(f"Error processing {image_data['attachment'].filename}: {e}")

            if successful_wars or failed_images:
                original_confirmation = self.bot.pending_confirmations.get(str(message.id), {})
                original_user_id = original_confirmation.get('user_id', 0)

                if dashboard_client.is_enabled() and len(successful_wars) >= 1:
                    await self._create_dashboard_review_session(
                        message, successful_wars, failed_images,
                        total_images, guild_id, original_user_id,
                    )
                else:
                    await self.create_confirmation_embed(
                        message, successful_wars, failed_images,
                        total_images, guild_id, original_user_id,
                    )
            else:
                embed = discord.Embed(
                    title="\u274c No Results Found",
                    description="No images could be processed successfully.",
                    color=0xff0000,
                )
                await message.edit(embed=embed)
                self.bot.confirmations.cleanup(str(message.id))
                asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed, 30))

        except Exception as e:
            logger.error(f"Error in bulk scan processing: {e}")
            embed = discord.Embed(
                title="\u274c Bulk Scan Error",
                description=f"An error occurred during bulk processing: {str(e)}",
                color=0xff0000,
            )
            await message.edit(embed=embed)
            self.bot.confirmations.cleanup(str(message.id))

    async def _create_dashboard_review_session(
        self,
        message: discord.Message,
        successful_wars: List[Dict],
        failed_images: List[Dict],
        total_images: int,
        guild_id: int,
        user_id: int,
    ):
        """Create a dashboard review session and send the review link."""
        try:
            api_results = []
            for war in successful_wars:
                roster_players = self.bot.db.get_roster_players(guild_id)
                roster_names = [p.lower() for p in roster_players] if roster_players else []

                players_with_roster_check = []
                for player in war['players']:
                    is_roster = player['name'].lower() in roster_names
                    players_with_roster_check.append({
                        **player,
                        'is_roster_member': is_roster,
                    })

                api_results.append({
                    'filename': war.get('filename'),
                    'image_url': war['message'].attachments[0].url if war.get('message') and war['message'].attachments else None,
                    'players': players_with_roster_check,
                    'race_count': war.get('total_race_count', 12),
                    'message_timestamp': war['message'].created_at.isoformat() if war.get('message') else None,
                    'discord_message_id': war['message'].id if war.get('message') else None,
                })

            api_failed_results = []
            for failed in failed_images:
                api_failed_results.append({
                    'filename': failed.get('filename'),
                    'image_url': failed['message'].attachments[0].url if failed.get('message') and failed['message'].attachments else None,
                    'error_message': failed.get('error'),
                    'message_timestamp': failed['message'].created_at.isoformat() if failed.get('message') else None,
                    'discord_message_id': failed['message'].id if failed.get('message') else None,
                })

            session = await dashboard_client.create_bulk_session(
                guild_id=guild_id,
                user_id=user_id,
                results=api_results,
                failed_results=api_failed_results,
            )

            if session and session.get('token'):
                review_url = dashboard_client.get_review_url(session['token'])

                embed = discord.Embed(
                    title="Bulk Scan Complete",
                    description=f"Processed {len(successful_wars)} images successfully!",
                    color=0x00ff00,
                )
                embed.add_field(
                    name="Review & Confirm",
                    value=f"[Open Dashboard]({review_url})\n\nReview all {len(successful_wars)} wars, edit player names/scores, and save to database.",
                    inline=False,
                )

                if failed_images:
                    def format_failed_item(f):
                        if f.get('message') and f['message'].created_at:
                            ts = f['message'].created_at
                            return f"\u2022 {ts.strftime('%m/%d/%Y %I:%M %p')}: {f['error']}"
                        return f"\u2022 {f.get('filename', 'Unknown')}: {f['error']}"

                    failed_list = "\n".join([format_failed_item(f) for f in failed_images[:5]])
                    if len(failed_images) > 5:
                        failed_list += f"\n... and {len(failed_images) - 5} more"
                    embed.add_field(
                        name=f"Failed Images ({len(failed_images)})",
                        value=failed_list,
                        inline=False,
                    )

                embed.set_footer(text="Link expires in 24 hours")
                await message.edit(embed=embed)
                self.bot.confirmations.cleanup(str(message.id))
                logger.info(f"Created dashboard review session {session['token']} for {len(successful_wars)} wars")
            else:
                logger.warning("Dashboard API failed, falling back to Discord confirmation")
                await self.create_confirmation_embed(
                    message, successful_wars, failed_images,
                    total_images, guild_id, user_id,
                )

        except Exception as e:
            logger.error(f"Error creating dashboard review session: {e}")
            await self.create_confirmation_embed(
                message, successful_wars, failed_images,
                total_images, guild_id, user_id,
            )

    async def handle_results_save(self, message: discord.Message, confirmation_data: Dict):
        """Handle saving confirmed bulk scan results to database."""
        try:
            successful_wars = confirmation_data['successful_wars']
            failed_images = confirmation_data['failed_images']
            total_images = confirmation_data['total_images']
            guild_id = confirmation_data['guild_id']

            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass

            embed = discord.Embed(
                title="\U0001f4be Saving Wars to Database",
                description="Saving confirmed results to database...",
                color=0x00ff00,
            )
            await message.edit(embed=embed)

            saved_wars = []
            save_failures = []

            for war_info in successful_wars:
                try:
                    submission = self.bot.war_service.submit_war(
                        war_info['players'], war_info['total_race_count'], guild_id
                    )

                    if submission.success:
                        saved_wars.append({
                            'filename': war_info['filename'],
                            'war_id': submission.war_id,
                            'players': war_info['players'],
                            'total_race_count': war_info['total_race_count'],
                        })

                        try:
                            await war_info['message'].add_reaction("\u2705")
                        except discord.errors.NotFound:
                            logger.debug("Skipping reaction for deleted message during bulk scan")
                        except Exception as e:
                            logger.warning(f"Failed to add reaction to message: {e}")
                    else:
                        save_failures.append({
                            'filename': war_info['filename'],
                            'error': submission.error or 'Database save failed',
                        })

                except Exception as e:
                    save_failures.append({
                        'filename': war_info['filename'],
                        'error': str(e),
                    })
                    logger.error(f"Error saving war {war_info['filename']}: {e}")

            user_id = confirmation_data.get('user_id')
            await self.create_results_embed(message, saved_wars, save_failures, failed_images, total_images, guild_id, user_id)
            self.bot.confirmations.cleanup(str(message.id))

        except Exception as e:
            logger.error(f"Error in bulk results save: {e}")
            embed = discord.Embed(
                title="\u274c Save Error",
                description=f"An error occurred while saving results: {str(e)}",
                color=0xff0000,
            )
            await message.edit(embed=embed)
            self.bot.confirmations.cleanup(str(message.id))

    async def create_results_embed(
        self,
        message: discord.Message,
        saved_wars: List[Dict],
        save_failures: List[Dict],
        failed_images: List[Dict],
        total_images: int,
        guild_id: int = None,
        user_id: int = None,
    ):
        """Create final results embed after saving to database."""
        success_count = len(saved_wars)
        save_failure_count = len(save_failures)
        ocr_failure_count = len(failed_images)
        total_failures = save_failure_count + ocr_failure_count

        if success_count == 0:
            embed = discord.Embed(
                title="\u274c No Wars Saved",
                description=f"Unable to save any wars from {total_images} images",
                color=0xff0000,
            )
        elif total_failures == 0:
            embed = discord.Embed(
                title="\u2705 Bulk Scan Complete - All Saved!",
                description=f"Successfully saved {success_count} wars from {total_images} images",
                color=0x00ff00,
            )
        else:
            embed = discord.Embed(
                title="\u26a0\ufe0f Bulk Scan Complete - Partial Success",
                description=f"Saved {success_count} wars, {total_failures} failed",
                color=0xffa500,
            )

        if saved_wars:
            wars_text = ""
            for war_info in saved_wars:
                players_summary = ", ".join([
                    f"{p['name']}"
                    + (f"({p['races']})" if p['races'] != war_info['total_race_count'] else "")
                    + f": {p['score']}"
                    for p in war_info['players']
                ])

                if len(players_summary) > 80:
                    players_summary = players_summary[:80] + "..."

                wars_text += f"**War #{war_info['war_id']}**\n\u2022 {players_summary}\n\n"

            if len(wars_text) > 1000:
                wars_text = wars_text[:1000] + "...\n*(truncated for space)*"

            embed.add_field(
                name=f"\u2705 Saved Wars ({success_count})",
                value=wars_text,
                inline=False,
            )

        if save_failures or failed_images:
            failures_text = ""
            all_failures = save_failures + [{'filename': f['filename'], 'error': f['error']} for f in failed_images]

            for failure in all_failures:
                failure_line = f"\u2022 **{failure['filename']}**: {failure['error']}\n"
                if len(failures_text + failure_line) > 1000:
                    failures_text += "...\n*(truncated)*"
                    break
                failures_text += failure_line

            embed.add_field(
                name=f"\u274c Failed ({total_failures})",
                value=failures_text,
                inline=False,
            )

            embed.add_field(
                name="\U0001f4a1 Fix Failed Images",
                value="Use `/addwar` to manually add results for failed images, or retry with `/scanimage`.",
                inline=False,
            )

        embed.set_footer(text=f"Bulk scan completed \u2022 {success_count} saved, {total_failures} failed")
        await message.edit(embed=embed)

        # Send DM notification to user
        if user_id and guild_id:
            try:
                user = self.bot.get_user(user_id)
                if user:
                    guild = self.bot.get_guild(guild_id)
                    guild_name = guild.name if guild else f"Server (ID: {guild_id})"

                    dm_embed = discord.Embed(
                        title="\u2705 Bulk Scan Complete",
                        description=f"Your bulk scan in **{guild_name}** has finished processing!",
                        color=0x00ff00 if total_failures == 0 else (0xffa500 if success_count > 0 else 0xff0000),
                    )

                    dm_embed.add_field(
                        name="\U0001f4ca Results",
                        value=f"\u2022 **Wars Saved**: {success_count}\n\u2022 **Failed**: {total_failures}\n\u2022 **Total Images**: {total_images}",
                        inline=False,
                    )

                    if success_count == total_images:
                        status_msg = "All images processed successfully!"
                    elif success_count > 0:
                        status_msg = "Scan completed with some failures. Check the channel for details."
                    else:
                        status_msg = "No wars could be saved. Check the channel for error details."

                    dm_embed.add_field(name="Status", value=status_msg, inline=False)
                    dm_embed.set_footer(text=f"Server: {guild_name}")
                    await user.send(embed=dm_embed)
                    logger.info(f"Sent bulk scan completion DM to user {user_id} for guild {guild_id}")
            except discord.errors.Forbidden:
                logger.warning(f"Cannot send DM to user {user_id} - DMs are disabled")
            except Exception as e:
                logger.error(f"Failed to send bulk scan completion DM: {e}")

        asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed, 60))

    async def create_confirmation_embed(
        self,
        message: discord.Message,
        successful_wars: List[Dict],
        failed_images: List[Dict],
        total_images: int,
        guild_id: int,
        user_id: int,
    ):
        """Create confirmation embed showing all OCR results before saving to database."""
        success_count = len(successful_wars)
        failure_count = len(failed_images)

        if success_count == 0:
            embed = discord.Embed(
                title="\u274c Bulk Scan Complete - No Results",
                description=f"Failed to process all {total_images} images",
                color=0xff0000,
            )

            if failed_images:
                failures_text = ""
                for failure in failed_images:
                    failures_text += f"\u2022 **{failure['filename']}**: {failure['error']}\n"

                if len(failures_text) > 1000:
                    failures_text = failures_text[:1000] + "...\n*(truncated)*"

                embed.add_field(
                    name=f"\u274c Failed Images ({failure_count})",
                    value=failures_text,
                    inline=False,
                )

            await message.edit(embed=embed)
            self.bot.confirmations.cleanup(str(message.id))
            asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, embed, 60))
            return

        embed = discord.Embed(
            title="\U0001f50d Bulk Scan Results - Review Before Saving",
            description=f"Found results in {success_count}/{total_images} images. **Review the OCR results below:**",
            color=0x00ff00 if failure_count == 0 else 0xffa500,
        )

        wars_text = ""
        for i, war_info in enumerate(successful_wars):
            players_list = []
            for p in war_info['players']:
                if p['races'] == war_info['total_race_count']:
                    players_list.append(f"\u2022 {p['name']}: {p['score']} points")
                else:
                    players_list.append(f"\u2022 {p['name']} ({p['races']}): {p['score']} points")

            message_time = discord.utils.format_dt(war_info['message'].created_at, style='f')
            war_section = f"\U0001f4ca **{message_time}**\n" + "\n".join(players_list) + "\n\n"

            if len(wars_text + war_section) > 1500:
                wars_text += f"*(... and {len(successful_wars) - i} more wars)*\n"
                break

            wars_text += war_section

        embed.add_field(
            name=f"\U0001f4cb Detected Results ({success_count} wars)",
            value=wars_text or "See individual war details",
            inline=False,
        )

        if failed_images:
            failures_text = ""
            for i, failure in enumerate(failed_images):
                failure_line = f"\u2022 {failure['error']}\n"
                if len(failures_text + failure_line) > 1000:
                    failures_text += f"\u2022 *(... and {len(failed_images) - i} more failures)*\n"
                    break
                failures_text += failure_line

            embed.add_field(
                name=f"\u274c Failed Images ({failure_count})",
                value=failures_text,
                inline=False,
            )

        embed.add_field(
            name="\u2753 Confirmation Required",
            value="\u2705 **Save all wars to database**\n\u274c **Cancel and discard results**",
            inline=False,
        )

        embed.set_footer(text="Review the OCR results carefully \u2022 React below to confirm or cancel")

        try:
            await message.delete()
        except:
            pass

        confirmation_msg = await message.channel.send(embed=embed)
        await confirmation_msg.add_reaction("\u2705")
        await confirmation_msg.add_reaction("\u274c")

        bulk_results_data = {
            'type': 'bulk_results_confirmation',
            'successful_wars': successful_wars,
            'failed_images': failed_images,
            'total_images': total_images,
            'guild_id': guild_id,
            'user_id': user_id,
        }

        if str(message.id) in self.bot.pending_confirmations:
            del self.bot.pending_confirmations[str(message.id)]

        self.bot.pending_confirmations[str(confirmation_msg.id)] = bulk_results_data

    async def countdown_and_delete_confirmation(
        self,
        message: discord.Message,
        embed: discord.Embed,
        countdown_seconds: int = 60,
    ):
        """Countdown and delete confirmation for bulk results."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:
                try:
                    embed_copy = embed.copy()
                    embed_copy.set_footer(text=f"Review the OCR results carefully \u2022 Expires in {remaining} seconds")
                    await message.edit(embed=embed_copy)
                except:
                    pass

        try:
            message_id = str(message.id)
            if message_id in self.bot.pending_confirmations:
                del self.bot.pending_confirmations[message_id]

            timeout_embed = discord.Embed(
                title="\u23f0 Confirmation Expired",
                description="Bulk scan results were not saved due to timeout. Use `/bulkscanimage` again if needed.",
                color=0x999999,
            )
            await message.edit(embed=timeout_embed)
            await message.clear_reactions()

            asyncio.create_task(self.bot.messages.countdown_and_delete_message(message, timeout_embed, 30))
        except:
            pass
