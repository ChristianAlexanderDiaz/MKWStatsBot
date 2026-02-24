"""Player management commands."""

import re
import logging
import discord
from discord import app_commands
from typing import Optional

from .base_cog import BaseCog, require_guild_setup
from ..database import DatabaseManager
from ..utils.formatters import country_code_to_flag, get_player_display_name
from ..utils.validators import has_admin_permission


class PlayerCog(BaseCog):
    """Player roster management, linking, and country flag commands."""

    async def guild_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for guild names (bot owner only)."""
        try:
            if not DatabaseManager.is_bot_owner(interaction.user.id):
                return []

            guilds = self.bot.guilds

            guild_choices = []
            for guild in guilds:
                if current.lower() in guild.name.lower():
                    guild_choices.append(app_commands.Choice(name=guild.name, value=str(guild.id)))

            return guild_choices[:25]
        except Exception as e:
            logging.error(f"Error in guild autocomplete: {e}")
            return []

    @app_commands.command(name="roster", description="Show complete guild roster organized by teams")
    @require_guild_setup
    async def show_full_roster(self, interaction: discord.Interaction):
        """Show the complete clan roster organized by teams."""
        try:
            guild_id = self.get_guild_id(interaction)
            all_players = self.bot.db.get_all_players_stats(guild_id)

            if not all_players:
                await interaction.response.send_message("❌ No players found in players table. Use `/addplayer <player>` to add players.")
                return

            embed = discord.Embed(
                title="👥 Complete Clan Roster",
                description=f"All {len(all_players)} clan members organized by teams:",
                color=0x9932cc
            )

            teams = {}
            for player in all_players:
                team = player.get('team', 'Unassigned')
                if team not in teams:
                    teams[team] = []
                teams[team].append(player)

            for team_name, players in teams.items():
                if players:
                    player_list = []

                    for player in players:
                        display_name = get_player_display_name(player['player_name'], team_name, guild_id, self.bot.db)
                        nickname_count = len(player.get('nicknames', []))
                        nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                        player_list.append(f"• **{display_name}**{nickname_text}")

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
        user="Discord user to add (@mention)",
        ingame_name="In-game name for OCR matching (optional, defaults to display name)",
        country="2-letter country code (US, CA, GB, JP, etc.) for flag display"
    )
    @require_guild_setup
    async def add_player_to_roster(self, interaction: discord.Interaction, user: discord.Member, ingame_name: str = None, country: str = None):
        """Add a player to the clan roster with Discord user ID."""
        try:
            guild_id = self.get_guild_id(interaction)

            role_config = self.bot.db.get_guild_role_config(guild_id)
            if not role_config:
                await interaction.response.send_message(
                    "❌ Guild roles are not configured. Please run `/setup` first to configure Member, Trial, and Ally roles.",
                    ephemeral=True
                )
                return

            user_role_ids = [role.id for role in user.roles]

            if role_config['role_member_id'] in user_role_ids:
                member_status = 'member'
                role_name = "Member"
            elif role_config['role_trial_id'] in user_role_ids:
                member_status = 'trial'
                role_name = "Trial"
            elif role_config['role_ally_id'] in user_role_ids:
                member_status = 'ally'
                role_name = "Ally"
            else:
                await interaction.response.send_message(
                    f"❌ {user.mention} doesn't have a Member, Trial, or Ally role.\n"
                    f"Please assign them one of these roles before adding to the roster.",
                    ephemeral=True
                )
                return

            country_code = None
            if country:
                country = country.upper().strip()
                if len(country) == 2 and country.isalpha():
                    country_code = country
                else:
                    await interaction.response.send_message(
                        f"❌ Invalid country code '{country}'. Use 2-letter codes like US, CA, GB, JP.",
                        ephemeral=True
                    )
                    return

            player_name = ingame_name if ingame_name else user.display_name

            success = self.bot.db.add_roster_player_with_discord(
                discord_user_id=user.id,
                player_name=player_name,
                display_name=user.display_name,
                discord_username=user.name,
                member_status=member_status,
                added_by=str(interaction.user),
                guild_id=guild_id,
                country_code=country_code
            )

            if success:
                embed = discord.Embed(
                    title="✅ Player Added",
                    description=f"Added {user.mention} to the clan roster!",
                    color=0x00ff00
                )
                embed.add_field(name="In-Game Name", value=player_name, inline=True)
                embed.add_field(name="Role Detected", value=f"{role_name}", inline=True)
                embed.add_field(name="Discord Username", value=f"@{user.name}", inline=True)

                if ingame_name:
                    embed.set_footer(text="OCR will match using the in-game name you provided")
                else:
                    embed.set_footer(text=f"OCR will match using display name. Use ingame_name parameter if different.")

                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    f"❌ {user.mention} is already in the roster or couldn't be added.",
                    ephemeral=True
                )

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

    @app_commands.command(name="linkplayer", description="Link an existing player to their Discord account")
    @app_commands.describe(
        player_name="Name of the existing player in the roster",
        user="Discord user to link (@mention)"
    )
    @require_guild_setup
    async def link_player_to_discord(self, interaction: discord.Interaction, player_name: str, user: discord.Member):
        """Link an existing player to a Discord user."""
        try:
            guild_id = self.get_guild_id(interaction)

            role_config = self.bot.db.get_guild_role_config(guild_id)
            if not role_config:
                await interaction.response.send_message(
                    "❌ Guild roles are not configured. Please run `/setup` first.",
                    ephemeral=True
                )
                return

            user_role_ids = [role.id for role in user.roles]

            if role_config['role_member_id'] in user_role_ids:
                member_status = 'member'
                role_name = "Member"
            elif role_config['role_trial_id'] in user_role_ids:
                member_status = 'trial'
                role_name = "Trial"
            elif role_config['role_ally_id'] in user_role_ids:
                member_status = 'ally'
                role_name = "Ally"
            else:
                await interaction.response.send_message(
                    f"❌ {user.mention} doesn't have a Member, Trial, or Ally role.\n"
                    f"Please assign them one of these roles before linking.",
                    ephemeral=True
                )
                return

            success = self.bot.db.link_player_to_discord_user(
                player_name=player_name,
                discord_user_id=user.id,
                display_name=user.display_name,
                discord_username=user.name,
                member_status=member_status,
                guild_id=guild_id
            )

            if success:
                embed = discord.Embed(
                    title="🔗 Player Linked",
                    description=f"Successfully linked **{player_name}** to {user.mention}!",
                    color=0x00ff00
                )
                embed.add_field(name="Player Name", value=player_name, inline=True)
                embed.add_field(name="Discord User", value=user.mention, inline=True)
                embed.add_field(name="Role Detected", value=role_name, inline=True)
                embed.set_footer(text="Role status and display name will now auto-sync from Discord")
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    f"❌ Could not link **{player_name}**. Player may not exist or is already linked.",
                    ephemeral=True
                )

        except Exception as e:
            logging.error(f"Error linking player: {e}")
            await interaction.response.send_message("❌ Error linking player to Discord account", ephemeral=True)

    @app_commands.command(name="listunlinked", description="Show players not yet linked to Discord accounts")
    @require_guild_setup
    async def list_unlinked_players(self, interaction: discord.Interaction):
        """List all players without Discord user ID links."""
        try:
            guild_id = self.get_guild_id(interaction)

            unlinked_players = self.bot.db.get_unlinked_players(guild_id)

            if not unlinked_players:
                embed = discord.Embed(
                    title="✅ All Players Linked",
                    description="All active players are linked to Discord accounts!",
                    color=0x00ff00
                )
                await interaction.response.send_message(embed=embed)
                return

            embed = discord.Embed(
                title="🔗 Unlinked Players",
                description=f"Found {len(unlinked_players)} players without Discord links:",
                color=0xffa500
            )

            teams = {}
            for player in unlinked_players:
                team = player.get('team', 'Unassigned')
                if team not in teams:
                    teams[team] = []
                teams[team].append(player)

            for team, players in teams.items():
                player_list = []
                for p in players:
                    wars = p.get('war_count', 0)
                    score = p.get('total_score', 0)
                    status = p.get('member_status', 'unknown').title()
                    player_list.append(f"• **{p['player_name']}** ({status}) - {wars} wars, {score} pts")

                players_text = "\n".join(player_list)
                if len(players_text) > 1024:
                    players_text = players_text[:1020] + "..."

                embed.add_field(name=f"Team: {team}", value=players_text, inline=False)

            embed.add_field(
                name="💡 How to Link",
                value="Use `/linkplayer player:PlayerName user:@DiscordUser` to link each player",
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f"Error listing unlinked players: {e}")
            await interaction.response.send_message("❌ Error retrieving unlinked players", ephemeral=True)

    @app_commands.command(name="syncstatus", description="Sync all player roles from Discord")
    @require_guild_setup
    async def sync_player_status(self, interaction: discord.Interaction):
        """Sync member_status for all linked players from their Discord roles."""
        try:
            guild_id = self.get_guild_id(interaction)

            role_config = self.bot.db.get_guild_role_config(guild_id)
            if not role_config:
                await interaction.response.send_message(
                    "❌ Guild roles are not configured. Please run `/setup` first.",
                    ephemeral=True
                )
                return

            all_players = self.bot.db.get_all_players_stats(guild_id)
            linked_players = [p for p in all_players if p.get('discord_user_id')]

            if not linked_players:
                await interaction.response.send_message(
                    "❌ No players are linked to Discord accounts yet.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            synced = 0
            changes = []

            for player in linked_players:
                discord_user_id = player.get('discord_user_id')
                current_status = player.get('member_status', 'unknown')

                member = interaction.guild.get_member(discord_user_id)
                if not member:
                    continue

                user_role_ids = [role.id for role in member.roles]
                new_status = None
                role_name = None

                if role_config['role_member_id'] in user_role_ids:
                    new_status = 'member'
                    role_name = "Member"
                elif role_config['role_trial_id'] in user_role_ids:
                    new_status = 'trial'
                    role_name = "Trial"
                elif role_config['role_ally_id'] in user_role_ids:
                    new_status = 'ally'
                    role_name = "Ally"

                if new_status and new_status != current_status:
                    self.bot.db.sync_player_role(discord_user_id, new_status, guild_id)
                    self.bot.db.sync_player_discord_info(discord_user_id, member.display_name, member.name, guild_id)
                    changes.append(f"• **{player['player_name']}**: {current_status.title()} → {role_name}")
                    synced += 1
                elif new_status:
                    self.bot.db.sync_player_discord_info(discord_user_id, member.display_name, member.name, guild_id)
                    synced += 1

            embed = discord.Embed(
                title="🔄 Role Sync Complete",
                description=f"Synced {synced} out of {len(linked_players)} linked players",
                color=0x00ff00
            )

            if changes:
                changes_text = "\n".join(changes)
                if len(changes_text) > 1024:
                    changes_text = changes_text[:1020] + "..."
                embed.add_field(name="📝 Status Changes", value=changes_text, inline=False)
            else:
                embed.add_field(name="✅ No Changes", value="All player roles are already up to date!", inline=False)

            embed.set_footer(text="Display names and usernames were also updated")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error syncing player status: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error syncing player roles", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error syncing player roles", ephemeral=True)

    @app_commands.command(name="setcountry", description="Set country flag for stats display")
    @app_commands.describe(
        country="2-letter country code (US, CA, GB, JP, etc.)",
        user="Discord user (optional - defaults to yourself)"
    )
    @require_guild_setup
    async def set_country(self, interaction: discord.Interaction, country: str, user: discord.Member = None):
        """Set country code for a player's flag display."""
        try:
            guild_id = self.get_guild_id(interaction)

            country = country.upper().strip()
            if len(country) != 2 or not country.isalpha():
                await interaction.response.send_message(
                    f"❌ Invalid country code '{country}'. Use 2-letter codes like US, CA, GB, JP.",
                    ephemeral=True
                )
                return

            target_user = user if user else interaction.user
            target_member = interaction.guild.get_member(target_user.id)

            if not target_member:
                await interaction.response.send_message("❌ User not found in server.", ephemeral=True)
                return

            if user and user != interaction.user:
                if not has_admin_permission(interaction):
                    await interaction.response.send_message(
                        "❌ Only administrators can set country for other players.",
                        ephemeral=True
                    )
                    return

            with self.bot.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET country_code = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = %s AND guild_id = %s AND is_active = TRUE
                """, (country, target_member.id, guild_id))

                if cursor.rowcount == 0:
                    await interaction.response.send_message(
                        f"❌ {target_member.mention} is not in the active roster.",
                        ephemeral=True
                    )
                    return

                conn.commit()

            flag = country_code_to_flag(country)

            embed = discord.Embed(
                title="🌍 Country Flag Updated",
                description=f"Set country flag to {flag} ({country})",
                color=0x00ff00
            )

            if user:
                embed.add_field(name="Player", value=target_member.mention, inline=True)
            else:
                embed.add_field(name="Player", value="You", inline=True)

            embed.add_field(name="Flag", value=flag, inline=True)
            embed.set_footer(text="Your flag will appear in /stats leaderboard")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f"Error setting country: {e}")
            await interaction.response.send_message("❌ Error setting country flag", ephemeral=True)

    @app_commands.command(name="setflag", description="[ADMIN] Set country flag for any player across guilds")
    @app_commands.describe(
        player_name="Player name (case-sensitive)",
        country="2-letter country code (US, CA, GB, JP, etc.)",
        guild_name="Select the guild where the player is located"
    )
    @app_commands.autocomplete(guild_name=guild_autocomplete)
    async def set_flag_admin(self, interaction: discord.Interaction, player_name: str, country: str, guild_name: str):
        """Admin-only command to set country flag for any player across different guilds."""
        try:
            if not DatabaseManager.is_bot_owner(interaction.user.id):
                await interaction.response.send_message(
                    "❌ This command is restricted to bot administrators only.",
                    ephemeral=True
                )
                return

            country = country.upper().strip()
            if len(country) != 2 or not country.isalpha():
                await interaction.response.send_message(
                    f"❌ Invalid country code '{country}'. Use 2-letter codes like US, CA, GB, JP.",
                    ephemeral=True
                )
                return

            try:
                target_guild_id = int(guild_name)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid guild selection. Please select a guild from the dropdown.",
                    ephemeral=True
                )
                return

            guild = self.bot.get_guild(target_guild_id)
            guild_display_name = guild.name if guild else f"Guild {target_guild_id}"

            with self.bot.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET country_code = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE LOWER(player_name) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """, (country, player_name, target_guild_id))

                if cursor.rowcount == 0:
                    await interaction.response.send_message(
                        f"❌ Player '{player_name}' not found in **{guild_display_name}**. Check the player name (case-sensitive).",
                        ephemeral=True
                    )
                    return

                conn.commit()

            flag = country_code_to_flag(country)

            embed = discord.Embed(
                title="🌍 Admin Flag Update",
                description=f"Successfully set country flag to {flag} ({country})",
                color=0x00ff00
            )

            embed.add_field(name="Player", value=player_name, inline=True)
            embed.add_field(name="Guild", value=guild_display_name, inline=True)
            embed.add_field(name="Flag", value=flag, inline=True)
            embed.set_footer(text="Flag will appear in stats and global leaderboard")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Error in /setflag admin command: {e}")
            await interaction.response.send_message("❌ Error setting country flag", ephemeral=True)

    @app_commands.command(name="bulksetcountry", description="Set countries for multiple players at once")
    @app_commands.describe(
        players_countries="Format: @User:US, PlayerName:CA, @User2:GB (supports mentions and names)"
    )
    @require_guild_setup
    async def bulk_set_country(self, interaction: discord.Interaction, players_countries: str):
        """Set countries for multiple players at once."""
        try:
            await interaction.response.defer(ephemeral=True)

            guild_id = self.get_guild_id(interaction)

            pairs = [pair.strip() for pair in players_countries.split(',')]

            updated = []
            errors = []

            mention_pattern = re.compile(r'<@!?(\d+)>')

            for pair in pairs:
                if ':' not in pair:
                    errors.append(f"❌ Invalid format: `{pair}` (use @User:CC or Player:CC)")
                    continue

                player_identifier, country_code = pair.split(':', 1)
                player_identifier = player_identifier.strip()
                country_code = country_code.strip().upper()

                if len(country_code) != 2 or not country_code.isalpha():
                    errors.append(f"❌ Invalid country code: `{country_code}`")
                    continue

                mention_match = mention_pattern.search(player_identifier)

                if mention_match:
                    user_id = int(mention_match.group(1))
                    member = interaction.guild.get_member(user_id)

                    if not member:
                        errors.append(f"❌ User not found in server: <@{user_id}>")
                        continue

                    with self.bot.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE players
                            SET country_code = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE discord_user_id = %s AND guild_id = %s AND is_active = TRUE
                        """, (country_code, user_id, guild_id))

                        if cursor.rowcount > 0:
                            flag = country_code_to_flag(country_code)
                            updated.append(f"{flag} {member.mention}")
                            conn.commit()
                        else:
                            errors.append(f"❌ {member.mention} not in active roster")
                else:
                    player_name = player_identifier

                    with self.bot.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE players
                            SET country_code = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                        """, (country_code, player_name, guild_id))

                        if cursor.rowcount > 0:
                            flag = country_code_to_flag(country_code)
                            updated.append(f"{flag} {player_name}")
                            conn.commit()
                        else:
                            errors.append(f"❌ Player not found: {player_name}")

            embed = discord.Embed(
                title="🌍 Bulk Country Update",
                color=0x00ff00 if updated else 0xff0000
            )

            if updated:
                if len(updated) <= 25:
                    embed.add_field(
                        name=f"✅ Updated {len(updated)} players",
                        value="\n".join(updated),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"✅ Updated {len(updated)} players",
                        value="\n".join(updated[:25]) + f"\n... and {len(updated) - 25} more",
                        inline=False
                    )

            if errors:
                error_text = "\n".join(errors[:10])
                if len(errors) > 10:
                    error_text += f"\n... and {len(errors) - 10} more errors"
                embed.add_field(
                    name=f"⚠️ Errors ({len(errors)})",
                    value=error_text,
                    inline=False
                )

            if not updated and not errors:
                embed.description = "No players processed"

            embed.set_footer(text="Country codes: https://www.iban.com/country-codes")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Error in bulk set country: {e}")
            await interaction.followup.send("❌ Error setting countries", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PlayerCog(bot))
