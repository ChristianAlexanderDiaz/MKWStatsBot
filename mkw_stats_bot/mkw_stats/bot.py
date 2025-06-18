import discord
from discord.ext import commands
import asyncio
import logging
import json
import os
import tempfile
import aiohttp
from typing import Optional, Dict, List
from dotenv import load_dotenv
from . import config
from .database import DatabaseManager
from .ocr_processor import OCRProcessor

# Load environment variables from .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mario_kart_bot.log'),
        logging.StreamHandler()
    ]
)

class MarioKartBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        # Initialize the new v2 database system
        self.db = DatabaseManager()
        self.ocr = OCRProcessor(db_manager=self.db)
        self.pending_confirmations = {}  # message_id -> confirmation_data
    
    async def on_ready(self):
        logging.info(f'{self.user} has connected to Discord!')
        logging.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for Mario Kart results 🏁"
            )
        )
    
    async def on_message(self, message):
        # Ignore bot's own messages
        if message.author == self.user:
            return
        
        # Process commands first
        await self.process_commands(message)
        
        # Check if message has attachments (images)
        if message.attachments:
            # Check if we're in the configured channel (if set)
            if config.CHANNEL_ID and message.channel.id != config.CHANNEL_ID:
                return
            
            # Process each image attachment
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    await self.process_race_results_image(message, attachment)
    
    async def process_race_results_image(self, message: discord.Message, attachment: discord.Attachment):
        """Process an image attachment for Mario Kart race results."""
        try:
            # Send initial processing message
            processing_msg = await message.channel.send("🔍 Processing race results image...")
            
            # Download the image
            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                    await attachment.save(temp_file.name)
                    temp_file_path = temp_file.name
                
                # Process the image with OCR using preset if available, including message timestamp
                if config.DEFAULT_TABLE_PRESET and config.DEFAULT_TABLE_PRESET in config.TABLE_PRESETS:
                    results = self.ocr.process_image_with_preset(temp_file_path, config.DEFAULT_TABLE_PRESET)
                    # Add timestamp to results
                    if results['success'] and results['results']:
                        war_metadata = self.ocr.create_default_war_metadata(message.created_at)
                        for result in results['results']:
                            result.update(war_metadata)
                        results['war_metadata'] = war_metadata
                else:
                    results = self.ocr.process_image(temp_file_path, message.created_at)
                
                if not results['success']:
                    await processing_msg.edit(
                        content=f"❌ **Error processing image:**\n{results['error']}"
                    )
                    return
                
                if not results['results']:
                    await processing_msg.edit(
                        content="❌ **No clan member results found in this image.**\n"
                               "Make sure the image contains a clear table with clan member names and scores."
                    )
                    return
                
                # Check validation results
                validation = results.get('validation', {})
                if not validation.get('is_valid', True):
                    validation_errors = '\n'.join(validation.get('errors', []))
                    validation_warnings = '\n'.join(validation.get('warnings', []))
                    
                    error_text = "❌ **Validation Issues Found:**\n"
                    if validation_errors:
                        error_text += f"**Errors:**\n{validation_errors}\n"
                    if validation_warnings:
                        error_text += f"**Warnings:**\n{validation_warnings}\n"
                    error_text += "\nPlease check the image and try again, or use manual entry."
                    
                    await processing_msg.edit(content=error_text)
                    return
                
                # Format results for confirmation
                confirmation_text = self.format_enhanced_confirmation(
                    results['results'], 
                    validation, 
                    results.get('war_metadata')
                )
                
                # Create confirmation embed
                embed = discord.Embed(
                    title="🏁 Mario Kart Results Detected",
                    description=confirmation_text,
                    color=0x00ff00
                )
                embed.add_field(
                    name="❓ Confirmation Required",
                    value="React with ✅ to save these results or ❌ to cancel.",
                    inline=False
                )
                embed.set_footer(text=f"This confirmation expires in {config.CONFIRMATION_TIMEOUT} seconds")
                
                # Edit the processing message with confirmation
                await processing_msg.edit(content="", embed=embed)
                
                # Add reaction buttons
                await processing_msg.add_reaction("✅")
                await processing_msg.add_reaction("❌")
                await processing_msg.add_reaction("✏️")
                
                # Store pending confirmation data
                confirmation_data = {
                    'results': results['results'],
                    'original_message_id': str(message.id),
                    'user_id': message.author.id,
                    'channel_id': message.channel.id
                }
                
                self.pending_confirmations[str(processing_msg.id)] = confirmation_data
                # Note: New v2 database doesn't need pending confirmations table
                
                # Set up timeout
                await asyncio.sleep(config.CONFIRMATION_TIMEOUT)
                
                # Check if still pending
                if str(processing_msg.id) in self.pending_confirmations:
                    await self.handle_confirmation_timeout(processing_msg)
                
            finally:
                # Clean up temp file
                if temp_file and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
        except Exception as e:
            logging.error(f"Error processing race results image: {e}")
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
            results = confirmation_data['results']
            
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
            
        except Exception as e:
            logging.error(f"Error handling confirmation accept: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while saving results: {str(e)}",
                color=0xff0000
            )
            await message.edit(embed=embed)
    
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
                "`!mkadd PlayerName 85` - Add player with score\n"
                "`!mkremove PlayerName` - Remove player\n"
                "`!mkupdate PlayerName 92` - Update player's score\n"
                "`!mkshow` - Show current results\n"
                "`!mksave` - Save to database"
            ),
            inline=False
        )
        
        embed.set_footer(text="Edit the results using the commands above, then use !mksave")
        
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

    @commands.command(name='mkstats')
    async def view_player_stats(self, ctx, player_name: str = None):
        """View statistics for a specific player or all players."""
        try:
            if player_name:
                # Get specific player stats
                stats = self.db.get_player_stats(player_name)
                if stats:
                    embed = discord.Embed(
                        title=f"📊 Stats for {stats['main_name']}",
                        color=0x00ff00
                    )
                    
                    if stats['nicknames']:
                        embed.add_field(name="Nicknames", value=", ".join(stats['nicknames']), inline=False)
                    
                    embed.add_field(name="Total Score", value=stats['total_scores'], inline=True)
                    embed.add_field(name="Races Played", value=stats['total_races'], inline=True)
                    embed.add_field(name="Wars Completed", value=f"{stats['war_count']:.2f}", inline=True)
                    embed.add_field(name="Average Score", value=f"{stats['average_score']:.1f}", inline=True)
                    
                    # Show recent scores
                    if stats['score_history']:
                        recent_scores = stats['score_history'][-5:]  # Last 5 scores
                        embed.add_field(name="Recent Scores", value=str(recent_scores), inline=False)
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"❌ No stats found for player: {player_name}")
            else:
                # Get all player stats
                all_stats = self.db.get_all_players_stats()
                if all_stats:
                    embed = discord.Embed(
                        title="📊 All Player Statistics",
                        description="Ranked by average score per war",
                        color=0x00ff00
                    )
                    
                    for i, stats in enumerate(all_stats[:10], 1):  # Top 10
                        embed.add_field(
                            name=f"{i}. {stats['main_name']}",
                            value=f"Avg: {stats['average_score']:.1f} | Wars: {stats['war_count']:.2f} | Races: {stats['total_races']}",
                            inline=False
                        )
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ No player statistics found")
                    
        except Exception as e:
            logging.error(f"Error viewing stats: {e}")
            await ctx.send("❌ Error retrieving statistics")

    @commands.command(name='mkrecent')
    async def view_recent_results(self, ctx, limit: int = 5):
        """View recent race sessions."""
        try:
            sessions = self.db.get_recent_sessions(limit)
            
            if sessions:
                embed = discord.Embed(
                    title=f"🏁 Recent {len(sessions)} Race Sessions",
                    color=0x00ff00
                )
                
                for session in sessions:
                    session_info = f"**Date:** {session['session_date']}\n"
                    session_info += f"**Races:** {session['race_count']}\n"
                    session_info += f"**Players:** {len(session['results'])}\n"
                    session_info += f"**Saved:** {session['created_at']}\n\n"
                    
                    # Show player results
                    results_text = ""
                    for result in session['results'][:6]:  # Show first 6 players
                        results_text += f"{result['name']}: {result['score']}\n"
                    
                    if len(session['results']) > 6:
                        results_text += f"... and {len(session['results']) - 6} more"
                    
                    embed.add_field(
                        name=f"Session {session['session_date']}",
                        value=session_info + results_text,
                        inline=False
                    )
                
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No recent sessions found")
                
        except Exception as e:
            logging.error(f"Error viewing recent sessions: {e}")
            await ctx.send("❌ Error retrieving recent sessions")

    @commands.command(name='mkdbinfo')
    async def database_info(self, ctx):
        """Show database information and location."""
        try:
            info = self.db.get_database_info()
            
            if 'error' in info:
                await ctx.send(f"❌ Database error: {info['error']}")
                return
            
            embed = discord.Embed(
                title="🗃️ Database Information",
                color=0x00ff00
            )
            embed.add_field(name="Location", value=f"`{info['database_path']}`", inline=False)
            embed.add_field(name="File Size", value=f"{info['file_size_kb']:.1f} KB", inline=True)
            embed.add_field(name="Players", value=info['player_count'], inline=True)
            embed.add_field(name="Race Sessions", value=info['session_count'], inline=True)
            
            await ctx.send(embed=embed)
                
        except Exception as e:
            logging.error(f"Error getting database info: {e}")
            await ctx.send("❌ Error retrieving database information")

