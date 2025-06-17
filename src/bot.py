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
from src import config
from src.database import DatabaseManager
from src.ocr_processor import OCRProcessor

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
        
        super().__init__(command_prefix='!mk', intents=intents)
        
        self.db = DatabaseManager()
        self.ocr = OCRProcessor()
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
                
                # Process the image with OCR
                results = self.ocr.process_image(temp_file_path)
                
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
                confirmation_text = self.format_enhanced_confirmation(results['results'], validation)
                
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
                
                # Store pending confirmation data
                confirmation_data = {
                    'results': results['results'],
                    'original_message_id': str(message.id),
                    'user_id': message.author.id,
                    'channel_id': message.channel.id
                }
                
                self.pending_confirmations[str(processing_msg.id)] = confirmation_data
                self.db.store_pending_confirmation(str(processing_msg.id), json.dumps(confirmation_data))
                
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
            await message.clear_reactions()
            
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
        await message.clear_reactions()
        
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
        await message.clear_reactions()
        
        # Clean up pending confirmation
        self.cleanup_confirmation(str(message.id))
    
    def cleanup_confirmation(self, message_id: str):
        """Clean up confirmation data."""
        if message_id in self.pending_confirmations:
            del self.pending_confirmations[message_id]
        self.db.remove_pending_confirmation(message_id)
    
    def format_enhanced_confirmation(self, results: List[Dict], validation: Dict) -> str:
        """Format extracted results with validation info for confirmation."""
        if not results:
            return "No results found."
        
        formatted = "📊 **Extracted Race Results:**\n\n"
        
        # Validation status
        if validation.get('warnings'):
            formatted += "⚠️ **Warnings:**\n"
            for warning in validation['warnings']:
                formatted += f"• {warning}\n"
            formatted += "\n"
        
        # Results table with expected count indicator
        expected = config.EXPECTED_PLAYERS_PER_TEAM
        actual = len(results)
        formatted += f"**Player Scores ({actual}/{expected} players):**\n"
        
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result['name']}**: {result['score']}\n"
        
        # Add confirmation instructions
        formatted += f"\n**Please verify these {actual} players and scores are correct.**"
        formatted += "\n✅ = Save to database | ❌ = Cancel"
        
        return formatted

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

@commands.command(name='roster')
async def show_roster(ctx):
    """Show the clan roster."""
    embed = discord.Embed(
        title="👥 Clan Roster",
        description="Current clan members being tracked:",
        color=0x9932cc
    )
    
    roster_text = "\n".join([f"• {name}" for name in config.CLAN_ROSTER])
    embed.add_field(name="Members", value=roster_text, inline=False)
    embed.set_footer(text="Only results for these players will be saved from race images.")
    
    await ctx.send(embed=embed)

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

@commands.command(name='help')
async def bot_help(ctx):
    """Show bot help information."""
    embed = discord.Embed(
        title="🏁 Mario Kart Results Bot Help",
        description="I automatically process Mario Kart race result images!",
        color=0x00ff00
    )
    
    embed.add_field(
        name="📷 Image Processing",
        value="Just upload an image with race results and I'll extract the data automatically!\n"
              "I'll validate that exactly 6 players are found before asking for confirmation.",
        inline=False
    )
    
    embed.add_field(
        name="🔧 Commands",
        value=(
            "`!mkstats [player]` - Show player stats (or leaderboard if no player specified)\n"
            "`!mkroster` - Show main clan roster\n"
            "`!mkteamroster [team]` - Show specific team rosters\n"
            "`!mkpreset [action]` - Manage table format presets\n"
            "`!mkhelp` - Show this help message"
        ),
        inline=False
    )
    
    embed.add_field(
        name="✅ Validation & Confirmation",
        value="• I check for exactly 6 players per team\n"
              "• I warn about unusual scores or duplicates\n"
              "• React ✅ to save results or ❌ to cancel",
        inline=False
    )
    
    embed.add_field(
        name="💾 Data Storage",
        value="All data is saved to a SQLite database file that persists between bot restarts.",
        inline=False
    )
    
    await ctx.send(embed=embed)

# Add commands to bot
def setup_bot():
    bot = MarioKartBot()
    bot.add_command(player_stats)
    bot.add_command(show_roster)
    bot.add_command(show_team_roster)
    bot.add_command(manage_preset)
    bot.add_command(bot_help)
    return bot

# Run the bot
if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("❌ Please set DISCORD_BOT_TOKEN environment variable")
        exit(1)
    
    bot = setup_bot()
    bot.run(config.DISCORD_TOKEN) 