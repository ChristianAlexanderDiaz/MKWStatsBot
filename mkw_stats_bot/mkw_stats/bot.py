import discord
from discord.ext import commands
import asyncio
import json
import os
import tempfile
import aiohttp
from typing import Optional, Dict, List, Union
from dotenv import load_dotenv
from . import config
from .database import DatabaseManager
from .ocr_processor import OCRProcessor
from .logging_config import get_logger, log_discord_command, setup_logging

# Load environment variables from .env file if it exists
load_dotenv()

# Setup centralized logging
setup_logging()
logger = get_logger(__name__)

class MarioKartBot(commands.Bot):
 
    """
    This is the main class for the Mario Kart Stats Bot.
    It is a subclass of the discord.ext.commands.Bot class.
    It is used to create the bot and handle the bot's events.
    """
    def __init__(self):
        # Initialize the bot's intents
        intents = discord.Intents.default()
        # Enable message content intenti
        intents.message_content = True
        # Enable reactions intent
        intents.reactions = True
        
        # Initialize the bot with no command prefix (slash commands only)
        super().__init__(command_prefix=None, intents=intents)
        
        # Initialize the new v2 database system
        self.db = DatabaseManager()
        # Initialize OCR processor at startup for instant response across all guilds
        self.ocr = OCRProcessor(db_manager=self.db)
        # Initialize the pending confirmations dictionary
        self.pending_confirmations = {}  # message_id -> confirmation_data
    
    """
    This is the on_ready event.
    It is called when the bot is ready to start processing events.
    """
    async def on_ready(self) -> None:
        """Event handler called when bot is ready."""
        # Log the bot's connection to Discord
        logger.info(f'{self.user} has connected to Discord!')
        # Log the number of guilds the bot is in
        logger.info(f'Bot is in {len(self.guilds)} guilds')
        # Log bot version for debugging
        logger.info(f'🔧 Bot Version: {config.BOT_VERSION}')
        
        # NOTE: Automatic roster initialization disabled
        # Guilds must now use /setup command for proper initialization
        logger.info("🔧 Automatic roster initialization disabled - use /setup command")
        logger.info("🔧 Using slash commands only - prefix commands disabled")
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.error(f"❌ Failed to sync slash commands: {e}")
        
        # Set bot status
        await self.change_presence(
            # Set the bot's status to watching for Mario Kart results
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for Mario Kart results 🏁"
            )
        )
    
    async def on_command_error(self, ctx, error):
        """Handle command errors - should not occur with prefix commands disabled."""
        if isinstance(error, commands.CommandNotFound):
            # Silently ignore command not found errors since we don't use prefix commands
            logger.debug(f"Ignored prefix command attempt: {ctx.message.content}")
            return
        
        # Log other errors for debugging
        logger.error(f"Command error: {error}")
        logger.error(f"Context: {ctx.message.content if ctx.message else 'Unknown'}")
    
    """
    This is the on_message event.
    It is called when a message is sent in a channel the bot is in.
    """
    async def on_message(self, message):
        # Ignore bot's own messages
        if message.author == self.user:
            return
        
        # Check if message has attachments (images)
        if message.attachments:
            # Get the configured OCR channel for this guild
            guild_id = message.guild.id if message.guild else None
            if not guild_id:
                return
                
            configured_channel_id = self.db.get_ocr_channel(guild_id)
            if not configured_channel_id or message.channel.id != configured_channel_id:
                return
            
            # Process each image attachment
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    await self.process_race_results_image(message, attachment)
    
    async def process_ocr_image(self, temp_path: str, guild_id: int, filename: str, original_message):
        """Shared OCR processing logic for both automatic and manual scanning."""
        try:
            # Use bot's OCR processor (initialized at startup)
            ocr = self.ocr
            
            # Perform OCR (raw results)
            ocr_result = ocr.perform_ocr_on_file(temp_path)
            
            if not ocr_result["success"]:
                embed = discord.Embed(
                    title="❌ OCR Failed",
                    description=f"OCR processing failed: {ocr_result.get('error', 'Unknown error')}",
                    color=0xff4444
                )
                return False, embed, None
                
            # Format raw OCR results for Discord
            if not ocr_result["text"].strip():
                embed = discord.Embed(
                    title="❌ No Text Detected",
                    description="OCR completed, but no text was detected in the image.",
                    color=0xff4444
                )
                return False, embed, None
                
            # Process OCR results for database validation
            extracted_texts = [{'text': ocr_result["text"], 'confidence': 0.9}]
            processed_results = ocr._parse_mario_kart_results(extracted_texts, guild_id)
            
            # Add confirmation workflow if we have processed results
            if processed_results:
                # Create clean confirmation embed without debug info
                embed = discord.Embed(
                    title="🏁 Mario Kart Results Detected",
                    description=f"Found {len(processed_results)} players in {filename}",
                    color=0x00ff00
                )
                
                # Show detected players
                players_text = "\n".join([
                    f"• {result['name']}" + (f" ({result.get('races', 12)})" if result.get('races', 12) != 12 else "") + f": {result['score']} points"
                    for result in processed_results
                ])
                
                embed.add_field(
                    name="📊 Detected Players",
                    value=players_text,
                    inline=False
                )
                
                embed.add_field(
                    name="❓ Confirmation Required",
                    value="React with ✅ to save these results or ❌ to cancel.",
                    inline=False
                )
                
                embed.set_footer(text="This confirmation expires in 60 seconds")
                
                return True, embed, processed_results
            else:
                # No results found
                embed = discord.Embed(
                    title="❌ No Results Found",
                    description=f"No clan members detected in {filename}",
                    color=0xff4444
                )
                embed.add_field(
                    name="Try:",
                    value="• Make sure the image shows a clear results table\n• Check that player names match your roster\n• Use `/addwar` for manual entry",
                    inline=False
                )
                return False, embed, None
                
        except Exception as e:
            logger.error(f"Error in shared OCR processing: {e}")
            embed = discord.Embed(
                title="❌ Processing Error",
                description=f"An error occurred while processing the image: {str(e)}",
                color=0xff4444
            )
            return False, embed, None

    async def process_race_results_image(self, message: discord.Message, attachment: discord.Attachment):
        """Process an image attachment for Mario Kart race results using shared OCR logic."""
        try:
            # Send initial processing message
            processing_msg = await message.channel.send("🔍 Processing race results image...")
            
            # Download the image
            temp_file = None
            try:
                # Create a temporary file to store the image
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                    # Save the image to the temporary file
                    await attachment.save(temp_file.name)
                    # Get the path to the temporary file
                    temp_file_path = temp_file.name
                
                # Get guild ID and validate channel
                guild_id = message.guild.id if message.guild else None
                if not guild_id:
                    await processing_msg.edit(content="❌ **Error:** Could not determine guild ID.")
                    return
                
                # Check if an OCR channel is configured for this guild
                configured_channel_id = self.db.get_ocr_channel(guild_id)
                if not configured_channel_id:
                    embed = discord.Embed(
                        title="❌ No OCR Channel Set",
                        description="You need to configure an OCR channel before automatic image scanning will work.",
                        color=0xff4444
                    )
                    embed.add_field(
                        name="🔧 Setup Required",
                        value="Use `/setchannel #your-channel` to enable automatic OCR processing in that channel.",
                        inline=False
                    )
                    embed.add_field(
                        name="📖 How it works",
                        value="• Run `/setchannel #results` to set your OCR channel\n• Upload images there for automatic scanning\n• Use `/scanimage` in that channel as backup",
                        inline=False
                    )
                    await processing_msg.edit(content="", embed=embed)
                    return
                
                # Check if current channel is the configured OCR channel  
                if message.channel.id != configured_channel_id:
                    configured_channel = self.get_channel(configured_channel_id)
                    channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"
                    
                    embed = discord.Embed(
                        title="❌ Wrong Channel for OCR",
                        description=f"Automatic image scanning only works in {channel_mention}",
                        color=0xff4444
                    )
                    embed.add_field(
                        name="🔧 Options",
                        value=f"• Upload your image to {channel_mention} for automatic processing\n• Use `/scanimage` in {channel_mention} for manual scanning\n• Change OCR channel with `/setchannel #new-channel`",
                        inline=False
                    )
                    await processing_msg.edit(content="", embed=embed)
                    return
                
                # Use shared OCR processing logic (validation already done)
                success, embed, processed_results = await self.process_ocr_image(
                    temp_file_path, guild_id, attachment.filename, message
                )
                
                if not success:
                    # Show error embed briefly then remove it (like addwar does)
                    await processing_msg.edit(content="", embed=embed)
                    # Auto-delete the embed after 5 seconds to keep channel clean
                    asyncio.create_task(self._countdown_and_delete_message(processing_msg, embed, 5))
                    return
                
                # Success - show confirmation embed and add reactions
                await processing_msg.edit(content="", embed=embed)
                
                # Add reaction buttons
                await processing_msg.add_reaction("✅")
                await processing_msg.add_reaction("❌")
                
                # Store pending confirmation data with original message reference
                confirmation_data = {
                    'type': 'ocr_war_submission',
                    'results': processed_results,
                    'guild_id': guild_id,
                    'user_id': message.author.id,
                    'channel_id': message.channel.id,
                    'original_message_obj': message
                }
                
                self.pending_confirmations[str(processing_msg.id)] = confirmation_data
                
                # Start timeout - use same countdown logic as other confirmations
                asyncio.create_task(self._countdown_and_delete_message(processing_msg, embed, 60))
                
            finally:
                # Clean up temp file
                if temp_file and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        # If an error occurs, log the error
        except Exception as e:
            logger.error(f"Error processing race results image: {e}")
            await message.channel.send(f"❌ **Error processing image:** {str(e)}")
    
    async def on_reaction_add(self, reaction, user):
        """Handle confirmation reactions."""
        if user == self.user:
            return
        
        message_id = str(reaction.message.id)
        
        # Check if this is a pending confirmation
        if message_id not in self.pending_confirmations:
            return
        
        confirmation_data = self.pending_confirmations[message_id]
        
        # Check if the user who reacted is the one who posted the original message
        if user.id != confirmation_data['user_id']:
            return
        
        if str(reaction.emoji) == "✅":
            await self.handle_confirmation_accept(reaction.message, confirmation_data)
        elif str(reaction.emoji) == "❌":
            await self.handle_confirmation_reject(reaction.message, confirmation_data)
        elif str(reaction.emoji) == "✏️":
            await self.handle_confirmation_edit(reaction.message, confirmation_data)
    
    async def handle_confirmation_accept(self, message: discord.Message, confirmation_data: Dict):
        """Handle accepted confirmation."""
        try:
            confirmation_type = confirmation_data.get('type', 'standard')
            
            if confirmation_type == 'bulk_scan_confirmation':
                # Handle bulk scan processing
                await self.handle_bulk_scan_processing(message, confirmation_data)
                return
            
            if confirmation_type == 'bulk_results_confirmation':
                # Handle saving bulk scan results to database
                await self.handle_bulk_results_save(message, confirmation_data)
                return
            
            results = confirmation_data['results']
            
            if confirmation_type == 'ocr_war_submission':
                # Handle OCR war submission
                success = await self.handle_ocr_war_submission(message, confirmation_data)
                return
            
            # Standard race results handling
            # Add message ID to results for tracking
            for result in results:
                result['message_id'] = confirmation_data['original_message_id']
            
            # Save to database
            success = self.db.add_race_results(results)
            
            if success:
                # Create success embed
                embed = discord.Embed(
                    title="✅ Results Saved Successfully!",
                    description=f"Saved results for {len(results)} clan members.",
                    color=0x00ff00
                )
                
                # Add individual results
                results_text = ""
                for result in results:
                    results_text += f"**{result['name']}**: {result['score']}\n"
                
                embed.add_field(name="Saved Results", value=results_text, inline=False)
                embed.set_footer(text="Results have been added to the database and averages updated.")
                
            else:
                embed = discord.Embed(
                    title="❌ Database Error",
                    description="Failed to save results to database. Please try again.",
                    color=0xff0000
                )
            
            await message.edit(embed=embed)
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                # Bot doesn't have permission to clear reactions, that's okay
                pass
            
            # Clean up pending confirmation
            self.cleanup_confirmation(str(message.id))
            
            # Start countdown and delete (using reusable helper)
            asyncio.create_task(self._countdown_and_delete_message(message, embed))
            
        except Exception as e:
            logger.error(f"Error handling confirmation accept: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while saving results: {str(e)}",
                color=0xff0000
            )
            await message.edit(embed=embed)
            
            # Start countdown and delete even on error (using reusable helper)
            asyncio.create_task(self._countdown_and_delete_message(message, embed))

    async def handle_ocr_war_submission(self, message: discord.Message, confirmation_data: Dict):
        """Handle OCR war submission to database."""
        try:
            results = confirmation_data['results']
            guild_id = confirmation_data['guild_id']
            
            # Get the commands cog to call addwar logic
            commands_cog = self.get_cog('MarioKartCommands')
            if not commands_cog:
                raise Exception("Commands cog not found")
            
            # Use the detailed OCR results directly (preserving race counts)
            from datetime import datetime
            import pytz
            
            # Process war submission using OCR results directly
            try:
                # Use OCR results directly instead of re-parsing string
                parsed_results = []
                
                for result in results:
                    player_name = result['name']
                    score = result['score']
                    race_count = result.get('races', 12)  # Use extracted race count or default to 12
                    
                    # Results from OCR processor are already database-validated names
                    parsed_results.append({
                        'name': player_name,
                        'original_name': result.get('raw_name', player_name),
                        'score': score,
                        'races': race_count,  # Use extracted race count
                        'date': datetime.now(pytz.UTC).strftime('%Y-%m-%d'),
                        'time': datetime.now(pytz.UTC).strftime('%H:%M:%S'),
                        'war_type': '6v6',
                        'notes': 'Auto-processed via OCR'
                    })
                
                if not parsed_results:
                    raise Exception("No valid players found for war submission")
                
                # Calculate total race count for the war (use max race count from all players)
                total_race_count = max(result['races'] for result in parsed_results)
                
                # Add war to database
                war_id = commands_cog.bot.db.add_race_results(parsed_results, total_race_count, guild_id)
                
                if war_id is not None:
                    # Update player statistics
                    for result in parsed_results:
                        commands_cog.bot.db.update_player_stats(
                            result['name'], 
                            result['score'], 
                            result['races'],  # Use individual race count
                            result['races'] / total_race_count,  # war_participation (races played / total races)
                            datetime.now(pytz.timezone('America/New_York')).isoformat(),
                            guild_id
                        )
                    
                    # Add checkmark to original image message
                    if 'original_message_obj' in confirmation_data:
                        try:
                            await confirmation_data['original_message_obj'].add_reaction("✅")
                        except discord.errors.NotFound:
                            # Message was deleted, skip adding reaction
                            logger.debug(f"Skipping reaction for deleted message")
                        except Exception as e:
                            # Log other errors but continue processing
                            logger.warning(f"Failed to add reaction to original message: {e}")
                            pass
                    
                    # Create success embed
                    embed = discord.Embed(
                        title="✅ War Results Saved!",
                        description=f"Successfully saved war results for {len(parsed_results)} players.",
                        color=0x00ff00
                    )
                    
                    # Add player summary
                    results_text = "\n".join([
                        f"**{result['name']}**: {result['score']} points" 
                        for result in parsed_results
                    ])
                    
                    embed.add_field(
                        name=f"📊 War Results ({len(parsed_results)} players)", 
                        value=results_text, 
                        inline=False
                    )
                    embed.add_field(
                        name="📈 Database Updated",
                        value="Player statistics and averages have been updated.",
                        inline=False
                    )
                    embed.set_footer(text=f"War added via OCR • Type: 6v6 • Races: {total_race_count}")
                    
                else:
                    embed = discord.Embed(
                        title="❌ Database Error",
                        description="Failed to save war to database. Please try manual submission.",
                        color=0xff0000
                    )
                
            except Exception as parse_error:
                logger.error(f"Error parsing OCR results for war submission: {parse_error}")
                embed = discord.Embed(
                    title="❌ Processing Error",
                    description=f"Error processing OCR results: {str(parse_error)}",
                    color=0xff0000
                )
            
            # Update message with result
            await message.edit(embed=embed)
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                # Bot doesn't have permission to clear reactions, that's okay
                pass
            
            # Clean up pending confirmation
            self.cleanup_confirmation(str(message.id))
            
            # Start countdown and delete (using reusable helper)
            asyncio.create_task(self._countdown_and_delete_message(message, embed))
            
        except Exception as e:
            logger.error(f"Error in OCR war submission: {e}")
            embed = discord.Embed(
                title="❌ Submission Error", 
                description=f"Failed to submit war: {str(e)}",
                color=0xff0000
            )
            await message.edit(embed=embed)
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                # Bot doesn't have permission to clear reactions, that's okay
                pass
            self.cleanup_confirmation(str(message.id))
            
            # Start countdown and delete (using reusable helper)
            asyncio.create_task(self._countdown_and_delete_message(message, embed))
    
    async def handle_bulk_scan_processing(self, message: discord.Message, confirmation_data: Dict):
        """Handle bulk scan processing after user confirms."""
        try:
            images_found = confirmation_data['images_found']
            guild_id = confirmation_data['guild_id']
            total_images = len(images_found)
            
            # Clear reactions and show processing message
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass
            
            # Create initial processing embed
            embed = discord.Embed(
                title="🔄 Processing Bulk Image Scan",
                description=f"Processing {total_images} image{'s' if total_images != 1 else ''}...",
                color=0x00ff00
            )
            embed.add_field(
                name="⏳ Status",
                value="Starting image processing...",
                inline=False
            )
            embed.set_footer(text="This may take several minutes • Processing images sequentially")
            
            await message.edit(embed=embed)
            
            # Process each image
            successful_wars = []
            failed_images = []
            
            for i, image_data in enumerate(images_found, 1):
                try:
                    # Update progress
                    progress_embed = discord.Embed(
                        title="🔄 Processing Bulk Image Scan",
                        description=f"Processing image {i}/{total_images}: {image_data['attachment'].filename}",
                        color=0x00ff00
                    )
                    progress_embed.add_field(
                        name="⏳ Progress",
                        value=f"{'▓' * (i * 20 // total_images)}{'░' * (20 - (i * 20 // total_images))} {i}/{total_images}",
                        inline=False
                    )
                    progress_embed.set_footer(text=f"Estimated time remaining: ~{(total_images - i) * 5} seconds")
                    
                    await message.edit(embed=progress_embed)
                    
                    # Download and process the image
                    import tempfile
                    import aiohttp
                    import os
                    
                    temp_file_path = None
                    try:
                        # Download image
                        async with aiohttp.ClientSession() as session:
                            async with session.get(image_data['attachment'].url) as response:
                                if response.status == 200:
                                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                                        temp_file_path = temp_file.name
                                        image_bytes = await response.read()
                                        temp_file.write(image_bytes)
                                else:
                                    raise Exception(f"Failed to download: HTTP {response.status}")
                        
                        # Process OCR using existing shared logic
                        success, _, processed_results = await self.process_ocr_image(
                            temp_file_path, guild_id, image_data['attachment'].filename, image_data['message']
                        )
                        
                        if success and processed_results:
                            # Store OCR results for later confirmation (don't save to database yet)
                            from datetime import datetime
                            import pytz
                            
                            # Process war submission data for confirmation
                            parsed_results = []
                            for result in processed_results:
                                player_name = result['name']
                                score = result['score']
                                race_count = result.get('races', 12)
                                
                                parsed_results.append({
                                    'name': player_name,
                                    'original_name': result.get('raw_name', player_name),
                                    'score': score,
                                    'races': race_count,
                                    'date': datetime.now(pytz.UTC).strftime('%Y-%m-%d'),
                                    'time': datetime.now(pytz.UTC).strftime('%H:%M:%S'),
                                    'war_type': '6v6',
                                    'notes': f'Auto-processed via bulk OCR from {image_data["attachment"].filename}'
                                })
                            
                            if parsed_results:
                                # Calculate total race count
                                total_race_count = max(result['races'] for result in parsed_results)
                                
                                # Store for confirmation (not saved to database yet)
                                successful_wars.append({
                                    'filename': image_data['attachment'].filename,
                                    'players': parsed_results,
                                    'total_race_count': total_race_count,
                                    'message': image_data['message']  # Store message for adding checkmark later
                                })
                            else:
                                failed_images.append({
                                    'filename': image_data['attachment'].filename,
                                    'error': 'No valid players found'
                                })
                        else:
                            failed_images.append({
                                'filename': image_data['attachment'].filename,
                                'error': 'OCR processing failed'
                            })
                            
                    finally:
                        # Clean up temp file
                        if temp_file_path and os.path.exists(temp_file_path):
                            try:
                                os.unlink(temp_file_path)
                            except:
                                pass
                    
                    # Add small delay to respect rate limits
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    failed_images.append({
                        'filename': image_data['attachment'].filename,
                        'error': str(e)
                    })
                    logger.error(f"Error processing {image_data['attachment'].filename}: {e}")
            
            # Show confirmation embed with all OCR results (before saving to database)
            if successful_wars or failed_images:
                # Get original user ID from the bulk scan confirmation data
                original_confirmation = self.pending_confirmations.get(str(message.id), {})
                original_user_id = original_confirmation.get('user_id', 0)
                await self.create_bulk_scan_confirmation_embed(message, successful_wars, failed_images, total_images, guild_id, original_user_id)
            else:
                # No results at all
                embed = discord.Embed(
                    title="❌ No Results Found",
                    description="No images could be processed successfully.",
                    color=0xff0000
                )
                await message.edit(embed=embed)
                self.cleanup_confirmation(str(message.id))
                asyncio.create_task(self._countdown_and_delete_message(message, embed, 30))
            
        except Exception as e:
            logger.error(f"Error in bulk scan processing: {e}")
            embed = discord.Embed(
                title="❌ Bulk Scan Error",
                description=f"An error occurred during bulk processing: {str(e)}",
                color=0xff0000
            )
            await message.edit(embed=embed)
            self.cleanup_confirmation(str(message.id))
    
    async def handle_bulk_results_save(self, message: discord.Message, confirmation_data: Dict):
        """Handle saving confirmed bulk scan results to database."""
        try:
            successful_wars = confirmation_data['successful_wars']
            failed_images = confirmation_data['failed_images']
            total_images = confirmation_data['total_images']
            guild_id = confirmation_data['guild_id']
            
            # Clear reactions
            try:
                await message.clear_reactions()
            except discord.errors.Forbidden:
                pass
            
            # Show saving progress
            embed = discord.Embed(
                title="💾 Saving Wars to Database",
                description="Saving confirmed results to database...",
                color=0x00ff00
            )
            await message.edit(embed=embed)
            
            # Save each war to database
            saved_wars = []
            save_failures = []
            
            from datetime import datetime
            import pytz
            
            for war_info in successful_wars:
                try:
                    # Add war to database
                    war_id = self.db.add_race_results(war_info['players'], war_info['total_race_count'], guild_id)
                    
                    if war_id is not None:
                        # Update player statistics
                        for result in war_info['players']:
                            self.db.update_player_stats(
                                result['name'], 
                                result['score'], 
                                result['races'],
                                result['races'] / war_info['total_race_count'],
                                datetime.now(pytz.timezone('America/New_York')).isoformat(),
                                guild_id
                            )
                        
                        # Store successful save info
                        saved_wars.append({
                            'filename': war_info['filename'],
                            'war_id': war_id,
                            'players': war_info['players'],
                            'total_race_count': war_info['total_race_count']
                        })
                        
                        # Add checkmark to original image message
                        try:
                            await war_info['message'].add_reaction("✅")
                        except discord.errors.NotFound:
                            # Message was deleted, skip adding reaction
                            logger.debug(f"Skipping reaction for deleted message during bulk scan")
                        except Exception as e:
                            # Log other errors but continue processing
                            logger.warning(f"Failed to add reaction to message: {e}")
                            pass
                    else:
                        save_failures.append({
                            'filename': war_info['filename'],
                            'error': 'Database save failed'
                        })
                        
                except Exception as e:
                    save_failures.append({
                        'filename': war_info['filename'],
                        'error': str(e)
                    })
                    logger.error(f"Error saving war {war_info['filename']}: {e}")
            
            # Create final success/failure embed
            await self.create_bulk_save_results_embed(message, saved_wars, save_failures, failed_images, total_images)
            
            # Clean up confirmation data
            self.cleanup_confirmation(str(message.id))
            
        except Exception as e:
            logger.error(f"Error in bulk results save: {e}")
            embed = discord.Embed(
                title="❌ Save Error",
                description=f"An error occurred while saving results: {str(e)}",
                color=0xff0000
            )
            await message.edit(embed=embed)
            self.cleanup_confirmation(str(message.id))
    
    async def create_bulk_save_results_embed(self, message: discord.Message, saved_wars: List[Dict], save_failures: List[Dict], failed_images: List[Dict], total_images: int):
        """Create final results embed after saving to database."""
        success_count = len(saved_wars)
        save_failure_count = len(save_failures)
        ocr_failure_count = len(failed_images)
        total_failures = save_failure_count + ocr_failure_count
        
        if success_count == 0:
            # Nothing saved
            embed = discord.Embed(
                title="❌ No Wars Saved",
                description=f"Unable to save any wars from {total_images} images",
                color=0xff0000
            )
        elif total_failures == 0:
            # All successful
            embed = discord.Embed(
                title="✅ Bulk Scan Complete - All Saved!",
                description=f"Successfully saved {success_count} wars from {total_images} images",
                color=0x00ff00
            )
        else:
            # Partial success
            embed = discord.Embed(
                title="⚠️ Bulk Scan Complete - Partial Success",
                description=f"Saved {success_count} wars, {total_failures} failed",
                color=0xffa500
            )
        
        # Show saved wars
        if saved_wars:
            wars_text = ""
            
            for war_info in saved_wars:
                # Show brief summary for each war
                players_summary = ", ".join([
                    f"{p['name']}" + (f"({p['races']})" if p['races'] != war_info['total_race_count'] else "") + f": {p['score']}"
                    for p in war_info['players']
                ])
                
                if len(players_summary) > 80:  # Truncate if too long
                    players_summary = players_summary[:80] + "..."
                
                wars_text += f"**War #{war_info['war_id']}**\n• {players_summary}\n\n"
            
            # Truncate if too long for Discord
            if len(wars_text) > 1000:
                wars_text = wars_text[:1000] + "...\n*(truncated for space)*"
            
            embed.add_field(
                name=f"✅ Saved Wars ({success_count})",
                value=wars_text or "Wars saved successfully",
                inline=False
            )
            
            embed.add_field(
                name="📊 Summary",
                value=f"• **Wars Created**: {success_count}\n• **Database Updated**: All player statistics refreshed",
                inline=False
            )
        
        # Show failures
        if save_failures or failed_images:
            all_failures = save_failures + failed_images
            failures_text = ""
            
            # Show all failures unless it would exceed Discord's character limit
            for i, failure in enumerate(all_failures):
                failure_line = f"• {failure['error']}\n"
                
                # Check if adding this failure would exceed Discord's field limit (~1000 chars)
                if len(failures_text + failure_line) > 1000:
                    failures_text += f"• *(... and {len(all_failures) - i} more failures)*\n"
                    break
                    
                failures_text += failure_line
            
            embed.add_field(
                name=f"❌ Failed ({total_failures})",
                value=failures_text,
                inline=False
            )
            
            embed.add_field(
                name="💡 Fix Failed Images",
                value="Use `/addwar` to manually add results for failed images, or retry with `/scanimage`.",
                inline=False
            )
        
        embed.set_footer(text=f"Bulk scan completed • {success_count} saved, {total_failures} failed")
        
        await message.edit(embed=embed)
        
        # Auto-delete after 60 seconds
        asyncio.create_task(self._countdown_and_delete_message(message, embed, 60))

    async def create_bulk_scan_confirmation_embed(self, message: discord.Message, successful_wars: List[Dict], failed_images: List[Dict], total_images: int, guild_id: int, user_id: int):
        """Create confirmation embed showing all OCR results before saving to database."""
        success_count = len(successful_wars)
        failure_count = len(failed_images)
        
        if success_count == 0:
            # All failed - no confirmation needed
            embed = discord.Embed(
                title="❌ Bulk Scan Complete - No Results",
                description=f"Failed to process all {total_images} images",
                color=0xff0000
            )
            
            # Show failed images
            if failed_images:
                failures_text = ""
                for failure in failed_images:
                    failures_text += f"• **{failure['filename']}**: {failure['error']}\n"
                
                if len(failures_text) > 1000:
                    failures_text = failures_text[:1000] + "...\n*(truncated)*"
                
                embed.add_field(
                    name=f"❌ Failed Images ({failure_count})",
                    value=failures_text,
                    inline=False
                )
            
            await message.edit(embed=embed)
            self.cleanup_confirmation(str(message.id))
            asyncio.create_task(self._countdown_and_delete_message(message, embed, 60))
            return
        
        # Show OCR results for confirmation
        embed = discord.Embed(
            title="🔍 Bulk Scan Results - Review Before Saving",
            description=f"Found results in {success_count}/{total_images} images. **Review the OCR results below:**",
            color=0x00ff00 if failure_count == 0 else 0xffa500
        )
        
        # Show detailed results for each war (same format as individual scanimage)
        wars_text = ""
        
        for i, war_info in enumerate(successful_wars):
            # Show players for this war (same detail as /scanimage)
            players_list = []
            for p in war_info['players']:
                if p['races'] == war_info['total_race_count']:
                    players_list.append(f"• {p['name']}: {p['score']} points")
                else:
                    players_list.append(f"• {p['name']} ({p['races']}): {p['score']} points")
            
            # Use the message timestamp instead of filename
            message_time = discord.utils.format_dt(war_info['message'].created_at, style='f')
            war_section = f"📊 **{message_time}**\n" + "\n".join(players_list) + "\n\n"
            
            # Check if adding this war would exceed Discord's limit
            if len(wars_text + war_section) > 1500:  # Leave room for other fields
                wars_text += f"*(... and {len(successful_wars) - i} more wars)*\n"
                break
            
            wars_text += war_section
        
        embed.add_field(
            name=f"📋 Detected Results ({success_count} wars)",
            value=wars_text or "See individual war details",
            inline=False
        )
        
        # Show failed images if any
        if failed_images:
            failures_text = ""
            
            # Show all failures unless it would exceed Discord's character limit
            for i, failure in enumerate(failed_images):
                failure_line = f"• {failure['error']}\n"
                
                # Check if adding this failure would exceed Discord's field limit
                if len(failures_text + failure_line) > 1000:
                    failures_text += f"• *(... and {len(failed_images) - i} more failures)*\n"
                    break
                    
                failures_text += failure_line
            
            embed.add_field(
                name=f"❌ Failed Images ({failure_count})",
                value=failures_text,
                inline=False
            )
        
        # Add confirmation instructions
        embed.add_field(
            name="❓ Confirmation Required",
            value="✅ **Save all wars to database**\n❌ **Cancel and discard results**",
            inline=False
        )
        
        embed.set_footer(text="Review the OCR results carefully • React below to confirm or cancel")
        
        # Delete the old processing message and create a new clean confirmation message
        try:
            await message.delete()
        except:
            pass
        
        # Send new confirmation message with no previous reactions
        confirmation_msg = await message.channel.send(embed=embed)
        
        # Add fresh reaction buttons
        await confirmation_msg.add_reaction("✅")
        await confirmation_msg.add_reaction("❌")
        
        # Store the results for later confirmation handling
        bulk_results_data = {
            'type': 'bulk_results_confirmation',
            'successful_wars': successful_wars,
            'failed_images': failed_images,
            'total_images': total_images,
            'guild_id': guild_id,
            'user_id': user_id  # Pass through the original user who ran the command
        }
        
        # Clean up old confirmation data and store new one
        if str(message.id) in self.pending_confirmations:
            del self.pending_confirmations[str(message.id)]
        
        # Store in pending confirmations for reaction handling (use new message ID)
        self.pending_confirmations[str(confirmation_msg.id)] = bulk_results_data
        
        # No auto-delete countdown - let user decide when to confirm/cancel
    
    async def _countdown_and_delete_confirmation_bulk(self, message: discord.Message, embed: discord.Embed, countdown_seconds: int = 60):
        """Countdown and delete confirmation for bulk results."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:  # Only show countdown for last 5 seconds
                try:
                    embed_copy = embed.copy()
                    embed_copy.set_footer(text=f"Review the OCR results carefully • Expires in {remaining} seconds")
                    await message.edit(embed=embed_copy)
                except:
                    pass
        
        # Timeout - clean up and show expired message
        try:
            message_id = str(message.id)
            if message_id in self.pending_confirmations:
                del self.pending_confirmations[message_id]
            
            timeout_embed = discord.Embed(
                title="⏰ Confirmation Expired",
                description="Bulk scan results were not saved due to timeout. Use `/bulkscanimage` again if needed.",
                color=0x999999
            )
            await message.edit(embed=timeout_embed)
            await message.clear_reactions()
            
            # Delete after 30 seconds
            asyncio.create_task(self._countdown_and_delete_message(message, timeout_embed, 30))
        except:
            pass

    async def handle_confirmation_reject(self, message: discord.Message, confirmation_data: Dict):
        """Handle rejected confirmation."""
        embed = discord.Embed(
            title="❌ Results Cancelled",
            description="Results were not saved to the database.",
            color=0xff6600
        )
        await message.edit(embed=embed)
        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:
            # Bot doesn't have permission to clear reactions, that's okay
            pass
        
        # Clean up pending confirmation
        self.cleanup_confirmation(str(message.id))
        
        # Start countdown and delete (using reusable helper)
        asyncio.create_task(self._countdown_and_delete_message(message, embed))

    async def handle_confirmation_edit(self, message: discord.Message, confirmation_data: Dict):
        """Handle manual edit request."""
        results = confirmation_data['results']
        
        embed = discord.Embed(
            title="✏️ Manual Edit Mode",
            description="Edit the results below using the commands:",
            color=0x9932cc
        )
        
        # Show current parsed results
        current_results = ""
        for i, result in enumerate(results, 1):
            current_results += f"{i}. **{result['name']}**: {result['score']}\n"
        
        embed.add_field(
            name="📊 Current Results",
            value=current_results or "No results",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Edit Commands",
            value=(
                "Manual editing is no longer supported.\n"
                "Use `/addwar` command to add war results manually."
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /addwar command for manual entry instead")
        
        await message.edit(embed=embed)
        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:
            # Bot doesn't have permission to clear reactions, that's okay
            pass
        
        # Store edit session data
        edit_session_data = {
            'results': confirmation_data['results'].copy(),
            'original_message_id': confirmation_data['original_message_id'],
            'user_id': confirmation_data['user_id'],
            'channel_id': confirmation_data['channel_id'],
            'edit_message_id': str(message.id)
        }
        
        # Store in a different dict for edit sessions
        if not hasattr(self, 'edit_sessions'):
            self.edit_sessions = {}
        self.edit_sessions[confirmation_data['user_id']] = edit_session_data
        
        # Clean up pending confirmation
        self.cleanup_confirmation(str(message.id))
    
    async def handle_confirmation_timeout(self, message: discord.Message):
        """Handle confirmation timeout."""
        embed = discord.Embed(
            title="⏰ Confirmation Expired",
            description="Results were not saved due to timeout.",
            color=0x999999
        )
        await message.edit(embed=embed)
        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:
            # Bot doesn't have permission to clear reactions, that's okay
            pass
        
        # Clean up pending confirmation
        self.cleanup_confirmation(str(message.id))
    
    def cleanup_confirmation(self, message_id: str):
        """Clean up confirmation data."""
        if message_id in self.pending_confirmations:
            del self.pending_confirmations[message_id]
        # Note: v2 database stores confirmations in memory only, no database cleanup needed
    
    async def _auto_delete_message(self, message: discord.Message, delay_seconds: int):
        """Auto-delete a message after the specified delay."""
        await asyncio.sleep(delay_seconds)
        try:
            await message.delete()
        except discord.errors.NotFound:
            # Message already deleted
            pass
        except discord.errors.Forbidden:
            # Bot doesn't have permission to delete messages
            pass
    
    async def _countdown_and_delete_message(self, message: discord.Message, embed: discord.Embed, countdown_seconds: int = 30):
        """Show countdown timer and delete message (for regular discord messages)."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:  # Only show countdown for last 5 seconds
                try:
                    await message.edit(embed=embed, content=f"Disappearing in {remaining} seconds...")
                except:
                    pass
        
        # Delete the message
        try:
            await message.delete()
        except:
            pass
    
    async def _countdown_and_delete_interaction(self, interaction: discord.Interaction, embed: discord.Embed, countdown_seconds: int = 30):
        """Show countdown timer and delete interaction response (for slash command responses)."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:  # Only show countdown for last 5 seconds
                try:
                    await interaction.edit_original_response(
                        embed=embed, 
                        content=f"Disappearing in {remaining} seconds..."
                    )
                except:
                    pass
        
        # Delete the message
        try:
            await interaction.delete_original_response()
        except:
            pass
    
    def format_enhanced_confirmation(self, results: List[Dict], validation: Dict, war_metadata: Dict = None) -> str:
        """Format extracted results with validation info and war metadata for confirmation."""
        if not results:
            return "No results found."
        
        formatted = "🏁 **War Results Detected:**\n\n"
        
        # War metadata section
        if war_metadata:
            formatted += "📅 **War Information:**\n"
            if war_metadata.get('date'):
                formatted += f"• **Date**: {war_metadata['date']}\n"
            if war_metadata.get('time'):
                formatted += f"• **Time**: {war_metadata['time']}\n"
            formatted += f"• **Races**: {war_metadata.get('race_count', config.DEFAULT_RACE_COUNT)}\n"
            formatted += f"• **Format**: {war_metadata.get('war_type', '6v6')}\n"
            formatted += "\n"
        
        # Validation status
        if validation.get('warnings'):
            formatted += "⚠️ **Warnings:**\n"
            for warning in validation['warnings']:
                formatted += f"• {warning}\n"
            formatted += "\n"
        
        # Results table with expected count indicator
        expected = config.EXPECTED_PLAYERS_PER_TEAM
        actual = len(results)
        formatted += f"📊 **Player Scores ({actual}/{expected} players):**\n"
        
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result['name']}**: {result['score']}\n"
        
        # Add confirmation instructions
        formatted += f"\n**Please verify this war data is correct:**"
        formatted += "\n✅ = Save to database | ❌ = Cancel | ✏️ = Edit manually"
        
        return formatted



async def setup_bot():
    """Setup function that creates the bot and loads the commands cog."""
    bot = MarioKartBot()
    
    # Load the commands cog
    from .commands import MarioKartCommands
    await bot.add_cog(MarioKartCommands(bot))
    
    return bot

# Run the bot
if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("❌ Please set DISCORD_BOT_TOKEN environment variable")
        exit(1)
    
    # Use asyncio to run the bot setup and start
    import asyncio
    
    async def main():
        bot = await setup_bot()
        await bot.start(config.DISCORD_TOKEN)
    
    asyncio.run(main()) 