# Bot commands
@commands.command(name='stats')
async def player_stats(ctx, player_name: str = None):
    """Get player statistics."""
    try:
        if player_name:
            # Get specific player stats
            stats = ctx.bot.db.get_player_stats(player_name)
            if stats:
                embed = discord.Embed(
                    title=f"📊 Stats for {stats['name']}",
                    color=0x0099ff
                )
                embed.add_field(name="Total Score", value=stats['total_score'], inline=True)
                embed.add_field(name="Races Played", value=stats['race_count'], inline=True)
                embed.add_field(name="Average Score", value=f"{stats['average_score']:.2f}", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Player Not Found",
                    description=f"No stats found for player '{player_name}'",
                    color=0xff0000
                )
        else:
            # Get all player stats
            all_stats = ctx.bot.db.get_all_players_stats()
            if all_stats:
                embed = discord.Embed(
                    title="📊 Clan Leaderboard",
                    description="Average scores (highest to lowest)",
                    color=0x0099ff
                )
                
                leaderboard_text = ""
                for i, stats in enumerate(all_stats[:10], 1):  # Top 10
                    leaderboard_text += f"{i}. **{stats['name']}**: {stats['average_score']:.2f} avg ({stats['race_count']} races)\n"
                
                embed.add_field(name="Top Players", value=leaderboard_text, inline=False)
            else:
                embed = discord.Embed(
                    title="📊 No Stats Available",
                    description="No player statistics found in the database.",
                    color=0x999999
                )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logging.error(f"Error in stats command: {e}")
        await ctx.send("❌ An error occurred while retrieving stats.")



