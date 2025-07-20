import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import json
import functools

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

class MarioKartCommands(commands.Cog):
    """Mario Kart bot commands organized in a cog."""
    
    def __init__(self, bot):
        self.bot = bot
    
    def get_guild_id(self, ctx):
        """Helper method to get guild ID from context."""
        return ctx.guild.id if ctx.guild else 0
    
    def get_guild_id_from_interaction(self, interaction: discord.Interaction) -> int:
        """Get guild ID from interaction, similar to get_guild_id but for interactions."""
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

    @app_commands.command(name="setup", description="Initialize guild for Mario Kart stats tracking")
    @app_commands.describe(
        teamname="Name for the first team",
        players="Players to add (comma-separated): 'Player1, Player2, Player3'"
    )
    async def setup_guild(self, interaction: discord.Interaction, teamname: str, players: str):
        """Initialize guild with basic setup."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            
            # Check if already initialized
            if self.is_guild_initialized(guild_id):
                await interaction.response.send_message("✅ Guild is already set up! Use other commands to manage your clan.", ephemeral=True)
                return
            
            # Parse players from comma-separated string
            player_list = [p.strip() for p in players.split(',')]
            player_list = [p for p in player_list if p]  # Remove empty strings
            
            # Validate at least one player
            if not player_list:
                await interaction.response.send_message("❌ You must provide at least one player.", ephemeral=True)
                return
            
            # Auto-detect server name from Discord
            servername = interaction.guild.name if interaction.guild else f"Guild {guild_id}"
            
            with self.bot.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. Create guild config
                cursor.execute("""
                    INSERT INTO guild_configs (guild_id, guild_name, team_names, allowed_channels, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        is_active = EXCLUDED.is_active,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, servername, json.dumps([teamname]), json.dumps([]), True))
                
                # 2. Add all players to players table
                added_players = []
                for player_name in player_list:
                    cursor.execute("""
                        INSERT INTO players (player_name, added_by, guild_id, team, nicknames, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (player_name, guild_id) DO UPDATE SET
                            is_active = TRUE,
                            team = EXCLUDED.team,
                            updated_at = CURRENT_TIMESTAMP
                    """, (player_name, f"setup_{interaction.user.name}", guild_id, teamname, [], True))
                    added_players.append(player_name)
                
                conn.commit()
            
            # Create success response
            embed = discord.Embed(
                title="🚀 Guild Setup Complete!",
                description=f"Successfully initialized **{servername}** for Mario Kart clan tracking.",
                color=0x00ff00
            )
            
            embed.add_field(name="Server Name", value=servername, inline=True)
            embed.add_field(name="Guild ID", value=str(guild_id), inline=True)
            embed.add_field(name="Team Name", value=teamname, inline=True)
            embed.add_field(name="Players Added", value=f"{len(added_players)} players", inline=True)
            
            # Show all added players
            players_text = ", ".join(added_players)
            if len(players_text) > 1000:  # Discord field limit
                players_text = players_text[:1000] + "..."
            embed.add_field(name="👥 Team Roster", value=players_text, inline=False)
            
            embed.add_field(
                name="🎯 Next Steps",
                value=(
                    "• Add more players: `!mkadd <player>`\n"
                    "• Start tracking wars: `/addwar`\n"
                    "• View stats: `!S [player]`\n"
                    "• Manage teams: `!mkassignteam`"
                ),
                inline=False
            )
            
            embed.set_footer(text="Your guild is now ready for Mario Kart clan management!")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error in guild setup: {e}")
            await interaction.response.send_message("❌ Error setting up guild. Please try again or contact support.", ephemeral=True)

    def parse_quoted_nicknames(self, text: str) -> list:
        """
        Parse nicknames from text, handling quoted strings for nicknames with spaces.
        
        Examples:
        - 'Vort VortexNickname' -> ['Vort', 'VortexNickname']
        - '"MK Vortex" Vort' -> ['MK Vortex', 'Vort']
        - 'Vort "MK Vortex" "Another Name"' -> ['Vort', 'MK Vortex', 'Another Name']
        """
        import re
        
        nicknames = []
        # Pattern to match quoted strings or unquoted words
        pattern = r'"([^"]+)"|(\S+)'
        
        matches = re.findall(pattern, text.strip())
        
        for match in matches:
            # match[0] is quoted content, match[1] is unquoted content
            nickname = match[0] if match[0] else match[1]
            if nickname:  # Skip empty matches
                nicknames.append(nickname)
        
        return nicknames

    @app_commands.command(name="stats", description="View player statistics or leaderboard")
    @app_commands.describe(player="Player name to view stats for (optional - shows leaderboard if empty)")
    @require_guild_setup
    async def stats_slash(self, interaction: discord.Interaction, player: str = None):
        """View statistics for a specific player or all players."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            if player:
                # Resolve nickname to actual player name first
                resolved_player = self.bot.db.resolve_player_name(player, guild_id)
                if not resolved_player:
                    await interaction.response.send_message(f"❌ No player found with name or nickname: {player}", ephemeral=True)
                    return
                
                # Get specific player stats from players table using resolved name
                stats = self.bot.db.get_player_statistics(resolved_player, guild_id)
                if stats:
                    # Create an embed for the player's stats
                    embed = discord.Embed(
                        title=f"📊 Stats for {stats['player_name']}",
                        color=0x00ff00
                    )
                    
                    # Player info section
                    team_name = stats.get('team', 'Unassigned')
                    embed.add_field(name="Team", value=team_name, inline=True)
                    
                    # Optional nicknames - only show if they exist
                    if stats.get('nicknames'):
                        embed.add_field(name="Nicknames", value=", ".join(stats['nicknames']), inline=True)
                    
                    # Average score (most important stat first)
                    embed.add_field(name="Average Score", value=f"{stats.get('average_score', 0.0):.1f} points", inline=True)
                    
                    # War statistics
                    war_count = float(stats.get('war_count', 0))
                    if war_count == 1.0:
                        wars_text = f"{war_count:.1f} war"
                    else:
                        wars_text = f"{war_count:.1f} wars"
                    
                    embed.add_field(name="Wars Played", value=wars_text, inline=True)
                    embed.add_field(name="Total Score", value=f"{stats.get('total_score', 0):,} points", inline=True)
                    embed.add_field(name="Total Races", value=str(stats.get('total_races', 0)), inline=True)
                    
                    # Format date to human readable format
                    if stats.get('last_war_date'):
                        from datetime import datetime
                        try:
                            # Parse the date and format it nicely
                            date_obj = datetime.strptime(stats['last_war_date'], '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%b %d, %Y')
                            embed.add_field(name="Last War", value=formatted_date, inline=True)
                        except:
                            # Fallback to original format if parsing fails
                            embed.add_field(name="Last War", value=stats['last_war_date'], inline=True)
                    else:
                        embed.add_field(name="Last War", value="No wars yet", inline=True)
                    
                    await interaction.response.send_message(embed=embed)
                else:
                    # Check if player exists in players table but has no stats yet
                    roster_stats = self.bot.db.get_player_stats(resolved_player, guild_id)
                    if roster_stats:
                        embed = discord.Embed(
                            title=f"📊 Stats for {roster_stats['player_name']}",
                            description="This player is in the roster but hasn't participated in any wars yet.",
                            color=0xff9900
                        )
                        
                        team_name = roster_stats.get('team', 'Unassigned')
                        embed.add_field(name="Team", value=team_name, inline=True)
                        
                        if roster_stats.get('nicknames'):
                            embed.add_field(name="Nicknames", value=", ".join(roster_stats['nicknames']), inline=True)
                        
                        embed.add_field(name="Wars Played", value="0", inline=True)
                        embed.set_footer(text="Use /addwar to add this player to a war")
                        
                        await interaction.response.send_message(embed=embed)
                    else:
                        await interaction.response.send_message(f"❌ No stats found for player: {player}", ephemeral=True)
            else:
                # Get all player statistics from players table
                # First get all players
                roster_stats = self.bot.db.get_all_players_stats(guild_id)
                
                if not roster_stats:
                    await interaction.response.send_message("❌ No players found in players table.", ephemeral=True)
                    return
                
                # Get war statistics for players who have them
                players_with_stats = []
                players_without_stats = []
                
                for roster_player in roster_stats:
                    war_stats = self.bot.db.get_player_statistics(roster_player['player_name'], guild_id)
                    if war_stats:
                        players_with_stats.append(war_stats)
                    else:
                        players_without_stats.append(roster_player)
                
                # Sort players with stats by average score (descending)
                players_with_stats.sort(key=lambda x: x.get('average_score', 0), reverse=True)
                
                # Combine and sort all players - those with stats first, then without stats
                all_players = players_with_stats + players_without_stats
                
                # Create simple embed for slash command (no pagination for now)
                embed = discord.Embed(
                    title="📊 Player Statistics Leaderboard",
                    color=0x00ff00
                )
                
                # Show all players
                display_players = all_players
                leaderboard_text = []
                
                for i, player in enumerate(display_players, 1):
                    if player.get('war_count', 0) > 0:
                        avg_score = player.get('average_score', 0.0)
                        war_count = float(player.get('war_count', 0))
                        
                        # Format war count with 1 decimal place and proper singular/plural
                        if war_count == 1.0:
                            war_display = f"{war_count:.1f} war"
                        else:
                            war_display = f"{war_count:.1f} wars"
                        
                        leaderboard_text.append(f"{i}. **{player['player_name']}** - {avg_score:.1f} avg ({war_display})")
                    else:
                        leaderboard_text.append(f"{i}. **{player['player_name']}** - No wars yet")
                
                embed.add_field(
                    name="Top Players",
                    value="\n".join(leaderboard_text) if leaderboard_text else "No player data available",
                    inline=False
                )
                
                embed.set_footer(text=f"Showing all {len(all_players)} players.")
                
                await interaction.response.send_message(embed=embed)
                
        except Exception as e:
            logging.error(f"Error in stats command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred while retrieving stats.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred while retrieving stats.", ephemeral=True)





    @app_commands.command(name="roster", description="Show complete guild roster organized by teams")
    @require_guild_setup
    async def show_full_roster(self, interaction: discord.Interaction):
        """Show the complete clan roster organized by teams."""
        try:
            # Get guild id 
            guild_id = self.get_guild_id(interaction)
            # Get all players with their team and nickname info
            all_players = self.bot.db.get_all_players_stats(guild_id)
            
            if not all_players:
                await interaction.response.send_message("❌ No players found in players table. Use `/addplayer <player>` to add players.")
                return
            
            embed = discord.Embed(
                title="👥 Complete Clan Roster",
                description=f"All {len(all_players)} clan members organized by teams:",
                color=0x9932cc
            )
            
            # Group players by team
            teams = {}
            for player in all_players:
                team = player.get('team', 'Unassigned')
                if team not in teams:
                    teams[team] = []
                teams[team].append(player)
            
            # Display each team
            for team_name, players in teams.items():
                if players:  # Only show teams with players
                    player_list = []
                    
                    for player in players:
                        nickname_count = len(player.get('nicknames', []))
                        nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                        player_list.append(f"• **{player['player_name']}**{nickname_text}")
                    
                    embed.add_field(
                        name=f"{team_name} ({len(players)} players)",
                        value="\n".join(player_list),
                        inline=False
                    )
            
            embed.set_footer(text="Use /showallteams for detailed team view | Only results for these players will be saved from war images.")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing roster: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving roster", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving roster", ephemeral=True)

    @app_commands.command(name="addplayer", description="Add a player to the clan roster")
    @app_commands.describe(player_name="Name of the player to add to the roster")
    @require_guild_setup
    async def add_player_to_roster(self, interaction: discord.Interaction, player_name: str):
        """Add a player to the clan roster."""
        try:
            guild_id = self.get_guild_id(interaction)
            # Add player to players table
            success = self.bot.db.add_roster_player(player_name, str(interaction.user), guild_id)
            
            if success:
                await interaction.response.send_message(f"✅ Added **{player_name}** to the clan roster!")
            else:
                await interaction.response.send_message(f"❌ **{player_name}** is already in the players table or couldn't be added.")
                
        except Exception as e:
            logging.error(f"Error adding player to roster: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error adding player to roster", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error adding player to roster", ephemeral=True)

    @app_commands.command(name="removeplayer", description="Remove a player from the clan roster")
    @app_commands.describe(player_name="Name of the player to remove from the roster")
    @require_guild_setup
    async def remove_player_from_roster(self, interaction: discord.Interaction, player_name: str):
        """Remove a player from the clan roster."""
        try:
            guild_id = self.get_guild_id(interaction)
            # Remove player from players table
            success = self.bot.db.remove_roster_player(player_name, guild_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Player Removed",
                    description=f"Removed **{player_name}** from the active players table.",
                    color=0xff4444
                )
                embed.add_field(
                    name="Note",
                    value="This marks the player as inactive but keeps their stats.",
                    inline=False
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ **{player_name}** is not in the active players table or couldn't be removed.")
                
        except Exception as e:
            logging.error(f"Error removing player from roster: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error removing player from roster", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error removing player from roster", ephemeral=True)

    @app_commands.command(name="help", description="Show bot help information")
    @require_guild_setup
    async def help_command(self, interaction: discord.Interaction):
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
            name="🔧 Player & Roster Commands",
            value=(
                "`/stats [player]` - Show player stats or leaderboard\n"
                "`/roster` - Show complete clan roster by teams\n"
                "`/addplayer <player>` - Add player to roster\n"
                "`/removeplayer <player>` - Remove player from roster"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚔️ War Management Commands",
            value=(
                "`/addwar` - Add war with player scores\n"
                "📷 Upload images for automatic OCR processing"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👥 Team Management Commands",
            value=(
                "`/addteam <team_name>` - Create a new team\n"
                "`/removeteam <team_name>` - Remove a team\n"
                "`/renameteam <old_name> <new_name>` - Rename a team\n"
                "`/showallteams` - Show all teams and their players\n"
                "`/assignplayerstoteam <team> <player1> <player2>...` - Assign multiple players to team\n"
                "`/assignplayertoteam <player> <team>` - Assign single player to team\n"
                "`/unassignplayerfromteam <player>` - Set player to Unassigned\n"
                "`/showspecificteamroster <team>` - Show specific team roster"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🏷️ Nickname Management Commands",
            value=(
                "`/addnickname <player> <nickname>` - Add nickname to player\n"
                "`/removenickname <player> <nickname>` - Remove nickname from player\n"
                "`/nicknamesfor <player>` - Show all nicknames for player\n"
                "💡 Nicknames help with OCR recognition of player names"
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
        
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="assignplayertoteam", description="Assign a single player to a team")
    @app_commands.describe(player_name="Name of the player to assign", team_name="Team to assign the player to")
    @require_guild_setup
    async def assign_single_player_to_team(self, interaction: discord.Interaction, player_name: str, team_name: str):
        """Assign a single player to a team."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Validate team name
            valid_teams = self.bot.db.get_guild_team_names(guild_id)
            valid_teams.append('Unassigned')  # Always allow Unassigned
            if team_name not in valid_teams:
                await interaction.response.send_message(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}")
                return
            
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table. Use `/addplayer {player_name}` to add them first.")
                return
            
            # Assign team
            success = self.bot.db.set_player_team(resolved_player, team_name, guild_id)
            
            if success:
                await interaction.response.send_message(f"✅ Assigned **{resolved_player}** to team **{team_name}**!")
            else:
                await interaction.response.send_message(f"❌ Failed to assign **{resolved_player}** to team **{team_name}**.")
                
        except Exception as e:
            logging.error(f"Error assigning player to team: {e}")
            try:
                await interaction.response.send_message("❌ Error assigning player to team", ephemeral=True)
            except:
                await interaction.followup.send("❌ Error assigning player to team", ephemeral=True)

    @app_commands.command(name="assignplayerstoteam", description="Assign multiple players to a team")
    @app_commands.describe(team_name="Team to assign players to", players="Space-separated list of player names (minimum 1 player)")
    @require_guild_setup
    async def assign_players_to_team(self, interaction: discord.Interaction, team_name: str, players: str):
        """Assign multiple players to a team."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Parse player names from space-separated string
            player_names = players.strip().split()
            if len(player_names) == 0:
                await interaction.response.send_message("❌ Please provide at least one player name.")
                return
            
            # Validate team name
            valid_teams = self.bot.db.get_guild_team_names(guild_id)
            valid_teams.append('Unassigned')  # Always allow Unassigned
            if team_name not in valid_teams:
                await interaction.response.send_message(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}\nUse `/showallteams` to see available teams or `/addteam` to create new teams.")
                return
            
            # Resolve all player names first
            resolved_players = []
            failed_players = []
            
            for player_name in player_names:
                resolved = self.bot.db.resolve_player_name(player_name, guild_id)
                if resolved:
                    resolved_players.append(resolved)
                else:
                    failed_players.append(player_name)
            
            if failed_players:
                await interaction.response.send_message(f"❌ These players were not found in players table: {', '.join(failed_players)}\nUse `/addplayer <player>` to add them first.")
                return
            
            # Assign all players to team
            successful_assignments = []
            failed_assignments = []
            
            for player in resolved_players:
                success = self.bot.db.set_player_team(player, team_name, guild_id)
                if success:
                    successful_assignments.append(player)
                else:
                    failed_assignments.append(player)
            
            # Create response embed
            embed = discord.Embed(
                title="👥 Team Assignment Results",
                color=0x00ff00 if not failed_assignments else 0xff4444
            )
            
            if successful_assignments:
                embed.add_field(
                    name=f"✅ Successfully assigned to **{team_name}**",
                    value="\n".join([f"• {player}" for player in successful_assignments]),
                    inline=False
                )
            
            if failed_assignments:
                embed.add_field(
                    name="❌ Failed to assign",
                    value="\n".join([f"• {player}" for player in failed_assignments]),
                    inline=False
                )
            
            embed.add_field(
                name="Summary",
                value=f"Successfully assigned: {len(successful_assignments)}\nFailed: {len(failed_assignments)}",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
                
        except Exception as e:
            logging.error(f"Error assigning players to team: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error assigning players to team", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error assigning players to team", ephemeral=True)

    @app_commands.command(name="unassignplayerfromteam", description="Unassign a player from their team (set to Unassigned)")
    @app_commands.describe(player_name="Name of the player to unassign from their team")
    @require_guild_setup
    async def unassign_player_from_team(self, interaction: discord.Interaction, player_name: str):
        """Unassign a player from their team (set to Unassigned)."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return
            
            # Set team to Unassigned
            success = self.bot.db.set_player_team(resolved_player, 'Unassigned', guild_id)
            
            if success:
                await interaction.response.send_message(f"✅ Set **{resolved_player}** to **Unassigned**!")
            else:
                await interaction.response.send_message(f"❌ Failed to unassign **{resolved_player}** from team.")
                
        except Exception as e:
            logging.error(f"Error unassigning player from team: {e}")
            try:
                await interaction.response.send_message("❌ Error unassigning player from team", ephemeral=True)
            except:
                await interaction.followup.send("❌ Error unassigning player from team", ephemeral=True)

    @app_commands.command(name="showallteams", description="Show all players organized by teams")
    @require_guild_setup
    async def show_teams(self, interaction: discord.Interaction):
        """Show all players organized by teams."""
        try:
            guild_id = self.get_guild_id(interaction)
            teams = self.bot.db.get_players_by_team(guild_id=guild_id)
            
            if not teams:
                await interaction.response.send_message("❌ No players found in players table. Use `/addplayer` to add players.")
                return
            
            embed = discord.Embed(
                title="👥 Team Rosters",
                description="Players organized by team assignment:",
                color=0x9932cc
            )
            
            # Define team colors
            team_colors = {
                'Phantom Orbit': '🔮',
                'Moonlight Bootel': '🌙', 
                'Unassigned': '❓'
            }
            
            total_players = 0
            for team_name, players in teams.items():
                if players:  # Only show teams with players
                    icon = team_colors.get(team_name, '👥')
                    player_list = "\n".join([f"• {player}" for player in players])
                    
                    embed.add_field(
                        name=f"{icon} {team_name} ({len(players)} players)",
                        value=player_list,
                        inline=True
                    )
                    total_players += len(players)
            
            embed.set_footer(text=f"Total players: {total_players} | Use /showspecificteamroster to view a specific team")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing teams: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving team information", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving team information", ephemeral=True)

    @app_commands.command(name="showspecificteamroster", description="Show roster for a specific team")
    @app_commands.describe(team_name="Name of the team to show roster for")
    @require_guild_setup
    async def show_team_roster(self, interaction: discord.Interaction, team_name: str):
        """Show roster for a specific team."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Validate team name
            valid_teams = self.bot.db.get_guild_team_names(guild_id)
            valid_teams.append('Unassigned')  # Always allow Unassigned
            if team_name not in valid_teams:
                await interaction.response.send_message(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}\nUse `/showallteams` to see available teams.")
                return
            
            team_players = self.bot.db.get_team_roster(team_name, guild_id)
            
            embed = discord.Embed(
                title=f"{team_name} Roster",
                description=f"Players in team {team_name}:",
                color=0x9932cc
            )
            
            if team_players:
                # Get detailed stats for team members
                detailed_players = []
                for player in team_players:
                    player_stats = self.bot.db.get_player_stats(player, guild_id)
                    if player_stats:
                        nicknames = player_stats.get('nicknames', [])
                        nickname_text = f" ({', '.join(nicknames)})" if nicknames else ""
                        detailed_players.append(f"• **{player}**{nickname_text}")
                    else:
                        detailed_players.append(f"• **{player}**")
                
                embed.add_field(
                    name=f"Team Members ({len(team_players)})",
                    value="\n".join(detailed_players),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Team Members",
                    value="No players assigned to this team.",
                    inline=False
                )
            
            embed.set_footer(text=f"Use /assignplayerstoteam {team_name} <players> to assign players to this team")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing team roster: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving team roster", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving team roster", ephemeral=True)

    @app_commands.command(name="addnickname", description="Add a nickname to a player for OCR recognition")
    @app_commands.describe(player_name="Player to add nickname for", nickname="Nickname to add")
    @require_guild_setup
    async def add_nickname(self, interaction: discord.Interaction, player_name: str, nickname: str):
        """Add a single nickname to a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table. Use `/addplayer {player_name}` to add them first.")
                return
            
            # Check if nickname is just a case variation of the player name
            if nickname.lower() == resolved_player.lower():
                await interaction.response.send_message(f"❌ No need to add **{nickname}** as a nickname for **{resolved_player}** - name matching is case-insensitive!", ephemeral=True)
                return
            
            # Add single nickname
            success = self.bot.db.add_nickname(resolved_player, nickname, guild_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Nickname Added!",
                    description=f"Added nickname **{nickname}** to **{resolved_player}**",
                    color=0x00ff00
                )
                embed.add_field(
                    name="Purpose",
                    value="Nicknames help OCR recognize players when their names appear differently in race results.",
                    inline=False
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ Nickname **{nickname}** already exists for **{resolved_player}** or couldn't be added.")
                
        except Exception as e:
            logging.error(f"Error adding nickname: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error adding nickname", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error adding nickname", ephemeral=True)


    @app_commands.command(name="removenickname", description="Remove a nickname from a player")
    @app_commands.describe(player_name="Player to remove nickname from", nickname="Nickname to remove")
    @require_guild_setup
    async def remove_nickname(self, interaction: discord.Interaction, player_name: str, nickname: str):
        """Remove a nickname from a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return
            
            # Remove nickname
            success = self.bot.db.remove_nickname(resolved_player, nickname, guild_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Nickname Removed!",
                    description=f"Removed nickname **{nickname}** from **{resolved_player}**",
                    color=0xff4444
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ Nickname **{nickname}** not found for **{resolved_player}** or couldn't be removed.")
                
        except Exception as e:
            logging.error(f"Error removing nickname: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error removing nickname", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error removing nickname", ephemeral=True)

    @app_commands.command(name="nicknamesfor", description="Show all nicknames for a player")
    @app_commands.describe(player_name="Player to show nicknames for")
    @require_guild_setup
    async def show_nicknames(self, interaction: discord.Interaction, player_name: str):
        """Show all nicknames for a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return
            
            # Get nicknames
            nicknames = self.bot.db.get_player_nicknames(resolved_player, guild_id)
            
            embed = discord.Embed(
                title=f"🏷️ Nicknames for {resolved_player}",
                color=0x9932cc
            )
            
            if nicknames:
                embed.description = "\n".join([f"• {nickname}" for nickname in nicknames])
            else:
                embed.description = "No nicknames set for this player."
            
            embed.set_footer(text=f"Use /addnickname {resolved_player} <nickname> to add more nicknames")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing nicknames: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving nicknames", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving nicknames", ephemeral=True)

    @app_commands.command(name="addwar", description="Add a war with player scores")
    @app_commands.describe(
        player_scores="Player scores in format: 'Player1: 104, Player2: 105, Player3: 50'",
        races="Number of races played (1-12, default: 12)"
    )
    async def addwar_slash(self, interaction: discord.Interaction, player_scores: str, races: int = 12):
        """Add a war manually with player scores using slash command."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            
            # Check if guild is initialized
            if not self.is_guild_initialized(guild_id):
                await interaction.response.send_message("❌ Guild not set up! Please run `/setup` first to initialize your clan.", ephemeral=True)
                return
            
            # Validate race count
            if races < 1 or races > 12:
                await interaction.response.send_message("❌ Race count must be between 1 and 12.", ephemeral=True)
                return
            
            # Parse player scores
            results = []
            
            # Split by comma and clean up spaces
            parts = [p.strip() for p in player_scores.split(',')]
            
            for part in parts:
                if ':' in part:
                    try:
                        name, score_str = part.split(':', 1)
                        name = name.strip()
                        original_name = name  # Store original before parsing
                        score = int(score_str.strip())
                        
                        # Check for individual race count in parentheses
                        individual_races = races  # Default to war race count
                        if '(' in name and ')' in name:
                            # Extract: "Stickman(7)" -> name="Stickman", individual_races=7
                            base_name = name[:name.index('(')].strip()
                            race_count_str = name[name.index('(')+1:name.index(')')].strip()
                            try:
                                individual_races = int(race_count_str)
                                name = base_name
                                
                                # Validate individual race count  
                                if individual_races < 1:
                                    await interaction.response.send_message(f"❌ Invalid race count for {base_name}: {individual_races}. Must be at least 1.", ephemeral=True)
                                    return
                                elif individual_races >= races:
                                    if individual_races == races:
                                        await interaction.response.send_message(f"❌ {base_name}({individual_races}): If they played all {races} races, use `{base_name}: {score}` instead (no parentheses).", ephemeral=True)
                                    else:
                                        await interaction.response.send_message(f"❌ {base_name}({individual_races}): Cannot play {individual_races} races when war only has {races} races total.", ephemeral=True)
                                    return
                            except ValueError:
                                await interaction.response.send_message(f"❌ Invalid race count format in: `{name}`. Use PlayerName(races): Score.", ephemeral=True)
                                return
                        
                        # Dynamic score validation based on races played
                        min_score = individual_races * 1  # All last place (1 point per race)
                        max_score = individual_races * 15  # All first place (15 points per race)
                        if score < min_score or score > max_score:
                            if '(' in original_name and ')' in original_name:
                                await interaction.response.send_message(f"❌ {base_name}({individual_races}): {score} points invalid. Must be {min_score}-{max_score} points for {individual_races} races.", ephemeral=True)
                            else:
                                await interaction.response.send_message(f"❌ {name}: {score} points invalid. Must be {min_score}-{max_score} points for {individual_races} races.", ephemeral=True)
                            return
                        
                        # Calculate war participation (fractional wars)
                        war_participation = individual_races / races
                        
                        results.append({
                            'name': name,
                            'score': score,
                            'races_played': individual_races,
                            'war_participation': war_participation,
                            'raw_input': part
                        })
                    except ValueError:
                        await interaction.response.send_message(f"❌ Invalid score format: `{part}`. Use PlayerName: Score or PlayerName(races): Score.", ephemeral=True)
                        return
            
            if not results:
                await interaction.response.send_message("❌ No player scores provided. Use format: `PlayerName: Score`", ephemeral=True)
                return
            
            # Resolve player names and validate they exist in players table
            resolved_results = []
            failed_players = []
            
            for result in results:
                resolved_player = self.bot.db.resolve_player_name(result['name'], guild_id)
                logging.info(f"Player resolution: '{result['name']}' -> {resolved_player}")
                if resolved_player:
                    resolved_results.append({
                        'name': resolved_player,
                        'score': result['score'],
                        'races_played': result['races_played'],
                        'war_participation': result['war_participation'],
                        'raw_line': f"Manual: {result['raw_input']}"
                    })
                else:
                    failed_players.append(result['name'])
            
            if failed_players:
                await interaction.response.send_message(f"❌ These players are not in the players table: {', '.join(failed_players)}\nUse `/addplayer <player>` to add them first.", ephemeral=True)
                return
            
            # Store war in database
            success = self.bot.db.add_race_results(resolved_results, races, guild_id)
            
            if not success:
                await interaction.response.send_message("❌ Failed to add war to database. Check logs for details.", ephemeral=True)
                return
            
            # Update player statistics
            import datetime
            current_date = datetime.datetime.now().strftime('%Y-%m-%d')
            stats_updated = []
            stats_failed = []
            
            for result in resolved_results:
                success = self.bot.db.update_player_stats(
                    result['name'], 
                    result['score'], 
                    result['races_played'],
                    result['war_participation'],
                    current_date,
                    guild_id
                )
                if success:
                    stats_updated.append(result['name'])
                    logging.info(f"✅ Stats updated for {result['name']}")
                else:
                    stats_failed.append(result['name'])
                    logging.error(f"❌ Stats update failed for {result['name']}")
            
            # Create success response
            embed = discord.Embed(
                title="⚔️ War Added Successfully!",
                color=0x00ff00
            )
            
            # Show war details
            player_list = []
            for result in resolved_results:
                if result['races_played'] == races:
                    # Full participation - no parentheses
                    player_list.append(f"**{result['name']}**: {result['score']} points")
                else:
                    # Substitution - show race count
                    player_list.append(f"**{result['name']}** ({result['races_played']}): {result['score']} points")
            
            embed.add_field(
                name="🏁 War Results",
                value="\n".join(player_list),
                inline=False
            )
            
            embed.add_field(
                name="📊 Stats Updated",
                value=f"✅ {len(stats_updated)} players" + (f"\n❌ {len(stats_failed)} failed" if stats_failed else ""),
                inline=True
            )
            
            embed.add_field(
                name="📅 Date",
                value=current_date,
                inline=True
            )
            
            embed.set_footer(text="Player statistics have been automatically updated")
            await interaction.response.send_message(embed=embed)
            
            # Start countdown timer
            countdown_seconds = 30
            for remaining in range(countdown_seconds, 0, -1):
                await asyncio.sleep(1)
                if remaining <= 10:  # Only show countdown for last 10 seconds
                    await interaction.edit_original_response(
                        embed=embed, 
                        content=f"Disappearing in {remaining} seconds..."
                    )
            
            # Delete the message
            await interaction.delete_original_response()
            
        except Exception as e:
            logging.error(f"Error adding war: {e}")
            await interaction.response.send_message("❌ Error adding war. Check the command format and try again.", ephemeral=True)


    
    
    
    # Team Management Commands
    @app_commands.command(name="addteam", description="Add a new team to the clan")
    @app_commands.describe(team_name="Name of the team to create (1W-50 characters, cannot be 'Unassigned')")
    @require_guild_setup
    async def add_team(self, interaction: discord.Interaction, team_name: str):
        """Add a new team to the guild."""
        try:
            guild_id = self.get_guild_id(interaction)
            success = self.bot.db.add_guild_team(guild_id, team_name)
            
            if success:
                embed = discord.Embed(
                    title="✅ Team Created!",
                    description=f"Successfully created team: **{team_name}**",
                    color=0x00ff00
                )
                embed.add_field(
                    name="Next Steps",
                    value=f"• Assign players with `/assignplayerstoteam {team_name} <players>`\n• View team roster with `/showspecificteamroster {team_name}`\n• List all teams with `/showallteams`",
                    inline=False
                )
                embed.add_field(
                    name="Rules",
                    value="• 1-50 characters long\n• Unicode characters supported\n• Maximum 5 teams per guild",
                    inline=False
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to create team. Check if the name is valid and you haven't reached the 5-team limit.")
                
        except Exception as e:
            logging.error(f"Error adding team: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error creating team", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error creating team", ephemeral=True)
    
    @app_commands.command(name="removeteam", description="Remove a team from the guild")
    @app_commands.describe(team_name="Name of the team to remove (players will be moved to 'Unassigned')")
    @require_guild_setup
    async def remove_team(self, interaction: discord.Interaction, team_name: str):
        """Remove a team from the guild."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Check if team exists
            current_teams = self.bot.db.get_guild_team_names(guild_id)
            team_exists = any(team.lower() == team_name.lower() for team in current_teams)
            
            if not team_exists:
                await interaction.response.send_message(f"❌ Team '{team_name}' not found. Use `/showallteams` to see available teams.")
                return
            
            # Get team player count for confirmation
            teams_with_counts = self.bot.db.get_guild_teams_with_counts(guild_id)
            player_count = 0
            actual_team_name = team_name
            
            for team, count in teams_with_counts.items():
                if team.lower() == team_name.lower():
                    player_count = count
                    actual_team_name = team
                    break
            
            # Confirmation embed
            embed = discord.Embed(
                title=f"⚠️ Remove Team: {actual_team_name}",
                description=f"Are you sure you want to remove this team?\n\n**{player_count} players** will be moved to 'Unassigned'.",
                color=0xff4444
            )
            embed.set_footer(text="React with ✅ to confirm or ❌ to cancel")
            
            await interaction.response.send_message(embed=embed)
            msg = await interaction.original_response()
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            
            def check(reaction, user):
                return user == interaction.user and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
            
            try:
                reaction, _ = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == "✅":
                    success = self.bot.db.remove_guild_team(guild_id, actual_team_name)
                    
                    if success:
                        embed = discord.Embed(
                            title="✅ Team Removed!",
                            description=f"Successfully removed team: **{actual_team_name}**\n\n{player_count} players moved to 'Unassigned'.",
                            color=0x00ff00
                        )
                        await interaction.edit_original_response(embed=embed)
                    else:
                        await interaction.edit_original_response(content="❌ Failed to remove team. Check logs for details.")
                else:
                    await interaction.edit_original_response(content="❌ Team removal cancelled.")
                
                try:
                    await msg.clear_reactions()
                except:
                    pass
                    
            except asyncio.TimeoutError:
                await interaction.edit_original_response(content="❌ Team removal timed out.")
                try:
                    await msg.clear_reactions()
                except:
                    pass
                
        except Exception as e:
            logging.error(f"Error removing team: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error removing team", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error removing team", ephemeral=True)
    
    @app_commands.command(name="renameteam", description="Rename an existing team in the guild")
    @app_commands.describe(old_name="Current team name", new_name="New team name")
    @require_guild_setup
    async def rename_team(self, interaction: discord.Interaction, old_name: str, new_name: str):
        """Rename a team in the guild."""
        try:
            guild_id = self.get_guild_id(interaction)
            success = self.bot.db.rename_guild_team(guild_id, old_name, new_name)
            
            if success:
                embed = discord.Embed(
                    title="✅ Team Renamed!",
                    description=f"Successfully renamed:\n**{old_name}** → **{new_name}**",
                    color=0x00ff00
                )
                embed.add_field(
                    name="Player Assignments",
                    value="All player assignments have been preserved.",
                    inline=False
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to rename team. Check if the old team exists and the new name is valid.")
                
        except Exception as e:
            logging.error(f"Error renaming team: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error renaming team", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error renaming team", ephemeral=True)
    

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(MarioKartCommands(bot)) 