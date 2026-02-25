"""Guild setup and configuration commands."""

import json
import logging
import traceback
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from .base_cog import BaseCog, require_guild_setup
from ..database import DatabaseManager
from ..utils.validators import has_admin_permission


class GuildCog(BaseCog):
    """Guild initialization, channel config, role config, and admin commands."""

    @app_commands.command(name="setup", description="Initialize guild for Mario Kart stats tracking")
    @app_commands.describe(
        teamname="Name for the first team",
        players="Players to add (@mention users, space-separated): '@User1 @User2 @User3'",
        results_channel="Channel where OCR will run (e.g., #results)",
        role_member="Role for full members (@Role)",
        role_trial="Role for trial members (@Role)",
        role_ally="Role for ally members (@Role)"
    )
    async def setup_guild(
        self,
        interaction: discord.Interaction,
        teamname: str,
        players: str,
        results_channel: discord.TextChannel,
        role_member: discord.Role,
        role_trial: discord.Role,
        role_ally: discord.Role
    ):
        """Initialize guild with basic setup and role configuration."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)

            if self.is_guild_initialized(guild_id):
                await interaction.response.send_message("✅ Guild is already set up! Use other commands to manage your clan.", ephemeral=True)
                return

            import re
            user_id_pattern = r'<@!?(\d+)>'
            user_ids = re.findall(user_id_pattern, players)

            if not user_ids:
                await interaction.response.send_message(
                    "❌ You must @mention at least one Discord user.\nExample: `/setup teamname:MyTeam players:@User1 @User2 ...`",
                    ephemeral=True
                )
                return

            player_members = []
            for user_id_str in user_ids:
                member = interaction.guild.get_member(int(user_id_str))
                if member:
                    player_members.append(member)
                else:
                    await interaction.response.send_message(
                        f"❌ Could not find member with ID {user_id_str} in this server.",
                        ephemeral=True
                    )
                    return

            bot_member = interaction.guild.get_member(self.bot.user.id)
            if bot_member:
                channel_perms = results_channel.permissions_for(bot_member)
                required_perms = {
                    'view_channel': channel_perms.view_channel,
                    'send_messages': channel_perms.send_messages,
                    'read_message_history': channel_perms.read_message_history,
                    'add_reactions': channel_perms.add_reactions
                }
                missing_perms = [name for name, has in required_perms.items() if not has]
                if missing_perms:
                    await interaction.response.send_message(
                        f"❌ Bot is missing permissions in {results_channel.mention}: {', '.join(missing_perms)}",
                        ephemeral=True
                    )
                    return

            servername = interaction.guild.name if interaction.guild else f"Guild {guild_id}"

            with self.bot.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO guild_configs (
                        guild_id, guild_name, team_names, is_active,
                        role_member_id, role_trial_id, role_ally_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        is_active = EXCLUDED.is_active,
                        role_member_id = EXCLUDED.role_member_id,
                        role_trial_id = EXCLUDED.role_trial_id,
                        role_ally_id = EXCLUDED.role_ally_id,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, servername, json.dumps([teamname]), True, role_member.id, role_trial.id, role_ally.id))

                added_players = []
                role_detection = []

                for member in player_members:
                    user_role_ids = [role.id for role in member.roles]

                    if role_member.id in user_role_ids:
                        member_status = 'member'
                        role_name = role_member.name
                    elif role_trial.id in user_role_ids:
                        member_status = 'trial'
                        role_name = role_trial.name
                    elif role_ally.id in user_role_ids:
                        member_status = 'ally'
                        role_name = role_ally.name
                    else:
                        await interaction.response.send_message(
                            f"❌ {member.mention} doesn't have a Member, Trial, or Ally role.\n"
                            f"Please assign them one of these roles first: {role_member.mention}, {role_trial.mention}, or {role_ally.mention}",
                            ephemeral=True
                        )
                        return

                    player_name = member.display_name

                    cursor.execute("""
                        INSERT INTO players (
                            discord_user_id, player_name, display_name, discord_username,
                            added_by, guild_id, team, nicknames, is_active, member_status,
                            last_role_sync
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (player_name, guild_id) DO UPDATE SET
                            discord_user_id = EXCLUDED.discord_user_id,
                            display_name = EXCLUDED.display_name,
                            discord_username = EXCLUDED.discord_username,
                            is_active = TRUE,
                            team = EXCLUDED.team,
                            member_status = EXCLUDED.member_status,
                            last_role_sync = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                    """, (member.id, player_name, member.display_name, member.name,
                          f"setup_{interaction.user.name}", guild_id, teamname, [], True, member_status))

                    added_players.append(player_name)
                    role_detection.append(f"{player_name} → {role_name}")

                conn.commit()

            ocr_success = self.bot.db.guilds.set_ocr_channel(guild_id, results_channel.id)
            if not ocr_success:
                logging.warning(f"Failed to set OCR channel during setup for guild {guild_id}")

            embed = discord.Embed(
                title="🚀 Guild Setup Complete!",
                description=f"Successfully initialized **{servername}** for Mario Kart clan tracking with Discord role integration.",
                color=0x00ff00
            )

            embed.add_field(name="Server Name", value=servername, inline=True)
            embed.add_field(name="Guild ID", value=str(guild_id), inline=True)
            embed.add_field(name="Team Name", value=teamname, inline=True)
            embed.add_field(name="Players Added", value=f"{len(added_players)} players", inline=True)

            embed.add_field(
                name="👥 Role Configuration",
                value=(
                    f"**Member**: {role_member.mention}\n"
                    f"**Trial**: {role_trial.mention}\n"
                    f"**Ally**: {role_ally.mention}"
                ),
                inline=False
            )

            role_detection_text = "\n".join(role_detection)
            if len(role_detection_text) > 1000:
                role_detection_text = role_detection_text[:1000] + "..."
            embed.add_field(name="🎭 Players & Roles Detected", value=role_detection_text, inline=False)

            embed.add_field(
                name="📷 OCR Channel Set",
                value=f"Automatic image scanning enabled in {results_channel.mention}",
                inline=False
            )

            embed.add_field(
                name="🎯 Next Steps",
                value=(
                    "• Add more players: `/addplayer @user`\n"
                    "• Link legacy players: `/linkplayer player:Name user:@User`\n"
                    "• Start tracking wars: `/addwar`\n"
                    "• View stats: `/stats [player]`\n"
                    "• Sync roles: `/syncstatus`"
                ),
                inline=False
            )

            embed.set_footer(text="Your guild is now ready with automatic role-based member management!")
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f"Error in guild setup: {e}")
            await interaction.response.send_message("❌ Error setting up guild. Please try again or contact support.", ephemeral=True)

    @app_commands.command(name="setroles", description="Configure Member/Trial/Ally roles for guild")
    @app_commands.describe(
        role_member="Role for full members (@Role)",
        role_trial="Role for trial members (@Role)",
        role_ally="Role for ally members (@Role)"
    )
    @require_guild_setup
    async def set_roles(self, interaction: discord.Interaction, role_member: discord.Role, role_trial: discord.Role, role_ally: discord.Role):
        """Configure roles for existing guild."""
        try:
            guild_id = self.get_guild_id(interaction)

            success = self.bot.db.guilds.set_guild_role_config(
                guild_id=guild_id,
                role_member_id=role_member.id,
                role_trial_id=role_trial.id,
                role_ally_id=role_ally.id
            )

            if success:
                embed = discord.Embed(
                    title="✅ Roles Configured!",
                    description="Successfully configured Discord roles for member management",
                    color=0x00ff00
                )

                embed.add_field(
                    name="👥 Role Configuration",
                    value=(
                        f"**Member**: {role_member.mention}\n"
                        f"**Trial**: {role_trial.mention}\n"
                        f"**Ally**: {role_ally.mention}"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="🎯 Next Steps",
                    value=(
                        "• Use `/addplayer @user` to add new players (auto-detects role)\n"
                        "• Use `/linkplayer player:Name user:@User` to link existing players\n"
                        "• Use `/syncstatus` to sync all player roles from Discord\n"
                        "• Use `/listunlinked` to see players needing links"
                    ),
                    inline=False
                )

                embed.set_footer(text="Player status will now auto-sync from Discord roles!")
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to configure roles. Try again.", ephemeral=True)

        except Exception as e:
            logging.error(f"Error setting roles: {e}")
            await interaction.response.send_message("❌ Error configuring roles", ephemeral=True)

    @app_commands.command(name="setchannel", description="Set the channel for automatic OCR processing of uploaded images")
    @app_commands.describe(channel="Channel where images will be automatically scanned for Mario Kart results")
    @require_guild_setup
    async def set_ocr_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for automatic OCR processing."""
        try:
            guild_id = self.get_guild_id(interaction)

            bot_member = interaction.guild.get_member(self.bot.user.id)
            if not bot_member:
                await interaction.response.send_message("❌ Unable to get bot member information.", ephemeral=True)
                return

            channel_perms = channel.permissions_for(bot_member)
            required_perms = {
                'view_channel': channel_perms.view_channel,
                'send_messages': channel_perms.send_messages,
                'read_message_history': channel_perms.read_message_history,
                'add_reactions': channel_perms.add_reactions,
                'use_application_commands': channel_perms.use_application_commands
            }

            missing_perms = [name for name, has_perm in required_perms.items() if not has_perm]
            if missing_perms:
                missing_list = "\n".join([f"• {name.replace('_', ' ').title()}" for name in missing_perms])
                await interaction.response.send_message(
                    f"❌ **Missing required permissions in {channel.mention}:**\n{missing_list}\n\n"
                    f"Please grant these permissions and try again, or use `/checkpermissions {channel.mention}` to verify.",
                    ephemeral=True
                )
                return

            success = self.bot.db.guilds.set_ocr_channel(guild_id, channel.id)

            if success:
                embed = discord.Embed(
                    title="✅ OCR Channel Set!",
                    description=f"Automatic image scanning is now enabled in {channel.mention}",
                    color=0x00ff00
                )
                embed.add_field(
                    name="📷 How it works",
                    value="• Upload a PNG image to the configured channel\n• Bot automatically scans for Mario Kart results\n• Confirm or cancel the detected scores\n• Use `/scanimage` as backup if auto-scan misses something",
                    inline=False
                )
                embed.add_field(
                    name="🔧 Management",
                    value=f"• Current channel: {channel.mention}\n• Change channel: `/setchannel #new-channel`\n• Check permissions: `/checkpermissions {channel.mention}`",
                    inline=False
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to set OCR channel. Please try again.", ephemeral=True)

        except Exception as e:
            logging.error(f"Error setting OCR channel: {e}")
            await interaction.response.send_message(f"❌ Error setting OCR channel: {str(e)}", ephemeral=True)

    @app_commands.command(name="checkpermissions", description="Check bot permissions in a channel for OCR functionality")
    @app_commands.describe(channel="Channel to check permissions for (defaults to current channel)")
    async def check_permissions(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Check bot permissions in the specified channel for OCR functionality."""
        try:
            target_channel = channel if channel else interaction.channel

            bot_member = interaction.guild.get_member(self.bot.user.id)
            if not bot_member:
                await interaction.response.send_message("❌ Unable to get bot member information.", ephemeral=True)
                return

            channel_perms = target_channel.permissions_for(bot_member)

            required_perms = {
                'view_channel': channel_perms.view_channel,
                'send_messages': channel_perms.send_messages,
                'read_message_history': channel_perms.read_message_history,
                'add_reactions': channel_perms.add_reactions,
                'use_application_commands': channel_perms.use_application_commands
            }

            embed = discord.Embed(
                title="🔐 Bot Permissions Check",
                description=f"Checking permissions in #{target_channel.name}",
                color=0x00ff00 if all(required_perms.values()) else 0xff4444
            )

            perms_text = ""
            for perm_name, has_perm in required_perms.items():
                status = "✅" if has_perm else "❌"
                display_name = perm_name.replace('_', ' ').title()
                perms_text += f"{status} {display_name}\n"

            embed.add_field(
                name="Required Permissions",
                value=perms_text,
                inline=False
            )

            missing_perms = [name for name, has_perm in required_perms.items() if not has_perm]
            if missing_perms:
                embed.add_field(
                    name="❌ Status",
                    value=f"Missing {len(missing_perms)} required permissions.\nAutomatic OCR and `/scanimage` may not work properly.",
                    inline=False
                )
                embed.add_field(
                    name="Missing Permissions",
                    value="\n".join([f"• {name.replace('_', ' ').title()}" for name in missing_perms]),
                    inline=False
                )
            else:
                embed.add_field(
                    name="✅ Status",
                    value="All required permissions are available!\nAutomatic OCR and `/scanimage` will work properly.",
                    inline=False
                )

            embed.set_footer(text="These permissions are required for OCR image processing (no manage_messages needed)")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f"Error checking permissions: {e}")
            await interaction.response.send_message(f"❌ Error checking permissions: {str(e)}", ephemeral=True)

    @app_commands.command(name="debugroles", description="[DEBUG] Check role filtering for /stats command")
    @require_guild_setup
    async def debug_roles(self, interaction: discord.Interaction):
        """Debug command to check why /stats shows 'No members found'."""
        await interaction.response.defer(ephemeral=True)

        guild_id = self.get_guild_id(interaction)

        role_config = self.bot.db.guilds.get_guild_role_config(guild_id)

        debug_lines = []
        debug_lines.append("=== ROLE CONFIGURATION ===")
        if role_config and role_config.get('role_member_id'):
            member_role_id = role_config['role_member_id']

            discord_role = interaction.guild.get_role(member_role_id)
            if discord_role:
                debug_lines.append(f"Member Role: {discord_role.name} (ID: {member_role_id})")
                debug_lines.append(f"Role exists in Discord: YES")
            else:
                debug_lines.append(f"Member Role ID: {member_role_id}")
                debug_lines.append(f"Role exists in Discord: NO - ROLE NOT FOUND!")
        else:
            debug_lines.append("No Member role configured")

        debug_lines.append("\n=== LINKED PLAYERS ===")

        roster_stats = self.bot.db.players.get_all_players_stats(guild_id)

        linked_players = [p for p in roster_stats if p.get('discord_user_id')]
        debug_lines.append(f"Total linked players: {len(linked_players)}\n")

        players_with_role = 0
        players_without_role = 0
        players_not_in_guild = 0

        for player in linked_players:
            discord_user_id = player.get('discord_user_id')
            player_name = player.get('player_name')
            member_status = player.get('member_status', 'member')

            member = interaction.guild.get_member(discord_user_id)

            if not member:
                debug_lines.append(f"❌ {player_name} - NOT IN GUILD (ID: {discord_user_id})")
                players_not_in_guild += 1
                continue

            if role_config and role_config.get('role_member_id'):
                member_role_id = role_config['role_member_id']
                user_role_ids = [role.id for role in member.roles]
                has_role = member_role_id in user_role_ids

                role_list = ", ".join([r.name for r in member.roles if r.name != "@everyone"])

                if has_role:
                    debug_lines.append(f"✅ {player_name} - HAS ROLE")
                    debug_lines.append(f"   Discord: {member.name}, Status: {member_status}")
                    debug_lines.append(f"   Roles: {role_list}\n")
                    players_with_role += 1
                else:
                    debug_lines.append(f"❌ {player_name} - MISSING ROLE")
                    debug_lines.append(f"   Discord: {member.name}, Status: {member_status}")
                    debug_lines.append(f"   Roles: {role_list}")
                    debug_lines.append(f"   Looking for role ID: {member_role_id}")
                    debug_lines.append(f"   Has role IDs: {user_role_ids}\n")
                    players_without_role += 1

        debug_lines.append("=== SUMMARY ===")
        debug_lines.append(f"Players with role: {players_with_role}")
        debug_lines.append(f"Players without role: {players_without_role}")
        debug_lines.append(f"Players not in guild: {players_not_in_guild}")

        if players_with_role == 0:
            debug_lines.append("\n⚠️ THIS IS WHY /stats SHOWS 'No members found'")
            if players_without_role > 0:
                debug_lines.append("→ Linked players don't have the configured Member role")

        debug_text = "\n".join(debug_lines)
        if len(debug_text) > 1900:
            chunks = [debug_text[i:i+1900] for i in range(0, len(debug_text), 1900)]
            for chunk in chunks:
                await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{debug_text}\n```", ephemeral=True)

    @app_commands.command(name="help", description="Show bot commands")
    @require_guild_setup
    async def help_command(self, interaction: discord.Interaction):
        """Show bot help information."""
        embed = discord.Embed(
            title="Commands",
            color=0x2b2d31
        )

        embed.add_field(
            name="Stats & Roster",
            value=(
                "`/stats [player]` - View stats or leaderboard\n"
                "`/roster` - View roster by teams\n"
                "`/addplayer <name> [status]` - Add player\n"
                "`/removeplayer <name>` - Remove player"
            ),
            inline=False
        )

        embed.add_field(
            name="Wars",
            value=(
                "`/wars [limit]` - View recent wars\n"
                "`/addwar <scores>` - Add war manually\n"
                "`/appendplayertowar <id> <scores>` - Add players to war\n"
                "`/removewar <id>` - Delete war"
            ),
            inline=False
        )

        embed.add_field(
            name="Teams",
            value=(
                "`/showallteams` - View all teams\n"
                "`/addteam <name>` - Create team\n"
                "`/removeteam <name>` - Delete team\n"
                "`/renameteam <old> <new>` - Rename team\n"
                "`/assignplayerstoteam <players> <team>` - Assign to team\n"
                "`/unassignplayer <name>` - Unassign player"
            ),
            inline=False
        )

        embed.add_field(
            name="Nicknames",
            value=(
                "`/addnickname <player> <nick>` - Add nickname\n"
                "`/removenickname <player> <nick>` - Remove nickname\n"
                "`/nicknamesfor <player>` - View nicknames"
            ),
            inline=False
        )

        embed.add_field(
            name="Member Status",
            value=(
                "`/setmemberstatus <player> <status>` - Set status\n"
                "`/showtrials` - View trial members\n"
                "`/showkicked` - View kicked members"
            ),
            inline=False
        )

        embed.add_field(
            name="OCR",
            value=(
                "Upload images to the OCR channel for auto-scanning\n"
                "`/scanimage` - Manually scan last image\n"
                "`/setchannel <channel>` - Set OCR channel"
            ),
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sendcommand", description="[ADMIN ONLY - TEMPORARY] Execute a bot command in a different channel")
    @app_commands.describe(
        command_name="Name of the command to execute (e.g., 'bulkscanimage', 'scanimage', 'addwar', etc.)",
        channel="Target channel where the command will be executed",
        args="[Optional] Command arguments as a string (e.g., 'limit:10' for bulkscanimage)"
    )
    @require_guild_setup
    async def send_command(self, interaction: discord.Interaction, command_name: str, channel: discord.TextChannel, args: str = None):
        """[TEMPORARY ADMIN COMMAND] Execute any bot command in a different channel."""
        if not DatabaseManager.is_bot_owner(interaction.user.id):
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner only.",
                ephemeral=True
            )
            return

        logging.info(f"🔧 [ADMIN] User {interaction.user.name} executing /{command_name} in {channel.name} with args: {args}")

        bot_member = interaction.guild.get_member(self.bot.user.id)
        if not bot_member:
            await interaction.response.send_message("❌ Unable to get bot member information.", ephemeral=True)
            return

        channel_perms = channel.permissions_for(bot_member)
        required_perms = ['view_channel', 'send_messages', 'read_message_history']
        missing_perms = [perm for perm in required_perms if not getattr(channel_perms, perm, False)]

        if missing_perms:
            missing_list = "\n".join([f"• {perm.replace('_', ' ').title()}" for perm in missing_perms])
            await interaction.response.send_message(
                f"❌ **Bot is missing permissions in {channel.mention}:**\n{missing_list}\n\n"
                f"Please grant these permissions to the bot and try again.",
                ephemeral=True
            )
            return

        # Find the command across all cogs
        command_method = None
        target_cog = None
        for cog in self.bot.cogs.values():
            for cmd in cog.walk_app_commands():
                if cmd.name == command_name:
                    command_method = cmd.callback
                    target_cog = cog
                    break
            if command_method:
                break

        if not command_method:
            await interaction.response.send_message(
                f"❌ Command '{command_name}' not found.\n\n"
                f"Use `/help` to see available commands, or check the command name spelling.",
                ephemeral=True
            )
            return

        kwargs = {}
        if args:
            try:
                for arg_pair in args.split():
                    if ':' in arg_pair:
                        key, value = arg_pair.split(':', 1)
                        try:
                            kwargs[key] = int(value)
                        except ValueError:
                            kwargs[key] = value
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Failed to parse arguments: {str(e)}\n\n"
                    f"Expected format: `key:value` separated by spaces\n"
                    f"Example: `limit:10` or `player_scores:Alice:150,Bob:140`",
                    ephemeral=True
                )
                return

        class InteractionProxy:
            """Proxy object that wraps the interaction but overrides the channel."""
            def __init__(self, original_interaction, target_channel):
                self._original = original_interaction
                self.channel = target_channel

            def __getattr__(self, name):
                return getattr(self._original, name)

        proxy_interaction = InteractionProxy(interaction, channel)

        try:
            await command_method(target_cog, proxy_interaction, **kwargs)
            logging.info(f"✅ [ADMIN] Successfully executed /{command_name} in {channel.name}")
        except TypeError as e:
            await interaction.response.send_message(
                f"❌ Invalid arguments for command '{command_name}': {str(e)}\n\n"
                f"Check the command signature and try again.",
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error executing sendcommand: {e}")
            logging.error(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error executing command: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GuildCog(bot))