@commands.command(name='preset')
async def manage_preset(ctx, action: str = None, preset_name: str = None):
    """Manage table format presets."""
    if action == "list":
        embed = discord.Embed(
            title="📋 Available Table Presets",
            description="Saved table format presets for consistent OCR:",
            color=0x9932cc
        )
        
        if config.TABLE_PRESETS:
            for name, preset in config.TABLE_PRESETS.items():
                regions_count = len(preset.get('regions', []))
                embed.add_field(
                    name=f"🔖 {name}",
                    value=f"{preset.get('description', 'No description')}\n**Regions:** {regions_count}",
                    inline=False
                )
        else:
            embed.add_field(name="No Presets", value="No table presets saved yet.", inline=False)
        
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="📋 Preset Commands",
            description="Manage table format presets:",
            color=0x9932cc
        )
        embed.add_field(
            name="Commands",
            value="`!mkpreset list` - Show all saved presets",
            inline=False
        )
        await ctx.send(embed=embed)

@commands.command(name='teamroster')
async def show_team_roster(ctx, team: str = None):
    """Show specific team rosters."""
    if team and team.lower() == "first":
        embed = discord.Embed(
            title="👥 First Team Roster",
            description="First team members (alphabetical order):",
            color=0x0099ff
        )
        
        roster_text = "\n".join([f"• {name}" for name in config.FIRST_TEAM_ROSTER])
        embed.add_field(name="Members", value=roster_text, inline=False)
        embed.set_footer(text=f"Total: {len(config.FIRST_TEAM_ROSTER)} players")
        
    else:
        embed = discord.Embed(
            title="👥 Available Team Rosters",
            description="Available team rosters:",
            color=0x9932cc
        )
        embed.add_field(
            name="Teams",
            value="`!mkteamroster first` - Show first team roster",
            inline=False
        )
    
    await ctx.send(embed=embed)

