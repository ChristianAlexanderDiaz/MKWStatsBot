"""Team management commands."""

import logging

import discord
from discord import app_commands

from ..utils.formatters import get_player_display_name
from ..utils.validators import has_admin_permission
from .base_cog import BaseCog, require_guild_setup


class TeamCog(BaseCog):
    """Team creation, assignment, tags, and roster commands."""

    async def player_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for player names."""
        try:
            guild_id = self.get_guild_id(interaction)
            all_players = self.bot.db.players.get_all_players_stats(guild_id)

            filtered = [p['player_name'] for p in all_players if current.lower() in p['player_name'].lower()]

            return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]
        except Exception as e:
            logging.error(f"Error in player autocomplete: {e}")
            return []

    async def team_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for team names."""
        try:
            guild_id = self.get_guild_id(interaction)
            team_names = self.bot.db.guilds.get_guild_team_names(guild_id)
            team_names.append('Unassigned')

            filtered = [name for name in team_names if current.lower() in name.lower()]

            return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]
        except Exception as e:
            logging.error(f"Error in team autocomplete: {e}")
            return []

    async def team_with_tag_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for teams that have tags set."""
        try:
            guild_id = self.get_guild_id(interaction)
            team_tags = self.bot.db.guilds.get_all_team_tags(guild_id)

            teams_with_tags = list(team_tags.keys())

            filtered = [name for name in teams_with_tags if current.lower() in name.lower()]

            return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]
        except Exception as e:
            logging.error(f"Error in team_with_tag autocomplete: {e}")
            return []

    @app_commands.command(name="assignplayers", description="Assign multiple players to a team")
    @app_commands.describe(players="Comma-separated player names (e.g. 'Player1, Player2, CAP ahaha')", team_name="Team to assign players to")
    @app_commands.autocomplete(team_name=team_autocomplete)
    @require_guild_setup
    async def assign_players_to_team(self, interaction: discord.Interaction, players: str, team_name: str):
        """Assign multiple players to a team."""
        try:
            guild_id = self.get_guild_id(interaction)

            player_names = [name.strip() for name in players.split(',') if name.strip()]
            if len(player_names) == 0:
                await interaction.response.send_message("❌ Please provide at least one player name. Use commas to separate multiple players.")
                return

            valid_teams = self.bot.db.guilds.get_guild_team_names(guild_id)
            valid_teams.append('Unassigned')
            if team_name not in valid_teams:
                await interaction.response.send_message(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}\nUse `/roster` to see team assignments or `/addteam` to create new teams.")
                return

            resolved_players = []
            failed_players = []

            for player_name in player_names:
                resolved = self.bot.db.players.resolve_player_name(player_name, guild_id)
                if resolved:
                    resolved_players.append(resolved)
                else:
                    failed_players.append(player_name)

            if failed_players:
                await interaction.response.send_message(f"❌ These players were not found in players table: {', '.join(failed_players)}\nUse `/addplayer <player>` to add them first.")
                return

            successful_assignments = []
            failed_assignments = []

            for player in resolved_players:
                success = self.bot.db.players.set_player_team(player, team_name, guild_id)
                if success:
                    successful_assignments.append(player)
                else:
                    failed_assignments.append(player)

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

    @app_commands.command(name="unassignplayer", description="Unassign a player from their team (set to Unassigned)")
    @app_commands.describe(player_name="Name of the player to unassign from their team")
    @app_commands.autocomplete(player_name=player_autocomplete)
    @require_guild_setup
    async def unassign_player_from_team(self, interaction: discord.Interaction, player_name: str):
        """Unassign a player from their team (set to Unassigned)."""
        try:
            guild_id = self.get_guild_id(interaction)

            resolved_player = self.bot.db.players.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return

            success = self.bot.db.players.set_player_team(resolved_player, 'Unassigned', guild_id)

            if success:
                await interaction.response.send_message(f"✅ Set **{resolved_player}** to **Unassigned**!")
            else:
                await interaction.response.send_message(f"❌ Failed to unassign **{resolved_player}** from team.")

        except Exception as e:
            logging.error(f"Error unassigning player from team: {e}")
            try:
                await interaction.response.send_message("❌ Error unassigning player from team", ephemeral=True)
            except discord.errors.HTTPException:
                await interaction.followup.send("❌ Error unassigning player from team", ephemeral=True)

    @app_commands.command(name="showmemberstatus", description="Show all players organized by member status")
    @require_guild_setup(defer=True)
    async def show_teams(self, interaction: discord.Interaction):
        """Show all players organized by member status."""
        try:
            guild_id = self.get_guild_id(interaction)

            all_players = self.bot.db.players.get_all_players_stats(guild_id)

            if not all_players:
                await interaction.followup.send("❌ No players found in players table. Use `/addplayer` to add players.")
                return

            status_groups = {}
            for player in all_players:
                status = player.get('member_status', 'member')
                if status == 'kicked':
                    continue

                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append(player)

            embed = discord.Embed(
                title="👥 Player Rosters by Status",
                description="Players organized by member status:",
                color=0x9932cc
            )

            status_info = {
                'member': {'icon': '👤', 'name': 'Members'},
                'trial': {'icon': '🔍', 'name': 'Trials'},
                'ally': {'icon': '🤝', 'name': 'Allies'}
            }

            total_players = 0
            for status in ['member', 'trial', 'ally']:
                if status in status_groups and status_groups[status]:
                    players = status_groups[status]
                    info = status_info[status]

                    player_list = []
                    for player in players:
                        team_name = player.get('team', 'Unassigned')
                        display_name = get_player_display_name(player['player_name'], team_name, guild_id, self.bot.db)
                        nickname_count = len(player.get('nicknames', []))
                        nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                        player_list.append(f"• **{display_name}**{nickname_text}")

                    embed.add_field(
                        name=f"{info['icon']} {info['name']} ({len(players)} players)",
                        value="\n".join(player_list),
                        inline=True
                    )
                    total_players += len(players)

            embed.set_footer(text=f"Total active players: {total_players} | Use /setmemberstatus to change player status")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing player rosters: {e}")
            await interaction.followup.send("❌ Error retrieving player information", ephemeral=True)

    @app_commands.command(name="showspecificteamroster", description="Show roster for a specific team")
    @app_commands.describe(team_name="Name of the team to show roster for")
    @require_guild_setup(defer=True)
    async def show_team_roster(self, interaction: discord.Interaction, team_name: str):
        """Show roster for a specific team."""
        try:
            guild_id = self.get_guild_id(interaction)

            valid_teams = self.bot.db.guilds.get_guild_team_names(guild_id)
            valid_teams.append('Unassigned')
            if team_name not in valid_teams:
                await interaction.followup.send(f"❌ Invalid team name. Valid teams: {', '.join(valid_teams)}\nUse `/roster` to see team assignments.")
                return

            team_players = self.bot.db.players.get_team_roster(team_name, guild_id)

            embed = discord.Embed(
                title=f"{team_name} Roster",
                description=f"Players in team {team_name}:",
                color=0x9932cc
            )

            if team_players:
                detailed_players = []
                for player in team_players:
                    display_name = get_player_display_name(player, team_name, guild_id, self.bot.db)
                    player_stats = self.bot.db.players.get_player_info(player, guild_id)
                    if player_stats:
                        nicknames = player_stats.get('nicknames', [])
                        nickname_text = f" ({', '.join(nicknames)})" if nicknames else ""
                        detailed_players.append(f"• **{display_name}**{nickname_text}")
                    else:
                        detailed_players.append(f"• **{display_name}**")

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
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing team roster: {e}")
            await interaction.followup.send("❌ Error retrieving team roster", ephemeral=True)

    @app_commands.command(name="addteam", description="Add a new team to the clan")
    @app_commands.describe(team_name="Name of the team to create (1W-50 characters, cannot be 'Unassigned')")
    @require_guild_setup
    async def add_team(self, interaction: discord.Interaction, team_name: str):
        """Add a new team to the guild."""
        try:
            guild_id = self.get_guild_id(interaction)
            success = self.bot.db.guilds.add_guild_team(guild_id, team_name)

            if success:
                embed = discord.Embed(
                    title="✅ Team Created!",
                    description=f"Successfully created team: **{team_name}**",
                    color=0x00ff00
                )
                embed.add_field(
                    name="Next Steps",
                    value=f"• Assign players with `/assignplayers players:player1,player2 team_name:{team_name}`\n• View team roster with `/showspecificteamroster {team_name}`\n• View player roster by team with `/roster`",
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

            current_teams = self.bot.db.guilds.get_guild_team_names(guild_id)
            team_exists = any(team.lower() == team_name.lower() for team in current_teams)

            if not team_exists:
                await interaction.response.send_message(f"❌ Team '{team_name}' not found. Use `/roster` to see available teams.")
                return

            teams_with_counts = self.bot.db.guilds.get_guild_teams_with_counts(guild_id)
            player_count = 0
            actual_team_name = team_name

            for team, count in teams_with_counts.items():
                if team.lower() == team_name.lower():
                    player_count = count
                    actual_team_name = team
                    break

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
                    success = self.bot.db.guilds.remove_guild_team(guild_id, actual_team_name)

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
                except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to clear reactions: {e}")

            except TimeoutError:
                await interaction.edit_original_response(content="❌ Team removal timed out.")
                try:
                    await msg.clear_reactions()
                except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to clear reactions: {e}")

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
            success = self.bot.db.guilds.rename_guild_team(guild_id, old_name, new_name)

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

    @app_commands.command(name="setteamtag", description="Set a tag for a team (1-8 chars, displays as 'TAG Playername')")
    @app_commands.describe(
        team_name="Team to set tag for",
        tag="Tag to display (1-8 characters, Unicode supported, no newlines)"
    )
    @app_commands.autocomplete(team_name=team_autocomplete)
    @require_guild_setup
    async def set_team_tag(self, interaction: discord.Interaction, team_name: str, tag: str):
        """Set a tag for a team in the guild."""
        try:
            guild_id = self.get_guild_id(interaction)

            if not has_admin_permission(interaction):
                await interaction.response.send_message(
                    "❌ Only server administrators can set team tags.",
                    ephemeral=True
                )
                return

            tag_stripped = tag.strip()
            if len(tag_stripped) < 1 or len(tag_stripped) > 8:
                await interaction.response.send_message(
                    f"❌ Tag must be 1-8 characters long (you provided {len(tag_stripped)} chars).\n"
                    f"Max 8 chars due to Switch 10-char name limit (8 tag + 1 separator + 1 name minimum).",
                    ephemeral=True
                )
                return

            success = self.bot.db.guilds.set_team_tag(guild_id, team_name, tag)

            if success:
                embed = discord.Embed(
                    title="✅ Team Tag Set!",
                    description=f"Successfully set tag for **{team_name}**",
                    color=0x00ff00
                )
                embed.add_field(name="Tag", value=f"`{tag_stripped}`", inline=True)
                embed.add_field(name="Display Format", value=f"`{tag_stripped} Playername`", inline=True)
                embed.set_footer(text="Tags will appear in roster, leaderboard, and stats views")
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    f"❌ Failed to set tag for team '{team_name}'.\n"
                    f"Make sure the team exists. Use `/roster` to see available teams.",
                    ephemeral=True
                )

        except Exception as e:
            logging.error(f"Error setting team tag: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error setting team tag", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error setting team tag", ephemeral=True)

    @app_commands.command(name="removeteamtag", description="Remove the tag from a team")
    @app_commands.describe(team_name="Team to remove tag from")
    @app_commands.autocomplete(team_name=team_with_tag_autocomplete)
    @require_guild_setup
    async def remove_team_tag(self, interaction: discord.Interaction, team_name: str):
        """Remove the tag from a team in the guild."""
        try:
            guild_id = self.get_guild_id(interaction)

            if not has_admin_permission(interaction):
                await interaction.response.send_message(
                    "❌ Only server administrators can remove team tags.",
                    ephemeral=True
                )
                return

            success = self.bot.db.guilds.remove_team_tag(guild_id, team_name)

            if success:
                embed = discord.Embed(
                    title="✅ Team Tag Removed!",
                    description=f"Successfully removed tag from **{team_name}**",
                    color=0x00ff00
                )
                embed.set_footer(text="Players from this team will now display without a tag")
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    f"❌ Failed to remove tag from team '{team_name}'.\n"
                    f"Make sure the team exists and has a tag set. Use `/showteamtags` to see teams with tags.",
                    ephemeral=True
                )

        except Exception as e:
            logging.error(f"Error removing team tag: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error removing team tag", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error removing team tag", ephemeral=True)

    @app_commands.command(name="showteamtags", description="Show all team tags for this guild")
    @require_guild_setup
    async def show_team_tags(self, interaction: discord.Interaction):
        """Show all team tags for the guild."""
        try:
            guild_id = self.get_guild_id(interaction)

            all_teams = self.bot.db.guilds.get_guild_team_names(guild_id)

            if not all_teams:
                await interaction.response.send_message("❌ No teams found. Use `/addteam` to create teams.", ephemeral=True)
                return

            all_teams.append('Unassigned')
            team_tags = self.bot.db.guilds.get_all_team_tags(guild_id)

            embed = discord.Embed(
                title="🏷️ Team Tags",
                description="Tags are displayed as 'TAG Playername' in roster, leaderboard, and stats.\nMax 8 characters (Switch 10-char limit).",
                color=0x9932cc
            )

            teams_with_tags = []
            teams_without_tags = []

            for team in all_teams:
                tag = team_tags.get(team)
                if tag:
                    teams_with_tags.append((team, tag))
                else:
                    teams_without_tags.append(team)

            if teams_with_tags:
                tag_text = []
                for team, tag in sorted(teams_with_tags):
                    tag_text.append(f"**{team}**: `{tag}`")

                embed.add_field(
                    name=f"Teams with Tags ({len(teams_with_tags)})",
                    value="\n".join(tag_text),
                    inline=False
                )

            if teams_without_tags:
                no_tag_text = ", ".join(f"**{team}**" for team in sorted(teams_without_tags))
                if len(no_tag_text) > 1024:
                    no_tag_text = no_tag_text[:1020] + "..."

                embed.add_field(
                    name=f"Teams without Tags ({len(teams_without_tags)})",
                    value=no_tag_text,
                    inline=False
                )

            embed.set_footer(text="Use /setteamtag to add tags | /removeteamtag to remove tags")
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f"Error showing team tags: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving team tags", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving team tags", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TeamCog(bot))
