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
                    # Create an embed for the player's stats
                    embed = discord.Embed(
                        title=f"📊 Stats for {stats['player_name']}",
                        color=0x00ff00
                    )
                    
                    # Display team information
                    team_info = {
                        'Phantom Orbit': '🔮',
                        'Moonlight Bootel': '🌙',
                        'Unassigned': '❓'
                    }
                    team_icon = team_info.get(stats.get('team', 'Unassigned'), '👥')
                    embed.add_field(name="Team", value=f"{team_icon} {stats.get('team', 'Unassigned')}", inline=True)
                    
                    # Display the players' nicknames if they exist
                    if stats.get('nicknames'):
                        embed.add_field(name="Nicknames", value=", ".join(stats['nicknames']), inline=True)
                    else:
                        embed.add_field(name="Nicknames", value="None", inline=True)
                    
                    # Display the players' roster info
                    embed.add_field(name="Added By", value=stats.get('added_by', 'Unknown'), inline=True)
                    
                    # Note: The current database schema doesn't have total_scores, total_races, etc.
                    # These would need to be calculated from the wars table
                    embed.add_field(name="Player Since", value=stats.get('created_at', 'Unknown')[:10] if stats.get('created_at') else 'Unknown', inline=True)
                    embed.add_field(name="Last Updated", value=stats.get('updated_at', 'Unknown')[:10] if stats.get('updated_at') else 'Unknown', inline=True)
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"❌ No stats found for player: {player_name}")
            else:
                # Get all player stats
                all_stats = self.bot.db.get_all_players_stats()
                if all_stats:
                    embed = discord.Embed(
                        title="📊 All Player Statistics",
                        description="Players organized by teams",
                        color=0x00ff00
                    )
                    
                    # Group by teams
                    teams = {}
                    for stats in all_stats:
                        team = stats.get('team', 'Unassigned')
                        if team not in teams:
                            teams[team] = []
                        teams[team].append(stats)
                    
                    # Team icons
                    team_icons = {
                        'Phantom Orbit': '🔮',
                        'Moonlight Bootel': '🌙',
                        'Unassigned': '❓'
                    }
                    
                    for team_name, players in teams.items():
                        if players:  # Only show teams with players
                            icon = team_icons.get(team_name, '👥')
                            player_list = []
                            for player in players:
                                nickname_text = f" ({', '.join(player['nicknames'][:2])})" if player.get('nicknames') else ""
                                player_list.append(f"• **{player['player_name']}**{nickname_text}")
                            
                            embed.add_field(
                                name=f"{icon} {team_name} ({len(players)} players)",
                                value="\n".join(player_list[:10]),  # Limit to 10 players per team
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
                        roster_players = self.bot.db.get_roster_players()
                        if name in roster_players:
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
        """Show the complete clan roster organized by teams."""
        try:
            # Get all players with their team and nickname info
            all_players = self.bot.db.get_all_players_stats()
            
            if not all_players:
                await ctx.send("❌ No players found in roster. Use `!mkadd <player>` to add players.")
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
            
            # Team icons and colors
            team_info = {
                'Phantom Orbit': {'icon': '🔮', 'color': 0x9932cc},
                'Moonlight Bootel': {'icon': '🌙', 'color': 0x4169e1},
                'Unassigned': {'icon': '❓', 'color': 0x808080}
            }
            
            # Display each team
            for team_name, players in teams.items():
                if players:  # Only show teams with players
                    icon = team_info.get(team_name, {}).get('icon', '👥')
                    player_list = []
                    
                    for player in players:
                        nickname_count = len(player.get('nicknames', []))
                        nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                        player_list.append(f"• **{player['player_name']}**{nickname_text}")
                    
                    embed.add_field(
                        name=f"{icon} {team_name} ({len(players)} players)",
                        value="\n".join(player_list),
                        inline=False
                    )
            
            embed.set_footer(text="Use !mkteams for detailed team view | Only results for these players will be saved from war images.")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing roster: {e}")
            await ctx.send("❌ Error retrieving roster")

    @commands.command(name='mkadd')
    async def add_player_to_roster(self, ctx, player_name: str = None):
        """Add a player to the clan roster."""
        if not player_name:
            embed = discord.Embed(
                title="➕ Add Player to Roster",
                description="Add a new player to the active clan roster.",
                color=0x00ff00
            )
            embed.add_field(
                name="Usage",
                value="`!mkadd <player_name>`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkadd NewPlayer`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Add player to roster
            success = self.bot.db.add_roster_player(player_name, str(ctx.author))
            
            if success:
                await ctx.send(f"✅ Added **{player_name}** to the clan roster!")
            else:
                await ctx.send(f"❌ **{player_name}** is already in the roster or couldn't be added.")
                
        except Exception as e:
            logging.error(f"Error adding player to roster: {e}")
            await ctx.send("❌ Error adding player to roster")

    @commands.command(name='mkremove')
    async def remove_player_from_roster(self, ctx, player_name: str = None):
        """Remove a player from the clan roster."""
        if not player_name:
            embed = discord.Embed(
                title="➖ Remove Player from Roster",
                description="Remove a player from the active clan roster.",
                color=0xff4444
            )
            embed.add_field(
                name="Usage",
                value="`!mkremove <player_name>`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkremove OldPlayer`",
                inline=False
            )
            embed.add_field(
                name="Note",
                value="This marks the player as inactive but keeps their stats.",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Remove player from roster
            success = self.bot.db.remove_roster_player(player_name)
            
            if success:
                await ctx.send(f"✅ Removed **{player_name}** from the active roster.")
            else:
                await ctx.send(f"❌ **{player_name}** is not in the active roster or couldn't be removed.")
                
        except Exception as e:
            logging.error(f"Error removing player from roster: {e}")
            await ctx.send("❌ Error removing player from roster")

    @commands.command(name='mkhelp')
    async def help_command(self, ctx):
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
                "`!mkstats [player]` - Show player stats or leaderboard\n"
                "`!mkroster` - Show complete clan roster by teams\n"
                "`!mkadd <player>` - Add player to roster\n"
                "`!mkremove <player>` - Remove player from roster\n"
                "`!mkmanual` - Manual war entry (when OCR fails)\n"
                "`!mkpreset list` - Show table format presets"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👥 Team Management Commands",
            value=(
                "`!mkassignteam <player> <team>` - Assign player to team\n"
                "`!mkassignplayerstoteam <team> <player1> <player2>...` - Assign multiple players to team\n"
                "`!mkunassignteam <player>` - Set player to Unassigned\n"
                "`!mkteams` - Show all teams and their players\n"
                "`!mkteamroster <team>` - Show specific team roster"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🏷️ Nickname Management Commands",
            value=(
                "`!mkaddnickname <player> <nickname>` - Add nickname to player\n"
                "`!mkaddnicknames <player> <nick1> <nick2>...` - Add multiple nicknames\n"
                "`!mkremovenickname <player> <nickname>` - Remove nickname from player\n"
                "`!mknicknames <player>` - Show all nicknames for player"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 Available Teams",
            value="• **Phantom Orbit** 🔮\n• **Moonlight Bootel** 🌙\n• **Unassigned** ❓",
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

    @commands.command(name='mkeditadd')
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

    @commands.command(name='mkeditremove')
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

    @commands.command(name='mkassignteam')
    async def assign_player_to_team(self, ctx, player_name: str = None, *, team_name: str = None):
        """Assign a player to a team."""
        if not player_name or not team_name:
            embed = discord.Embed(
                title="👥 Assign Player to Team",
                description="Assign a player to a team.",
                color=0x9932cc
            )
            embed.add_field(
                name="Usage",
                value="`!mkassignteam <player_name> <team_name>`",
                inline=False
            )
            embed.add_field(
                name="Valid Teams",
                value="• Unassigned\n• Phantom Orbit\n• Moonlight Bootel",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkassignteam Cynical Phantom Orbit`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Validate team name
        valid_teams = ['Unassigned', 'Phantom Orbit', 'Moonlight Bootel']
        if team_name not in valid_teams:
            await ctx.send(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}")
            return
        
        try:
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name)
            if not resolved_player:
                await ctx.send(f"❌ Player **{player_name}** not found in roster. Use `!mkadd {player_name}` to add them first.")
                return
            
            # Assign team
            success = self.bot.db.set_player_team(resolved_player, team_name)
            
            if success:
                await ctx.send(f"✅ Assigned **{resolved_player}** to team **{team_name}**!")
            else:
                await ctx.send(f"❌ Failed to assign **{resolved_player}** to team **{team_name}**.")
                
        except Exception as e:
            logging.error(f"Error assigning player to team: {e}")
            await ctx.send("❌ Error assigning player to team")

    @commands.command(name='mkassignplayerstoteam')
    async def assign_players_to_team(self, ctx, team_name: str = None, *player_names):
        """Assign multiple players to a team."""
        if not team_name or not player_names:
            embed = discord.Embed(
                title="👥 Assign Multiple Players to Team",
                description="Assign multiple players to a team at once.",
                color=0x9932cc
            )
            embed.add_field(
                name="Usage",
                value="`!mkassignplayerstoteam <team_name> <player1> <player2> <player3> ...`",
                inline=False
            )
            embed.add_field(
                name="Valid Teams",
                value="• Unassigned\n• Phantom Orbit\n• Moonlight Bootel",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkassignplayerstoteam \"Phantom Orbit\" Cynical TestPlayer1 TestPlayer2`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Validate team name
        valid_teams = ['Unassigned', 'Phantom Orbit', 'Moonlight Bootel']
        if team_name not in valid_teams:
            await ctx.send(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}")
            return
        
        if len(player_names) == 0:
            await ctx.send("❌ Please provide at least one player name.")
            return
        
        try:
            # Resolve all player names first
            resolved_players = []
            failed_players = []
            
            for player_name in player_names:
                resolved = self.bot.db.resolve_player_name(player_name)
                if resolved:
                    resolved_players.append(resolved)
                else:
                    failed_players.append(player_name)
            
            if failed_players:
                await ctx.send(f"❌ These players were not found in roster: {', '.join(failed_players)}\nUse `!mkadd <player>` to add them first.")
                return
            
            # Assign all players to team
            successful_assignments = []
            failed_assignments = []
            
            for player in resolved_players:
                success = self.bot.db.set_player_team(player, team_name)
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
            
            await ctx.send(embed=embed)
                
        except Exception as e:
            logging.error(f"Error assigning players to team: {e}")
            await ctx.send("❌ Error assigning players to team")

    @commands.command(name='mkunassignteam')
    async def unassign_player_from_team(self, ctx, player_name: str = None):
        """Unassign a player from their team (set to Unassigned)."""
        if not player_name:
            embed = discord.Embed(
                title="👥 Unassign Player from Team",
                description="Set a player's team to Unassigned.",
                color=0xff4444
            )
            embed.add_field(
                name="Usage",
                value="`!mkunassignteam <player_name>`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkunassignteam Cynical`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name)
            if not resolved_player:
                await ctx.send(f"❌ Player **{player_name}** not found in roster.")
                return
            
            # Set team to Unassigned
            success = self.bot.db.set_player_team(resolved_player, 'Unassigned')
            
            if success:
                await ctx.send(f"✅ Set **{resolved_player}** to **Unassigned**!")
            else:
                await ctx.send(f"❌ Failed to unassign **{resolved_player}** from team.")
                
        except Exception as e:
            logging.error(f"Error unassigning player from team: {e}")
            await ctx.send("❌ Error unassigning player from team")

    @commands.command(name='mkteams')
    async def show_teams(self, ctx):
        """Show all players organized by teams."""
        try:
            teams = self.bot.db.get_players_by_team()
            
            if not teams:
                await ctx.send("❌ No players found in roster.")
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
            
            embed.set_footer(text=f"Total players: {total_players}")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing teams: {e}")
            await ctx.send("❌ Error retrieving team information")

    @commands.command(name='mkteamroster')
    async def show_team_roster(self, ctx, *, team_name: str = None):
        """Show roster for a specific team."""
        if not team_name:
            embed = discord.Embed(
                title="👥 Show Team Roster",
                description="Display all players in a specific team.",
                color=0x9932cc
            )
            embed.add_field(
                name="Usage",
                value="`!mkteamroster <team_name>`",
                inline=False
            )
            embed.add_field(
                name="Valid Teams",
                value="• Unassigned\n• Phantom Orbit\n• Moonlight Bootel",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkteamroster Phantom Orbit`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Validate team name
        valid_teams = ['Unassigned', 'Phantom Orbit', 'Moonlight Bootel']
        if team_name not in valid_teams:
            await ctx.send(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}")
            return
        
        try:
            team_players = self.bot.db.get_team_roster(team_name)
            
            # Define team colors and icons
            team_info = {
                'Phantom Orbit': {'icon': '🔮', 'color': 0x9932cc},
                'Moonlight Bootel': {'icon': '🌙', 'color': 0x4169e1},
                'Unassigned': {'icon': '❓', 'color': 0x808080}
            }
            
            team_data = team_info.get(team_name, {'icon': '👥', 'color': 0x9932cc})
            
            embed = discord.Embed(
                title=f"{team_data['icon']} {team_name} Roster",
                description=f"Players in team {team_name}:",
                color=team_data['color']
            )
            
            if team_players:
                # Get detailed stats for team members
                detailed_players = []
                for player in team_players:
                    player_stats = self.bot.db.get_player_stats(player)
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
            
            embed.set_footer(text=f"Use !mkassignteam <player> \"{team_name}\" to assign players to this team")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing team roster: {e}")
            await ctx.send("❌ Error retrieving team roster")

    @commands.command(name='mkaddnickname')
    async def add_nickname(self, ctx, player_name: str = None, *nicknames):
        """Add a single nickname to a player."""
        if not player_name or not nicknames:
            embed = discord.Embed(
                title="🏷️ Add Nickname",
                description="Add a nickname to a player for OCR recognition.",
                color=0x9932cc
            )
            embed.add_field(
                name="Usage",
                value="`!mkaddnickname <player_name> <nickname>`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkaddnickname Cynical cyn`",
                inline=False
            )
            embed.add_field(
                name="Purpose",
                value="Nicknames help OCR recognize players when their names appear differently in race results.",
                inline=False
            )
            embed.add_field(
                name="💡 Tip",
                value="For multiple nicknames, use `!mkaddnicknames <player> <nick1> <nick2> ...`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Check if multiple nicknames were provided
        if len(nicknames) > 1:
            await ctx.send(f"❌ You provided multiple nicknames. Did you mean to use `!mkaddnicknames {player_name} {' '.join(nicknames)}`?")
            return
        
        try:
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name)
            if not resolved_player:
                await ctx.send(f"❌ Player **{player_name}** not found in roster. Use `!mkadd {player_name}` to add them first.")
                return
            
            # Add single nickname
            nickname = nicknames[0]
            success = self.bot.db.add_nickname(resolved_player, nickname)
            
            if success:
                await ctx.send(f"✅ Added nickname **{nickname}** to **{resolved_player}**!")
            else:
                await ctx.send(f"❌ Nickname **{nickname}** already exists for **{resolved_player}** or couldn't be added.")
                
        except Exception as e:
            logging.error(f"Error adding nickname: {e}")
            await ctx.send("❌ Error adding nickname")

    @commands.command(name='mkaddnicknames')
    async def add_nicknames(self, ctx, player_name: str = None, *nicknames):
        """Add multiple nicknames to a player."""
        if not player_name or not nicknames:
            embed = discord.Embed(
                title="🏷️ Add Multiple Nicknames",
                description="Add multiple nicknames to a player at once.",
                color=0x9932cc
            )
            embed.add_field(
                name="Usage",
                value="`!mkaddnicknames <player_name> <nickname1> <nickname2> <nickname3> ...`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkaddnicknames Cynical cyn cynical123 cyn_mkw`",
                inline=False
            )
            embed.add_field(
                name="Purpose",
                value="Bulk add nicknames for OCR recognition when names appear differently in race results.",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name)
            if not resolved_player:
                await ctx.send(f"❌ Player **{player_name}** not found in roster. Use `!mkadd {player_name}` to add them first.")
                return
            
            # Add all nicknames
            successful_additions = []
            failed_additions = []
            
            for nickname in nicknames:
                success = self.bot.db.add_nickname(resolved_player, nickname)
                if success:
                    successful_additions.append(nickname)
                else:
                    failed_additions.append(nickname)
            
            # Create response embed
            embed = discord.Embed(
                title="🏷️ Nickname Addition Results",
                color=0x00ff00 if not failed_additions else 0xff4444
            )
            
            if successful_additions:
                embed.add_field(
                    name=f"✅ Successfully added to **{resolved_player}**",
                    value="\n".join([f"• {nickname}" for nickname in successful_additions]),
                    inline=False
                )
            
            if failed_additions:
                embed.add_field(
                    name="❌ Failed to add (already exist or error)",
                    value="\n".join([f"• {nickname}" for nickname in failed_additions]),
                    inline=False
                )
            
            embed.add_field(
                name="Summary",
                value=f"Successfully added: {len(successful_additions)}\nFailed: {len(failed_additions)}",
                inline=False
            )
            
            await ctx.send(embed=embed)
                
        except Exception as e:
            logging.error(f"Error adding nicknames: {e}")
            await ctx.send("❌ Error adding nicknames")

    @commands.command(name='mkremovenickname')
    async def remove_nickname(self, ctx, player_name: str = None, nickname: str = None):
        """Remove a nickname from a player."""
        if not player_name or not nickname:
            embed = discord.Embed(
                title="🏷️ Remove Nickname",
                description="Remove a nickname from a player.",
                color=0xff4444
            )
            embed.add_field(
                name="Usage",
                value="`!mkremovenickname <player_name> <nickname>`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mkremovenickname Cynical cyn`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name)
            if not resolved_player:
                await ctx.send(f"❌ Player **{player_name}** not found in roster.")
                return
            
            # Remove nickname
            success = self.bot.db.remove_nickname(resolved_player, nickname)
            
            if success:
                await ctx.send(f"✅ Removed nickname **{nickname}** from **{resolved_player}**!")
            else:
                await ctx.send(f"❌ Nickname **{nickname}** not found for **{resolved_player}** or couldn't be removed.")
                
        except Exception as e:
            logging.error(f"Error removing nickname: {e}")
            await ctx.send("❌ Error removing nickname")

    @commands.command(name='mknicknames')
    async def show_nicknames(self, ctx, player_name: str = None):
        """Show all nicknames for a player."""
        if not player_name:
            embed = discord.Embed(
                title="🏷️ Show Player Nicknames",
                description="Display all nicknames for a player.",
                color=0x9932cc
            )
            embed.add_field(
                name="Usage",
                value="`!mknicknames <player_name>`",
                inline=False
            )
            embed.add_field(
                name="Example", 
                value="`!mknicknames Cynical`",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Resolve player name (handles nicknames)
            resolved_player = self.bot.db.resolve_player_name(player_name)
            if not resolved_player:
                await ctx.send(f"❌ Player **{player_name}** not found in roster.")
                return
            
            # Get nicknames
            nicknames = self.bot.db.get_player_nicknames(resolved_player)
            
            embed = discord.Embed(
                title=f"🏷️ Nicknames for {resolved_player}",
                description=f"All nicknames for **{resolved_player}**:",
                color=0x9932cc
            )
            
            if nicknames:
                embed.add_field(
                    name=f"Nicknames ({len(nicknames)})",
                    value="\n".join([f"• {nickname}" for nickname in nicknames]),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Nicknames",
                    value="No nicknames set for this player.",
                    inline=False
                )
            
            embed.set_footer(text=f"Use !mkaddnickname {resolved_player} <nickname> to add more nicknames")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing nicknames: {e}")
            await ctx.send("❌ Error retrieving nicknames")

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(MarioKartCommands(bot)) 