@commands.command(name='manual')
async def manual_entry(ctx, *, war_data: str = None):
    """Manually enter war results when OCR fails."""
    if not war_data:
        embed = discord.Embed(
            title="📝 Manual War Entry",
            description="Use this command when OCR fails or for quick entry.",
            color=0x9932cc
        )
        embed.add_field(
            name="Format",
            value="`!mkmanual PlayerName1:85 PlayerName2:92 PlayerName3:78...`",
            inline=False
        )
        embed.add_field(
            name="Example", 
            value="`!mkmanual Cynical:85 DEMISE:92 Klefki:78 Quick:90 sopt:88 yukino:95`",
            inline=False
        )
        embed.add_field(
            name="Optional Parameters",
            value="Add `races:11` `date:2024-01-15` at the end if needed",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Parse manual entry
    try:
        results = []
        war_metadata = {
            'date': ctx.message.created_at.strftime('%Y-%m-%d'),
            'time': ctx.message.created_at.strftime('%H:%M:%S'),
            'race_count': config.DEFAULT_RACE_COUNT,
            'war_type': '6v6',
            'notes': 'Manual entry'
        }
        
        parts = war_data.split()
        for part in parts:
            if ':' in part:
                if part.startswith('races:'):
                    war_metadata['race_count'] = int(part.split(':')[1])
                elif part.startswith('date:'):
                    war_metadata['date'] = part.split(':')[1]
                else:
                    # Player:Score format
                    name, score = part.split(':', 1)
                    if name in config.CLAN_ROSTER:
                        results.append({
                            'name': name,
                            'score': int(score),
                            'raw_line': f"Manual: {name}:{score}",
                            **war_metadata
                        })
        
        if len(results) != config.EXPECTED_PLAYERS_PER_TEAM:
            await ctx.send(f"❌ Expected {config.EXPECTED_PLAYERS_PER_TEAM} players, got {len(results)}. Please check your entry.")
            return
        
        # Format for confirmation
        confirmation_text = ctx.bot.format_enhanced_confirmation(results, {'is_valid': True, 'warnings': []}, war_metadata)
        
        embed = discord.Embed(
            title="📝 Manual Entry Confirmation",
            description=confirmation_text,
            color=0x9932cc
        )
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        # Store for confirmation
        confirmation_data = {
            'results': results,
            'original_message_id': str(ctx.message.id),
            'user_id': ctx.author.id,
            'channel_id': ctx.channel.id
        }
        ctx.bot.pending_confirmations[str(msg.id)] = confirmation_data
        
    except Exception as e:
        await ctx.send(f"❌ Error parsing manual entry: {e}")

@commands.command(name='roster')
async def show_full_roster(ctx):
    """Show the complete clan roster."""
    embed = discord.Embed(
        title="👥 Complete Clan Roster",
        description=f"All {len(config.CLAN_ROSTER)} clan members:",
        color=0x9932cc
    )
    
    # Split roster into columns for better display
    mid_point = len(config.CLAN_ROSTER) // 2
    col1 = config.CLAN_ROSTER[:mid_point]
    col2 = config.CLAN_ROSTER[mid_point:]
    
    embed.add_field(
        name="Players (A-M)", 
        value="\n".join([f"• {name}" for name in col1]), 
        inline=True
    )
    embed.add_field(
        name="Players (M-Z)", 
        value="\n".join([f"• {name}" for name in col2]), 
        inline=True
    )
    embed.set_footer(text="Only results for these players will be saved from war images.")
    
    await ctx.send(embed=embed)

@commands.command(name='mkhelp')
async def bot_help(ctx):
    """Show bot help information."""
    embed = discord.Embed(
        title="🏁 MKWStatsBot Help",
        description="I automatically process Mario Kart war result images and track statistics!",
        color=0x00ff00
    )
    
    embed.add_field(
        name="📷 Automatic Processing",
        value="• Upload war result images\n"
              "• I extract player names, scores, and war metadata\n"
              "• Validates 6v6 format with confirmation\n"
              "• Saves to database automatically",
        inline=False
    )
    
    embed.add_field(
        name="🔧 Commands",
        value=(
            "`!mkstats [player]` - Show player stats or leaderboard\n"
            "`!mkroster` - Show complete clan roster\n"
            "`!mkmanual` - Manual war entry (when OCR fails)\n"
            "`!mkpreset list` - Show table format presets\n"
            "`!mkhelp` - Show this help message"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🏁 War Processing",
        value="• Detects 6v6 format (12 total players)\n"
              "• Extracts race count (usually 12)\n"
              "• Uses message timestamp for date/time\n"
              "• Validates player names against roster",
        inline=False
    )
    
    embed.add_field(
        name="✅ Confirmation System",
        value="✅ = Save to database\n❌ = Cancel\n✏️ = Manual edit (coming soon)",
        inline=False
    )
    
    await ctx.send(embed=embed)

@commands.command(name='mkadd')
async def add_player_to_edit(ctx, player_name: str = None, score: int = None):
    """Add a player to the current edit session."""
    if not hasattr(ctx.bot, 'edit_sessions') or ctx.author.id not in ctx.bot.edit_sessions:
        await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
        return
    
    if not player_name or score is None:
        await ctx.send("❌ Usage: `!mkadd PlayerName 85`")
        return
    
    edit_session = ctx.bot.edit_sessions[ctx.author.id]
    results = edit_session['results']
    
    # Check if player already exists
    for result in results:
        if result['name'].lower() == player_name.lower():
            await ctx.send(f"❌ Player {player_name} already exists. Use `!mkupdate` to change their score.")
            return
    
    # Add new player
    new_result = {
        'name': player_name,
        'score': score,
        'raw_line': f"Manual add: {player_name}:{score}",
        'preset_used': 'manual_edit'
    }
    results.append(new_result)
    
    await ctx.send(f"✅ Added {player_name}: {score}")

@commands.command(name='mkremove')
async def remove_player_from_edit(ctx, player_name: str = None):
    """Remove a player from the current edit session."""
    if not hasattr(ctx.bot, 'edit_sessions') or ctx.author.id not in ctx.bot.edit_sessions:
        await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
        return
    
    if not player_name:
        await ctx.send("❌ Usage: `!mkremove PlayerName`")
        return
    
    edit_session = ctx.bot.edit_sessions[ctx.author.id]
    results = edit_session['results']
    
    # Find and remove player
    for i, result in enumerate(results):
        if result['name'].lower() == player_name.lower():
            removed = results.pop(i)
            await ctx.send(f"✅ Removed {removed['name']}: {removed['score']}")
            return
    
    await ctx.send(f"❌ Player {player_name} not found in results.")

@commands.command(name='mkupdate')
async def update_player_score(ctx, player_name: str = None, score: int = None):
    """Update a player's score in the current edit session."""
    if not hasattr(ctx.bot, 'edit_sessions') or ctx.author.id not in ctx.bot.edit_sessions:
        await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
        return
    
    if not player_name or score is None:
        await ctx.send("❌ Usage: `!mkupdate PlayerName 92`")
        return
    
    edit_session = ctx.bot.edit_sessions[ctx.author.id]
    results = edit_session['results']
    
    # Find and update player
    for result in results:
        if result['name'].lower() == player_name.lower():
            old_score = result['score']
            result['score'] = score
            await ctx.send(f"✅ Updated {result['name']}: {old_score} → {score}")
            return
    
    await ctx.send(f"❌ Player {player_name} not found in results.")

@commands.command(name='mkshow')
async def show_current_edit(ctx):
    """Show current results in the edit session."""
    if not hasattr(ctx.bot, 'edit_sessions') or ctx.author.id not in ctx.bot.edit_sessions:
        await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
        return
    
    edit_session = ctx.bot.edit_sessions[ctx.author.id]
    results = edit_session['results']
    
    embed = discord.Embed(
        title="📊 Current Results",
        description=f"Showing {len(results)} players:",
        color=0x9932cc
    )
    
    results_text = ""
    for i, result in enumerate(results, 1):
        results_text += f"{i}. **{result['name']}**: {result['score']}\n"
    
    embed.add_field(name="Players", value=results_text or "No players", inline=False)
    embed.set_footer(text="Use !mksave when ready to save these results")
    
    await ctx.send(embed=embed)

@commands.command(name='mksave')
async def save_edited_results(ctx):
    """Save the edited results to the database."""
    if not hasattr(ctx.bot, 'edit_sessions') or ctx.author.id not in ctx.bot.edit_sessions:
        await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
        return
    
    edit_session = ctx.bot.edit_sessions[ctx.author.id]
    results = edit_session['results']
    
    if not results:
        await ctx.send("❌ No results to save.")
        return
    
    # Show saving message
    saving_msg = await ctx.send("💾 Saving results to database...")
    
    # Add message ID to results for tracking
    for result in results:
        result['message_id'] = edit_session['original_message_id']
    
    # Save to database
    success = ctx.bot.db.add_race_results(results)
    
    if success:
        embed = discord.Embed(
            title="✅ Results Saved Successfully!",
            description=f"Saved {len(results)} race results to database",
            color=0x00ff00
        )
        
        # Show what was saved with better formatting
        saved_list = []
        for result in results:
            saved_list.append(f"**{result['name']}**: {result['score']} points")
        
        embed.add_field(
            name="📊 Saved Results",
            value="\n".join(saved_list),
            inline=False
        )
        
        embed.add_field(
            name="💡 Next Steps",
            value="• Use `!mkstats` to view all player statistics\n• Use `!mkrecent` to see recent results\n• Use `!mkdbinfo` to see database info",
            inline=False
        )
        
        embed.set_footer(text="Player averages have been automatically updated")
        await saving_msg.edit(content="", embed=embed)
    else:
        await saving_msg.edit(content="❌ Failed to save results to database. Check logs for details.")
    
    # Clean up edit session
    del ctx.bot.edit_sessions[ctx.author.id]

# Add commands to bot
def setup_bot():
    bot = MarioKartBot()
    bot.add_command(player_stats)
    bot.add_command(show_full_roster)
    bot.add_command(manual_entry)
    bot.add_command(show_team_roster)
    bot.add_command(manage_preset)
    bot.add_command(bot_help)
    bot.add_command(add_player_to_edit)
    bot.add_command(remove_player_from_edit)
    bot.add_command(update_player_score)
    bot.add_command(show_current_edit)
    bot.add_command(save_edited_results)
    return bot

# Run the bot
if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("❌ Please set DISCORD_BOT_TOKEN environment variable")
        exit(1)
    
    bot = setup_bot()
    bot.run(config.DISCORD_TOKEN) 