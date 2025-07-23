import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import json
import functools
import aiohttp
import tempfile
import os
from .ocr_processor import OCRProcessor

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
                stats = self.bot.db.get_player_stats(resolved_player, guild_id)
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
                    roster_stats = self.bot.db.get_player_info(resolved_player, guild_id)
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
                    war_stats = self.bot.db.get_player_stats(roster_player['player_name'], guild_id)
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
    @app_commands.describe(
        player_name="Name of the player to add to the roster",
        member_status="Member status (default: Member)"
    )
    @app_commands.choices(member_status=[
        app_commands.Choice(name="Member", value="member"),
        app_commands.Choice(name="Trial", value="trial"),
        app_commands.Choice(name="Kicked", value="kicked")
    ])
    @require_guild_setup
    async def add_player_to_roster(self, interaction: discord.Interaction, player_name: str, member_status: str = "member"):
        """Add a player to the clan roster."""
        try:
            guild_id = self.get_guild_id(interaction)
            # Add player to players table with member status
            success = self.bot.db.add_roster_player(player_name, str(interaction.user), guild_id, member_status)
            
            if success:
                status_display = member_status.title()
                await interaction.response.send_message(f"✅ Added **{player_name}** to the clan roster as **{status_display}**!")
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
                "`/addplayer <player> [status]` - Add player to roster (Member/Trial/Kicked)\n"
                "`/removeplayer <player>` - Remove player from roster"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👤 Member Status Commands",
            value=(
                "`/setmemberstatus <player> <status>` - Set player status (Member/Trial/Kicked)\n"
                "`/showtrials` - Show all trial members\n"
                "`/showkicked` - Show all kicked members"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚔️ War Management Commands",
            value=(
                "`/addwar` - Add war with player scores\n"
                "`/showallwars [limit]` - List all wars with pagination\n"
                "`/appendplayertowar <war_id> <player_scores>` - Add new players to existing war\n"
                "`/removewar <war_id>` - Delete war and revert statistics\n"
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
                "`/assignplayerstoteam <player1> <player2>... <team>` - Assign players to team (1 or more)\n"
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



    @app_commands.command(name="assignplayerstoteam", description="Assign multiple players to a team")
    @app_commands.describe(players="Space-separated list of player names (minimum 1 player)", team_name="Team to assign players to")
    @require_guild_setup
    async def assign_players_to_team(self, interaction: discord.Interaction, players: str, team_name: str):
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
                    player_stats = self.bot.db.get_player_info(player, guild_id)
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
            
            embed.set_footer(text=f"Use /assignplayerstoteam <players> {team_name} to assign players to this team")
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

    @app_commands.command(name="setmemberstatus", description="Set the member status for a player")
    @app_commands.describe(
        player_name="Player to set status for",
        member_status="New member status"
    )
    @app_commands.choices(member_status=[
        app_commands.Choice(name="Member", value="member"),
        app_commands.Choice(name="Trial", value="trial"),
        app_commands.Choice(name="Kicked", value="kicked")
    ])
    @require_guild_setup
    async def set_member_status(self, interaction: discord.Interaction, player_name: str, member_status: str):
        """Set the member status for a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return
            
            # Set member status
            success = self.bot.db.set_player_member_status(resolved_player, member_status, guild_id)
            
            if success:
                status_display = member_status.title()
                embed = discord.Embed(
                    title="✅ Member Status Updated!",
                    description=f"Set **{resolved_player}** status to **{status_display}**",
                    color=0x00ff00
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ Failed to update member status for **{resolved_player}**.")
                
        except Exception as e:
            logging.error(f"Error setting member status: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error setting member status", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error setting member status", ephemeral=True)

    @app_commands.command(name="showtrials", description="Show all trial members")
    @require_guild_setup
    async def show_trials(self, interaction: discord.Interaction):
        """Show all trial members."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Get trial members
            trials = self.bot.db.get_players_by_member_status('trial', guild_id)
            
            embed = discord.Embed(
                title="🔍 Trial Members",
                color=0xffa500
            )
            
            if trials:
                trial_list = []
                for player in trials:
                    nickname_count = len(player.get('nicknames', []))
                    nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                    team_text = f" - {player['team']}" if player['team'] != 'Unassigned' else ""
                    trial_list.append(f"• **{player['player_name']}**{team_text}{nickname_text}")
                
                embed.description = "\n".join(trial_list)
                embed.add_field(
                    name="Total Trial Members",
                    value=str(len(trials)),
                    inline=True
                )
            else:
                embed.description = "No trial members found."
            
            embed.set_footer(text="Use /setmemberstatus <player> Member to promote trial members")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing trials: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving trial members", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving trial members", ephemeral=True)

    @app_commands.command(name="showkicked", description="Show all kicked members")
    @require_guild_setup
    async def show_kicked(self, interaction: discord.Interaction):
        """Show all kicked members."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Get kicked members
            kicked = self.bot.db.get_players_by_member_status('kicked', guild_id)
            
            embed = discord.Embed(
                title="🚫 Kicked Members",
                color=0xff4444
            )
            
            if kicked:
                kicked_list = []
                for player in kicked:
                    nickname_count = len(player.get('nicknames', []))
                    nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                    team_text = f" - {player['team']}" if player['team'] != 'Unassigned' else ""
                    kicked_list.append(f"• **{player['player_name']}**{team_text}{nickname_text}")
                
                embed.description = "\n".join(kicked_list)
                embed.add_field(
                    name="Total Kicked Members",
                    value=str(len(kicked)),
                    inline=True
                )
            else:
                embed.description = "No kicked members found."
            
            embed.set_footer(text="Use /setmemberstatus <player> Member to reinstate kicked members")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing kicked members: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving kicked members", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving kicked members", ephemeral=True)

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
            war_id = self.bot.db.add_race_results(resolved_results, races, guild_id)
            
            if war_id is None:
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
                title=f"⚔️ War Added Successfully! (ID: {war_id})",
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
                if remaining <= 5:  # Only show countdown for last 5 seconds
                    await interaction.edit_original_response(
                        embed=embed, 
                        content=f"Disappearing in {remaining} seconds..."
                    )
            
            # Delete the message
            await interaction.delete_original_response()
            
        except Exception as e:
            logging.error(f"Error adding war: {e}")
            await interaction.response.send_message("❌ Error adding war. Check the command format and try again.", ephemeral=True)

    @app_commands.command(name="showallwars", description="Show all wars with pagination")
    @app_commands.describe(limit="Number of wars to show (default: 10, max: 50)")
    @require_guild_setup
    async def show_all_wars(self, interaction: discord.Interaction, limit: int = 10):
        """Show all wars with pagination."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Validate limit
            if limit < 1 or limit > 50:
                await interaction.response.send_message("❌ Limit must be between 1 and 50.", ephemeral=True)
                return
            
            # Get wars from database
            wars = self.bot.db.get_all_wars(limit, guild_id)
            
            if not wars:
                await interaction.response.send_message("❌ No wars found in the database.")
                return
            
            embed = discord.Embed(
                title="⚔️ War History",
                description=f"Showing {len(wars)} most recent wars:",
                color=0x9932cc
            )
            
            for war in wars:
                war_id = war.get('id')
                war_date = war.get('war_date')
                race_count = war.get('race_count')
                players_data = war.get('results', [])  # Fix: use 'results' instead of 'players_data'
                
                # Count unique players
                player_count = len(players_data)
                
                # Create complete player list with scores
                if players_data:
                    player_entries = []
                    for p in players_data:
                        name = p.get('name', 'Unknown')
                        score = p.get('score', 0)
                        races = p.get('races_played', race_count)
                        if races == race_count:
                            player_entries.append(f"{name}: {score}")
                        else:
                            player_entries.append(f"{name}({races}): {score}")
                    
                    player_list = ", ".join(player_entries)
                    
                    # If the list is too long for Discord field limit, truncate
                    if len(player_list) > 1000:
                        # Find a good breaking point
                        truncated = player_list[:900]
                        last_comma = truncated.rfind(', ')
                        if last_comma > 0:
                            player_list = truncated[:last_comma] + f"... +{len(players_data) - truncated[:last_comma].count(',') - 1} more"
                        else:
                            player_list = truncated + "..."
                else:
                    player_list = "No players"
                
                embed.add_field(
                    name=f"War ID: {war_id} - {war_date}",
                    value=f"🏁 {race_count} races | 👥 {player_count} players\n📋 {player_list}",
                    inline=False
                )
            
            embed.set_footer(text=f"Use /updatewar <id> or /removewar <id> to modify wars | Showing {limit} most recent wars (oldest first)")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing all wars: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving wars", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving wars", ephemeral=True)

    @app_commands.command(name="appendplayertowar", description="Add new players to an existing war")
    @app_commands.describe(
        war_id="ID of the war to add players to",
        player_scores="Player scores to add in format: 'Player1: 104, Player2: 105'"
    )
    @require_guild_setup
    async def append_player_to_war(self, interaction: discord.Interaction, war_id: int, player_scores: str):
        """Add new players to an existing war (append-only, no updates to existing players)."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Get the existing war
            existing_war = self.bot.db.get_war_by_id(war_id, guild_id)
            if not existing_war:
                await interaction.response.send_message(f"❌ War ID: {war_id} not found.", ephemeral=True)
                return
            
            # Use existing race count
            races = existing_war.get('race_count', 12)
            
            # Parse new player scores
            new_players = []
            parts = [p.strip() for p in player_scores.split(',')]
            
            for part in parts:
                if ':' in part:
                    try:
                        name, score_str = part.split(':', 1)
                        name = name.strip()
                        score = int(score_str.strip())
                        
                        # Handle individual race count in parentheses
                        individual_races = races
                        if '(' in name and ')' in name:
                            base_name = name[:name.index('(')].strip()
                            race_count_str = name[name.index('(')+1:name.index(')')].strip()
                            try:
                                individual_races = int(race_count_str)
                                name = base_name
                                
                                if individual_races < 1 or individual_races > races:
                                    await interaction.response.send_message(f"❌ Invalid race count for {base_name}: {individual_races}", ephemeral=True)
                                    return
                            except ValueError:
                                await interaction.response.send_message(f"❌ Invalid race count format in: `{name}`", ephemeral=True)
                                return
                        
                        # Validate score
                        min_score = individual_races * 1
                        max_score = individual_races * 15
                        if score < min_score or score > max_score:
                            await interaction.response.send_message(f"❌ {name}: {score} points invalid for {individual_races} races.", ephemeral=True)
                            return
                        
                        # Resolve player name
                        resolved_player = self.bot.db.resolve_player_name(name, guild_id)
                        if not resolved_player:
                            await interaction.response.send_message(f"❌ Player **{name}** not found in players table.", ephemeral=True)
                            return
                        
                        war_participation = individual_races / races
                        
                        new_players.append({
                            'name': resolved_player,
                            'score': score,
                            'races_played': individual_races,
                            'war_participation': war_participation,
                            'raw_line': f"Append: {part}"
                        })
                    except ValueError:
                        await interaction.response.send_message(f"❌ Invalid score format: `{part}`", ephemeral=True)
                        return
            
            if not new_players:
                await interaction.response.send_message("❌ No valid player scores provided.", ephemeral=True)
                return
            
            # Check if any players already exist in the war (this will fail in database method)
            existing_results = existing_war.get('results', [])
            existing_names = {player.get('name', '').lower() for player in existing_results}
            conflicts = []
            for new_player in new_players:
                if new_player.get('name', '').lower() in existing_names:
                    conflicts.append(new_player.get('name', 'Unknown'))
            
            if conflicts:
                await interaction.response.send_message(f"❌ These players already exist in war {war_id}: {', '.join(conflicts)}\nUse a different command to update existing player scores.", ephemeral=True)
                return
            
            # Show confirmation dialog
            embed = discord.Embed(
                title=f"⚠️ Add Players to War ID: {war_id}",
                description=f"Adding {len(new_players)} new players to the war:",
                color=0xff9900
            )
            
            add_list = []
            for p in new_players:
                if p['races_played'] == races:
                    add_list.append(f"+ {p['name']}: {p['score']}")
                else:
                    add_list.append(f"+ {p['name']}({p['races_played']}): {p['score']}")
            
            embed.add_field(
                name=f"🆕 Adding {len(new_players)} players",
                value="\n".join(add_list[:10]) + (f"\n... +{len(add_list)-10} more" if len(add_list) > 10 else ""),
                inline=False
            )
            
            embed.add_field(
                name=f"✅ Keeping {len(existing_results)} existing players unchanged",
                value="All existing players will remain exactly as they are",
                inline=False
            )
            
            embed.add_field(
                name="⚠️ This will:",
                value="• Add new players to the war\n• Add statistics for new players only\n• This action cannot be undone",
                inline=False
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
                    import datetime
                    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
                    
                    # Append players to war using new database method
                    success = self.bot.db.append_players_to_war_by_id(war_id, new_players, guild_id)
                    
                    if success:
                        # Add statistics for new players only
                        stats_added = []
                        stats_failed = []
                        
                        for new_player in new_players:
                            stats_success = self.bot.db.update_player_stats(
                                new_player['name'],
                                new_player['score'],
                                new_player['races_played'],
                                new_player['war_participation'],
                                current_date,
                                guild_id
                            )
                            if stats_success:
                                stats_added.append(new_player['name'])
                            else:
                                stats_failed.append(new_player['name'])
                        
                        embed = discord.Embed(
                            title="✅ Players Added Successfully!",
                            description=f"War ID: {war_id} has been updated with {len(new_players)} new players.",
                            color=0x00ff00
                        )
                        
                        embed.add_field(
                            name="Players Added",
                            value=f"🏁 {races} races\n👥 {len(new_players)} new players\n📊 {len(stats_added)} stats updated" + (f", {len(stats_failed)} failed" if stats_failed else ""),
                            inline=False
                        )
                        
                        # Show added players
                        player_list = []
                        for p in new_players:
                            if p['races_played'] == races:
                                player_list.append(f"**{p['name']}**: {p['score']} points")
                            else:
                                player_list.append(f"**{p['name']}** ({p['races_played']}): {p['score']} points")
                        
                        embed.add_field(
                            name="🏁 New Players Added",
                            value="\n".join(player_list[:10]) + (f"\n... +{len(player_list)-10} more" if len(player_list) > 10 else ""),
                            inline=False
                        )
                        
                        await interaction.edit_original_response(embed=embed)
                    else:
                        await interaction.edit_original_response(content="❌ Failed to add players to war. Check logs for details.")
                else:
                    await interaction.edit_original_response(content="❌ Player addition cancelled.")
                
                try:
                    await msg.clear_reactions()
                except:
                    pass
                    
            except asyncio.TimeoutError:
                await interaction.edit_original_response(content="❌ Player addition timed out.")
                try:
                    await msg.clear_reactions()
                except:
                    pass
            
        except Exception as e:
            logging.error(f"Error appending players to war: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error adding players to war", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error adding players to war", ephemeral=True)

    @app_commands.command(name="removewar", description="Remove a war and revert player statistics")
    @app_commands.describe(war_id="ID of the war to remove")
    @require_guild_setup
    async def remove_war(self, interaction: discord.Interaction, war_id: int):
        """Remove a war and revert player statistics."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Get the war to be removed
            war = self.bot.db.get_war_by_id(war_id, guild_id)
            if not war:
                await interaction.response.send_message(f"❌ War ID: {war_id} not found.", ephemeral=True)
                return
            
            war_date = war.get('war_date')
            race_count = war.get('race_count')
            
            # Handle data format - check if we get it from get_war_by_id or need to extract from database format
            players_data = war.get('players_data', [])
            if isinstance(players_data, dict) and 'results' in players_data:
                players_data = players_data['results']
            
            # Show confirmation dialog
            embed = discord.Embed(
                title=f"⚠️ Remove War ID: {war_id}",
                description=f"Are you sure you want to remove this war from **{war_date}**?",
                color=0xff4444
            )
            
            # Show war details - all players
            if players_data:
                player_entries = []
                for player in players_data:
                    name = player.get('name', 'Unknown')
                    score = player.get('score', 0)
                    races = player.get('races_played', race_count)
                    if races == race_count:
                        player_entries.append(f"{name}: {score}")
                    else:
                        player_entries.append(f"{name}({races}): {score}")
                
                player_list = ", ".join(player_entries)
                
                # Handle Discord field limit
                if len(player_list) > 1000:
                    truncated = player_list[:900]
                    last_comma = truncated.rfind(', ')
                    if last_comma > 0:
                        player_list = truncated[:last_comma] + f"... +{len(players_data) - truncated[:last_comma].count(',') - 1} more"
                    else:
                        player_list = truncated + "..."
                
                embed.add_field(
                    name=f"War Details ({race_count} races, {len(players_data)} players)",
                    value=player_list,
                    inline=False
                )
            
            embed.add_field(
                name="⚠️ This will:",
                value="• Delete the war from database\n• Subtract war contributions from player statistics\n• This action cannot be undone",
                inline=False
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
                    # Remove the war and revert player stats
                    stats_reverted = self.bot.db.remove_war_by_id(war_id, guild_id)
                    
                    if stats_reverted is not None:
                        embed = discord.Embed(
                            title="✅ War Removed Successfully!",
                            description=f"War ID: {war_id} from {war_date} has been removed.",
                            color=0x00ff00
                        )
                        embed.add_field(
                            name="Statistics Updated",
                            value=f"Reverted stats for {stats_reverted} players",
                            inline=False
                        )
                        await interaction.edit_original_response(embed=embed)
                    else:
                        await interaction.edit_original_response(content="❌ Failed to remove war. Check logs for details.")
                else:
                    await interaction.edit_original_response(content="❌ War removal cancelled.")
                
                try:
                    await msg.clear_reactions()
                except:
                    pass
                    
            except asyncio.TimeoutError:
                await interaction.edit_original_response(content="❌ War removal timed out.")
                try:
                    await msg.clear_reactions()
                except:
                    pass
                
        except Exception as e:
            logging.error(f"Error removing war: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error removing war", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error removing war", ephemeral=True)

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
                    value=f"• Assign players with `/assignplayerstoteam <players> {team_name}`\n• View team roster with `/showspecificteamroster {team_name}`\n• List all teams with `/showallteams`",
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

    @app_commands.command(name="runocr", description="Test OCR on the most recent image uploaded to this channel")
    @require_guild_setup
    async def run_ocr_test(self, interaction: discord.Interaction):
        """Run OCR test on the most recent image uploaded to the channel."""
        temp_image_path = None
        overlay_path = None
        
        try:
            await interaction.response.defer()
            logging.info(f"🔍 Starting OCR test command for user {interaction.user.name}")
            
            guild_id = self.get_guild_id_from_interaction(interaction)
            logging.info(f"🏰 Guild ID: {guild_id}")
            
            # Search for the most recent image in the channel
            logging.info("📝 Searching for recent images in channel...")
            recent_image = None
            message_count = 0
            
            async for message in interaction.channel.history(limit=50):
                message_count += 1
                if message.attachments:
                    for attachment in message.attachments:
                        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
                            recent_image = attachment
                            logging.info(f"✅ Found image: {attachment.filename} (size: {attachment.size} bytes)")
                            break
                if recent_image:
                    break
            
            logging.info(f"📊 Searched {message_count} messages")
            
            if not recent_image:
                logging.warning("❌ No recent image found in channel")
                await interaction.followup.send("❌ No recent image found in this channel. Please upload an image first.")
                return
            
            # Download the image to a temporary file
            logging.info(f"⬇️ Downloading image from: {recent_image.url}")
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(recent_image.url) as response:
                        if response.status == 200:
                            # Create temporary file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                                temp_image_path = temp_file.name
                                image_data = await response.read()
                                temp_file.write(image_data)
                                logging.info(f"✅ Image downloaded to: {temp_image_path} ({len(image_data)} bytes)")
                        else:
                            logging.error(f"❌ HTTP error downloading image: {response.status}")
                            await interaction.followup.send(f"❌ Failed to download image (HTTP {response.status})")
                            return
            except Exception as e:
                logging.error(f"❌ Exception downloading image: {e}")
                await interaction.followup.send(f"❌ Error downloading image: {str(e)}")
                return
            
            # Initialize OCR processor
            logging.info("🔧 Initializing OCR processor...")
            try:
                ocr = OCRProcessor(db_manager=self.bot.db)
                logging.info("✅ OCR processor initialized successfully")
            except Exception as e:
                logging.error(f"❌ Failed to initialize OCR processor: {e}")
                await interaction.followup.send(f"❌ Error initializing OCR: {str(e)}")
                return
            
            # Process the image with OCR (custom region debug mode)
            logging.info("🔍 Starting custom region OCR debug processing...")
            try:
                result = ocr.process_custom_region_debug(temp_image_path, guild_id)
                logging.info(f"📊 Custom region OCR debug processing completed. Success: {result.get('success', False)}")
                
                if 'debug_overlay' in result:
                    overlay_path = result['debug_overlay']
                    logging.info(f"🎨 Custom region debug overlay image created: {overlay_path}")
                
            except Exception as e:
                logging.error(f"❌ Exception during custom region OCR processing: {e}")
                await interaction.followup.send(f"❌ Custom region OCR processing error: {str(e)}")
                return
            
            if not result.get('success', False):
                error_msg = result.get('error', 'Unknown error')
                logging.error(f"❌ OCR processing failed: {error_msg}")
                await interaction.followup.send(f"❌ OCR processing failed: {error_msg}")
                return
            
            # Format the results
            logging.info("📝 Formatting custom region OCR debug results...")
            results_text = "🔍 **Custom Region OCR Debug Results**\n\n"
            
            results = result.get('results', [])
            debug_info = result.get('debug_info', {})
            region_used = debug_info.get('region_used', {})
            logging.info(f"👥 Found {len(results)} player results")
            
            # Show debug statistics and region info
            total_elements = debug_info.get('total_elements', 0)
            results_text += f"**Debug Stats:**\n"
            results_text += f"📍 Region: ({region_used.get('start', [0,0])[0]}, {region_used.get('start', [0,0])[1]}) to ({region_used.get('end', [0,0])[0]}, {region_used.get('end', [0,0])[1]})\n"
            results_text += f"🔤 Text elements in region: {total_elements}\n"
            results_text += f"👥 Player results found: {len(results)}\n\n"
            
            if results:
                results_text += "**Players Found:**\n"
                for i, player_result in enumerate(results, 1):
                    name = player_result.get('name', 'Unknown')
                    raw_name = player_result.get('raw_name', name)
                    score = player_result.get('score', 0)
                    is_roster = player_result.get('is_roster_member', False)
                    
                    # Add indicator for roster status
                    if is_roster:
                        indicator = "✅"
                        display_name = name
                    else:
                        indicator = "❓"
                        display_name = raw_name if raw_name != name else name
                    
                    results_text += f"{i}. {indicator} **{display_name}**: {score} points\n"
                    logging.info(f"  👤 Player {i}: {display_name} - {score} points (roster: {is_roster})")
                
                # Add validation info
                validation = result.get('validation', {})
                if validation:
                    results_text += f"\n**Total Found:** {validation.get('player_count', 0)}"
                    warnings = validation.get('warnings', [])
                    if warnings and len(warnings) <= 3:  # Limit warnings to avoid too long message
                        results_text += f"\n⚠️ **Warnings:** {'; '.join(warnings[:3])}"
                        logging.warning(f"⚠️ Validation warnings: {warnings}")
            else:
                results_text += "No players found in the image."
                logging.warning("❌ No player results found")
                
            # Add note about color coding and region
            results_text += f"\n\n**Legend for overlay image:**\n🟡 Yellow: Selected Region\n🟠 Orange: Extended Region\n🔴 Red: Letters/Names\n🟢 Green: Numbers/Scores\n🔵 Blue: Symbols"
            
            # Create embed for results
            embed = discord.Embed(
                title="🔍 OCR Processing Test",
                description=results_text,
                color=0x00ff00 if result.get('success') else 0xff0000
            )
            
            # Send the results
            logging.info("📤 Sending OCR results to Discord...")
            await interaction.followup.send(embed=embed)
            
            # Send the debug overlay image if available
            debug_overlay_path = result.get('debug_overlay')
            if debug_overlay_path and os.path.exists(debug_overlay_path):
                logging.info(f"📤 Sending debug overlay image: {debug_overlay_path}")
                try:
                    with open(debug_overlay_path, 'rb') as f:
                        overlay_file = discord.File(f, 'ocr_debug_overlay.png')
                        await interaction.followup.send(
                            "🎨 **Color-Coded Text Detection:**", 
                            file=overlay_file
                        )
                    logging.info("✅ Debug overlay image sent successfully")
                except Exception as e:
                    logging.error(f"❌ Error sending debug overlay image: {e}")
                    await interaction.followup.send(f"⚠️ Could not send debug overlay image: {str(e)}")
            else:
                logging.warning("⚠️ No debug overlay image available to send")
            
            # Send raw OCR text for debugging if available
            raw_text = debug_info.get('raw_text', '')
            if raw_text and len(raw_text) > 50:  # Only send if there's substantial text
                logging.info("📤 Sending raw OCR text for debugging")
                try:
                    # Truncate if too long for Discord
                    if len(raw_text) > 1500:
                        raw_text = raw_text[:1500] + "\n... (truncated)"
                    
                    await interaction.followup.send(
                        f"📄 **Raw OCR Text (for debugging):**\n```\n{raw_text}\n```"
                    )
                    logging.info("✅ Raw OCR text sent successfully")
                except Exception as e:
                    logging.error(f"❌ Error sending raw OCR text: {e}")
            else:
                logging.info("ℹ️ No substantial raw text to send")
            
            logging.info("✅ OCR test command completed successfully")
            
        except Exception as e:
            logging.error(f"❌ Unexpected error in OCR test command: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Unexpected error: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Unexpected error: {str(e)}")
            except:
                logging.error("❌ Could not send error message to Discord")
        finally:
            # Clean up temporary files
            if temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.unlink(temp_image_path)
                    logging.info(f"🧹 Cleaned up temp image: {temp_image_path}")
                except Exception as e:
                    logging.error(f"⚠️ Could not clean up temp image: {e}")
            
            debug_overlay_path = result.get('debug_overlay') if 'result' in locals() else None
            if debug_overlay_path and os.path.exists(debug_overlay_path):
                try:
                    os.unlink(debug_overlay_path)
                    logging.info(f"🧹 Cleaned up debug overlay image: {debug_overlay_path}")
                except Exception as e:
                    logging.error(f"⚠️ Could not clean up debug overlay image: {e}")
    

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(MarioKartCommands(bot)) 