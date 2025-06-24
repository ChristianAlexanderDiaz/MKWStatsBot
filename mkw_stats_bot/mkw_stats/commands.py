import discord
from discord.ext import commands
import logging
from . import config

class MarioKartCommands(commands.Cog):
    """Mario Kart bot commands organized in a cog."""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='mkstats')
    async def view_player_stats(self, ctx, player_name: str = None):
        """View statistics for a specific player or all players."""
        try:
            if player_name:
                # Get specific player stats
                stats = self.bot.db.get_player_stats(player_name)
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
                all_stats = self.bot.db.get_all_players_stats()
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
            sessions = self.bot.db.get_recent_sessions(limit)
            
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
            info = self.bot.db.get_database_info()
            
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

    @commands.command(name='mkpreset')
    async def manage_preset(self, ctx, action: str = None, preset_name: str = None):
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

    @commands.command(name='mkteamroster')
    async def show_team_roster(self, ctx, team: str = None):
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

    @commands.command(name='mkmanual')
    async def manual_entry(self, ctx, *, war_data: str = None):
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
            confirmation_text = self.bot.format_enhanced_confirmation(results, {'is_valid': True, 'warnings': []}, war_metadata)
            
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
            self.bot.pending_confirmations[str(msg.id)] = confirmation_data
            
        except Exception as e:
            await ctx.send(f"❌ Error parsing manual entry: {e}")

    @commands.command(name='mkroster')
    async def show_full_roster(self, ctx):
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
    async def bot_help(self, ctx):
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
            value="✅ = Save to database\n❌ = Cancel\n✏️ = Manual edit",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.command(name='mkadd')
    async def add_player_to_edit(self, ctx, player_name: str = None, score: int = None):
        """Add a player to the current edit session."""
        if not hasattr(self.bot, 'edit_sessions') or ctx.author.id not in self.bot.edit_sessions:
            await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
            return
        
        if not player_name or score is None:
            await ctx.send("❌ Usage: `!mkadd PlayerName 85`")
            return
        
        edit_session = self.bot.edit_sessions[ctx.author.id]
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
    async def remove_player_from_edit(self, ctx, player_name: str = None):
        """Remove a player from the current edit session."""
        if not hasattr(self.bot, 'edit_sessions') or ctx.author.id not in self.bot.edit_sessions:
            await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
            return
        
        if not player_name:
            await ctx.send("❌ Usage: `!mkremove PlayerName`")
            return
        
        edit_session = self.bot.edit_sessions[ctx.author.id]
        results = edit_session['results']
        
        # Find and remove player
        for i, result in enumerate(results):
            if result['name'].lower() == player_name.lower():
                removed = results.pop(i)
                await ctx.send(f"✅ Removed {removed['name']}: {removed['score']}")
                return
        
        await ctx.send(f"❌ Player {player_name} not found in results.")

    @commands.command(name='mkupdate')
    async def update_player_score(self, ctx, player_name: str = None, score: int = None):
        """Update a player's score in the current edit session."""
        if not hasattr(self.bot, 'edit_sessions') or ctx.author.id not in self.bot.edit_sessions:
            await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
            return
        
        if not player_name or score is None:
            await ctx.send("❌ Usage: `!mkupdate PlayerName 92`")
            return
        
        edit_session = self.bot.edit_sessions[ctx.author.id]
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
    async def show_current_edit(self, ctx):
        """Show current results in the edit session."""
        if not hasattr(self.bot, 'edit_sessions') or ctx.author.id not in self.bot.edit_sessions:
            await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
            return
        
        edit_session = self.bot.edit_sessions[ctx.author.id]
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
    async def save_edited_results(self, ctx):
        """Save the edited results to the database."""
        if not hasattr(self.bot, 'edit_sessions') or ctx.author.id not in self.bot.edit_sessions:
            await ctx.send("❌ No active edit session. React with ✏️ to an OCR result first.")
            return
        
        edit_session = self.bot.edit_sessions[ctx.author.id]
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
        success = self.bot.db.add_race_results(results)
        
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
        del self.bot.edit_sessions[ctx.author.id]

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(MarioKartCommands(bot)) 