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
import traceback
from . import config
# OCR processor initialized in bot.py at startup for instant response

# Member status choices - centralized definition
MEMBER_STATUS_CHOICES = [
    app_commands.Choice(name="Member", value="member"),
    app_commands.Choice(name="Trial", value="trial"),
    app_commands.Choice(name="Ally", value="ally"),
    app_commands.Choice(name="Kicked", value="kicked")
]

def country_code_to_flag(country_code: str) -> str:
    """Convert 2-letter country code to flag emoji."""
    if not country_code or len(country_code) != 2:
        return ""

    # Convert country code to regional indicator symbols
    # A=🇦, B=🇧, etc. (Unicode offset: 127462 - 65 = 127397)
    country_code = country_code.upper()
    flag = ""
    for char in country_code:
        if 'A' <= char <= 'Z':
            flag += chr(127462 + ord(char) - 65)
    return flag


def is_bot_owner(user_id: int) -> bool:
    """Check if user is the bot owner (Christian/Cynical)."""
    BOT_OWNER_ID = 291621912914821120
    return user_id == BOT_OWNER_ID


def has_admin_permission(interaction: discord.Interaction) -> bool:
    """Check if user has admin permission (server admin, server owner, or bot owner)."""
    return (
        interaction.user.guild_permissions.administrator or
        interaction.user.id == interaction.guild.owner_id or
        is_bot_owner(interaction.user.id)
    )


class LeaderboardView(discord.ui.View):
    """Pagination view for player statistics leaderboard."""

    def __init__(self, all_players: list, sortby: str, total_players_count: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.all_players = all_players
        self.sortby = sortby
        self.total_players_count = total_players_count
        self.current_page = 1
        self.players_per_page = 10
        self.total_pages = max(1, (len(all_players) + self.players_per_page - 1) // self.players_per_page)

        # Update button states
        self.update_buttons()

    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        self.first_button.disabled = (self.current_page == 1)
        self.prev_button.disabled = (self.current_page == 1)
        self.next_button.disabled = (self.current_page == self.total_pages)
        self.last_button.disabled = (self.current_page == self.total_pages)

    def create_embed(self) -> discord.Embed:
        """Create embed for current page."""
        # Calculate slice
        start_idx = (self.current_page - 1) * self.players_per_page
        end_idx = min(start_idx + self.players_per_page, len(self.all_players))
        page_players = self.all_players[start_idx:end_idx]

        # Create embed
        embed = discord.Embed(
            title="📊 Player Statistics Leaderboard",
            color=0x00ff00
        )

        # Build numbered leaderboard with flags
        leaderboard_text = []
        for idx, player in enumerate(page_players):
            # Calculate actual rank number across all pages
            rank = start_idx + idx + 1

            # Get flag emoji
            country_code = player.get('country_code', '')
            flag = country_code_to_flag(country_code) if country_code else "❓"

            if player.get('war_count', 0) > 0:
                avg_score = player.get('average_score', 0.0)
                war_count = float(player.get('war_count', 0))
                total_diff = player.get('total_team_differential', 0)
                avg_diff = total_diff / war_count if war_count > 0 else 0
                diff_symbol = "+" if avg_diff >= 0 else ""

                # Numbered format: #. [flag] [name] | [avg] avg | [wars] wars | [diff] diff
                leaderboard_text.append(
                    f"{rank}. {flag} **{player['player_name']}** | {avg_score:.1f} avg | {war_count:.1f} wars | {diff_symbol}{avg_diff:.1f} diff"
                )
            else:
                leaderboard_text.append(f"{rank}. {flag} **{player['player_name']}** | No wars yet")

        embed.add_field(
            name="Top Players",
            value="\n".join(leaderboard_text) if leaderboard_text else "No player data available",
            inline=False
        )

        # Footer with page info and sort method
        if self.sortby and self.sortby.lower() == 'winrate':
            sort_method = "Win Rate"
        elif self.sortby and self.sortby.lower() == 'avgdiff':
            sort_method = "Average Differential"
        else:
            sort_method = "Average Score"

        embed.set_footer(
            text=f"Page {self.current_page}/{self.total_pages} • {self.total_players_count} Members • Sorted by: {sort_method} • Use /setcountry to add your flag"
        )

        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to first page."""
        self.current_page = 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        self.current_page = max(1, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        self.current_page = min(self.total_pages, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to last page."""
        self.current_page = self.total_pages
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class AddPlayerToWarConfirmView(discord.ui.View):
    """Confirmation view for adding players to an existing war."""

    def __init__(self, war_id: int, new_players: list, existing_war: dict, races: int,
                 user: discord.User, commands_cog, guild_id: int):
        super().__init__(timeout=60.0)
        self.war_id = war_id
        self.new_players = new_players
        self.existing_war = existing_war
        self.races = races
        self.user = user
        self.commands_cog = commands_cog
        self.guild_id = guild_id

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle confirm button click."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Only the command user can confirm this action.",
                ephemeral=True
            )
            return

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(view=self)

        # Execute the war update
        import datetime
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')

        success = self.commands_cog.bot.db.append_players_to_war_by_id(
            self.war_id, self.new_players, guild_id=self.guild_id
        )

        if success:
            # Get the updated war to get the new team_differential
            updated_war = self.commands_cog.bot.db.get_war_by_id(self.war_id, self.guild_id)
            team_score = sum(p['score'] for p in updated_war.get('results', []))
            race_count = updated_war.get('race_count', 12)
            total_points = 82 * race_count
            opponent_score = total_points - team_score
            team_differential = team_score - opponent_score

            # Add statistics for new players only
            stats_added = []
            stats_failed = []

            for new_player in self.new_players:
                stats_success = self.commands_cog.bot.db.update_player_stats(
                    new_player['name'],
                    new_player['score'],
                    new_player['races_played'],
                    new_player['war_participation'],
                    current_date,
                    self.guild_id,
                    team_differential
                )
                if stats_success:
                    stats_added.append(new_player['name'])
                else:
                    stats_failed.append(new_player['name'])

            embed = discord.Embed(
                title="✅ Players Added Successfully!",
                description=f"War ID: {self.war_id} has been updated with {len(self.new_players)} new players.",
                color=0x00ff00
            )

            embed.add_field(
                name="Players Added",
                value=f"🏁 {self.races} races\n👥 {len(self.new_players)} new players\n📊 {len(stats_added)} stats updated" + (f", {len(stats_failed)} failed" if stats_failed else ""),
                inline=False
            )

            # Show added players
            player_list = []
            for p in self.new_players:
                if p['races_played'] == self.races:
                    player_list.append(f"**{p['name']}**: {p['score']} points")
                else:
                    player_list.append(f"**{p['name']}** ({p['races_played']}): {p['score']} points")

            embed.add_field(
                name="🏁 New Players Added",
                value="\n".join(player_list[:10]) + (f"\n... +{len(player_list)-10} more" if len(player_list) > 10 else ""),
                inline=False
            )

            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.edit_original_response(
                content="❌ Failed to add players to war. Check logs for details.",
                view=self,
                embed=None
            )

        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button click."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Only the command user can cancel this action.",
                ephemeral=True
            )
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="❌ Player addition cancelled.",
            view=self,
            embed=None
        )

        self.stop()


class RemoveWarConfirmView(discord.ui.View):
    """Confirmation view for removing a war."""

    def __init__(self, war_id: int, war: dict, user: discord.User, commands_cog, guild_id: int):
        super().__init__(timeout=60.0)
        self.war_id = war_id
        self.war = war
        self.user = user
        self.commands_cog = commands_cog
        self.guild_id = guild_id

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle confirm button click."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Only the command user can confirm this action.",
                ephemeral=True
            )
            return

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(view=self)

        # Remove the war and revert player stats
        stats_reverted = self.commands_cog.bot.db.remove_war_by_id(self.war_id, guild_id=self.guild_id)

        if stats_reverted is not None:
            war_date = self.war.get('war_date')
            embed = discord.Embed(
                title="✅ War Removed Successfully!",
                description=f"War ID: {self.war_id} from {war_date} has been removed.",
                color=0x00ff00
            )
            embed.add_field(
                name="Statistics Updated",
                value=f"Reverted stats for {stats_reverted} players",
                inline=False
            )
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.edit_original_response(
                content="❌ Failed to remove war. Check logs for details.",
                view=self,
                embed=None
            )

        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button click."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Only the command user can cancel this action.",
                ephemeral=True
            )
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="❌ War removal cancelled.",
            view=self,
            embed=None
        )

        self.stop()


def get_member_status_text() -> str:
    """Get formatted member status text for help documentation."""
    return "/".join(choice.name for choice in MEMBER_STATUS_CHOICES)

def create_duplicate_war_embed(resolved_results: list, races: int) -> discord.Embed:
    """
    Create an embed showing duplicate war detection with comparison.
    Follows existing embed patterns in the codebase.
    """
    embed = discord.Embed(
        title="⚠️ Duplicate War Detected",
        description="The war you're trying to add appears identical to your most recent war.",
        color=0xffa500  # Orange warning color (same as other warnings)
    )
    
    # Show the war results that would be added (same format as successful war embed)
    player_list = []
    for result in resolved_results:
        if result['races_played'] == races:
            # Full participation - no parentheses
            player_list.append(f"**{result['name']}**: {result['score']} points")
        else:
            # Substitution - show race count
            player_list.append(f"**{result['name']}** ({result['races_played']}): {result['score']} points")
    
    embed.add_field(
        name="🏁 War Results Being Added",
        value="\n".join(player_list),
        inline=False
    )
    
    embed.add_field(
        name="❓ What would you like to do?",
        value="✅ **Accept** - Add this war anyway\n❌ **Cancel** - Don't add this war",
        inline=False
    )
    
    embed.set_footer(text="This confirmation expires in 60 seconds • React with ✅ or ❌")
    
    return embed

# OCR processor is now initialized in bot.py at startup

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


def require_moderator():
    """Decorator to require user to have Manage Channels, Manage Server, or Administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        perms = interaction.user.guild_permissions
        return perms.administrator or perms.manage_guild or perms.manage_channels
    return app_commands.check(predicate)


def require_admin():
    """Decorator to require user to have Manage Server or Administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        perms = interaction.user.guild_permissions
        return perms.administrator or perms.manage_guild
    return app_commands.check(predicate)


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

    def _format_error_for_user(self, error: Exception, context: str = "") -> str:
        """Convert exception to user-friendly message with technical details.

        Args:
            error: The exception that occurred
            context: Optional context about where the error occurred

        Returns:
            Formatted error message for Discord users
        """
        error_type = type(error).__name__
        error_msg = str(error)

        # Truncate very long error messages
        if len(error_msg) > 150:
            error_msg = error_msg[:150] + "..."

        if context:
            return f"❌ {context}: {error_type} - {error_msg}"
        else:
            return f"❌ {error_type}: {error_msg}"

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

            # Check if already initialized
            if self.is_guild_initialized(guild_id):
                await interaction.response.send_message("✅ Guild is already set up! Use other commands to manage your clan.", ephemeral=True)
                return

            # Parse user mentions from the players string
            # Discord mentions come as <@123456789> in the string
            import re
            user_id_pattern = r'<@!?(\d+)>'
            user_ids = re.findall(user_id_pattern, players)

            if not user_ids:
                await interaction.response.send_message(
                    "❌ You must @mention at least one Discord user.\nExample: `/setup teamname:MyTeam players:@User1 @User2 ...`",
                    ephemeral=True
                )
                return

            # Get member objects for each mentioned user
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

            # Validate bot has required permissions in OCR channel
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

            # Auto-detect server name from Discord
            servername = interaction.guild.name if interaction.guild else f"Guild {guild_id}"

            with self.bot.db.get_connection() as conn:
                cursor = conn.cursor()

                # 1. Create guild config with role configuration
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

                # 2. Add all players to players table with Discord user IDs
                added_players = []
                role_detection = []

                for member in player_members:
                    # Detect member_status from Discord roles
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
                        # User doesn't have any of the configured roles - reject
                        await interaction.response.send_message(
                            f"❌ {member.mention} doesn't have a Member, Trial, or Ally role.\n"
                            f"Please assign them one of these roles first: {role_member.mention}, {role_trial.mention}, or {role_ally.mention}",
                            ephemeral=True
                        )
                        return

                    # Use display_name as default player_name (can be changed later if needed)
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

            # 3. Set the OCR channel for automatic image processing
            ocr_success = self.bot.db.set_ocr_channel(guild_id, results_channel.id)
            if not ocr_success:
                logging.warning(f"Failed to set OCR channel during setup for guild {guild_id}")

            # Create success response
            embed = discord.Embed(
                title="🚀 Guild Setup Complete!",
                description=f"Successfully initialized **{servername}** for Mario Kart clan tracking with Discord role integration.",
                color=0x00ff00
            )

            embed.add_field(name="Server Name", value=servername, inline=True)
            embed.add_field(name="Guild ID", value=str(guild_id), inline=True)
            embed.add_field(name="Team Name", value=teamname, inline=True)
            embed.add_field(name="Players Added", value=f"{len(added_players)} players", inline=True)

            # Show role configuration
            embed.add_field(
                name="👥 Role Configuration",
                value=(
                    f"**Member**: {role_member.mention}\n"
                    f"**Trial**: {role_trial.mention}\n"
                    f"**Ally**: {role_ally.mention}"
                ),
                inline=False
            )

            # Show player role detection
            role_detection_text = "\n".join(role_detection)
            if len(role_detection_text) > 1000:  # Discord field limit
                role_detection_text = role_detection_text[:1000] + "..."
            embed.add_field(name="🎭 Players & Roles Detected", value=role_detection_text, inline=False)

            # Show OCR channel configuration
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
    @app_commands.describe(
        player="Player name to view stats for (optional - shows leaderboard if empty)",
        lastxwars="Show stats for last X wars only (optional - shows all-time if empty)",
        sortby="Leaderboard sort method"
    )
    @app_commands.choices(sortby=[
        app_commands.Choice(name="Average Score", value="average"),
        app_commands.Choice(name="Win Rate", value="winrate"),
        app_commands.Choice(name="Average Differential", value="avgdiff")
    ])
    @require_guild_setup
    async def stats_slash(self, interaction: discord.Interaction, player: str = None, lastxwars: int = None, sortby: str = None):
        """View statistics for a specific player or all players."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            if player:
                # Resolve nickname to actual player name first
                resolved_player = self.bot.db.resolve_player_name(player, guild_id)
                if not resolved_player:
                    await interaction.response.send_message(f"❌ No player found with name or nickname: {player}", ephemeral=True)
                    return
                
                # Handle lastxwars parameter validation and stats retrieval
                if lastxwars is not None:
                    # Validate lastxwars parameter
                    if lastxwars < 1:
                        await interaction.response.send_message("❌ Must be at least 1 war.", ephemeral=True)
                        return
                    
                    # Get player's distinct war count for validation
                    distinct_wars = self.bot.db.get_player_distinct_war_count(resolved_player, guild_id)
                    if distinct_wars == 0:
                        await interaction.response.send_message(f"❌ {resolved_player} hasn't participated in any wars yet.", ephemeral=True)
                        return
                    
                    if lastxwars > distinct_wars:
                        await interaction.response.send_message(f"❌ {resolved_player} has only participated in {distinct_wars} wars, can't show last {lastxwars}.", ephemeral=True)
                        return
                    
                    # Get stats for last X wars
                    stats = self.bot.db.get_player_stats_last_x_wars(resolved_player, lastxwars, guild_id)
                else:
                    # Get all-time stats (default behavior)
                    stats = self.bot.db.get_player_stats(resolved_player, guild_id)
                
                if stats:
                    # Modern minimalistic embed design
                    from datetime import datetime

                    # Get flag emoji
                    country_code = stats.get('country_code', '')
                    flag = country_code_to_flag(country_code) if country_code else ""
                    flag_prefix = f"{flag} " if flag else ""

                    # Determine title and color based on context
                    if lastxwars is not None:
                        title_text = f"{flag_prefix}{stats['player_name']} (Last {lastxwars} Wars)"
                        scope_text = f"Last {lastxwars} Wars"
                    else:
                        title_text = f"{flag_prefix}{stats['player_name']}"
                        scope_text = "Career Statistics"

                    # Dynamic color based on team differential
                    total_diff = stats.get('total_team_differential', 0)
                    if total_diff is not None and total_diff > 0:
                        color = 0x00ff88  # Green for positive
                    elif total_diff is not None and total_diff < 0:
                        color = 0xff6b6b  # Red for negative
                    else:
                        color = 0x95a5a6  # Gray for neutral

                    # Build description with player info
                    team_name = stats.get('team', 'Unassigned')
                    description_parts = [f"**{team_name}**"]

                    if stats.get('nicknames'):
                        nicknames_str = ", ".join(stats['nicknames'])
                        description_parts.append(f"*{nicknames_str}*")

                    embed = discord.Embed(
                        title=title_text,
                        description="\n".join(description_parts),
                        color=color
                    )

                    # Performance Overview (highest, average, lowest scores)
                    highest_score = stats.get('highest_score', 0)
                    avg_score = stats.get('average_score', 0.0)
                    lowest_score = stats.get('lowest_score', 0)

                    performance_text = f"```\nHighest:    {highest_score}\nAverage:    {avg_score:.1f}\nLowest:     {lowest_score}\n```"
                    embed.add_field(name="⚔️ Performance", value=performance_text, inline=True)

                    # Team Differential (highlight wins/losses)
                    if total_diff is not None:
                        war_count = float(stats.get('war_count', 0))
                        avg_diff = total_diff / war_count if war_count > 0 else 0

                        # Determine symbols and formatting
                        total_diff_symbol = "+" if total_diff >= 0 else ""
                        avg_diff_symbol = "+" if avg_diff >= 0 else ""

                        if total_diff > 0:
                            diff_emoji = "📈"
                            diff_text = "Winning"
                        elif total_diff < 0:
                            diff_emoji = "📉"
                            diff_text = "Fighting"
                        else:
                            diff_emoji = "⚖️"
                            diff_text = "Balanced"

                        # Get win/loss/tie record and percentage
                        wins = stats.get('wins', 0)
                        losses = stats.get('losses', 0)
                        ties = stats.get('ties', 0)
                        win_pct = stats.get('win_percentage', 0.0)

                        differential_text = f"```\nAvg:   {avg_diff_symbol}{avg_diff:.1f}\n{wins}-{losses}-{ties} ({win_pct:.1f}%)\nTotal: {total_diff_symbol}{total_diff}\n```\n*{diff_text}*"
                        embed.add_field(name=f"{diff_emoji} Differential", value=differential_text, inline=True)

                    # Activity Stats (war count, races, last war)
                    war_count = float(stats.get('war_count', 0))
                    total_races = stats.get('total_races', 0)
                    if stats.get('last_war_date'):
                        try:
                            date_obj = datetime.strptime(stats['last_war_date'], '%Y-%m-%d')
                            last_war = date_obj.strftime('%b %d, %Y')
                        except (ValueError, TypeError) as e:
                            logging.debug(f"Date parsing failed for {stats.get('last_war_date')}: {e}")
                            last_war = stats['last_war_date']
                    else:
                        last_war = "Never"

                    activity_text = f"```\nWars:       {war_count:.1f}\nRaces:      {total_races}\nLast War:   {last_war}\n```"
                    embed.add_field(name="📅 Activity", value=activity_text, inline=True)

                    # Footer
                    embed.set_footer(text=f"Guild-Specific {scope_text}")

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
                roster_stats = self.bot.db.get_all_players_stats(guild_id)

                # Get guild role configuration to check actual Discord roles
                role_config = self.bot.db.get_guild_role_config(guild_id)

                # Filter for Members: check Discord role if linked, otherwise use database status
                member_stats = []
                for player in roster_stats:
                    discord_user_id = player.get('discord_user_id')

                    if discord_user_id:
                        # Player is linked - check actual Discord role
                        member = interaction.guild.get_member(discord_user_id)
                        if not member:
                            # Player left or was kicked - exclude them
                            continue

                        # Check if they have the Member role (if role config exists)
                        if role_config and role_config.get('role_member_id'):
                            member_role_id = role_config['role_member_id']
                            user_role_ids = [role.id for role in member.roles]
                            if member_role_id in user_role_ids:
                                member_stats.append(player)
                            # else: linked but doesn't have Member role - exclude
                        else:
                            # No role config, use database status
                            if player.get('member_status') == 'member':
                                member_stats.append(player)
                    else:
                        # Player not linked - only show if role config is NOT set
                        # When role config exists, unlinked players are excluded entirely
                        if not (role_config and role_config.get('role_member_id')):
                            if player.get('member_status') == 'member':
                                member_stats.append(player)

                if not member_stats:
                    await interaction.response.send_message("❌ No members found with the Member role in Discord.", ephemeral=True)
                    return

                # Get war statistics for members who have them
                players_with_stats = []
                players_without_stats = []

                for roster_player in member_stats:
                    war_stats = self.bot.db.get_player_stats(roster_player['player_name'], guild_id)
                    if war_stats:
                        players_with_stats.append(war_stats)
                    else:
                        players_without_stats.append(roster_player)
                
                # Sort players with stats by sortby parameter (default: average score)
                if sortby and sortby.lower() == 'winrate':
                    players_with_stats.sort(key=lambda x: x.get('win_percentage', 0), reverse=True)
                elif sortby and sortby.lower() == 'avgdiff':
                    # Sort by average differential (total_team_differential / war_count)
                    players_with_stats.sort(
                        key=lambda x: x.get('total_team_differential', 0) / x.get('war_count', 1) if x.get('war_count', 0) > 0 else 0,
                        reverse=True
                    )
                else:
                    players_with_stats.sort(key=lambda x: x.get('average_score', 0), reverse=True)
                
                # Combine and sort all players - those with stats first, then without stats
                all_players = players_with_stats + players_without_stats

                # Use pagination view for leaderboard
                view = LeaderboardView(all_players, sortby, len(all_players))
                embed = view.create_embed()

                await interaction.response.send_message(embed=embed, view=view)
                
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
        user="Discord user to add (@mention)",
        ingame_name="In-game name for OCR matching (optional, defaults to display name)",
        country="2-letter country code (US, CA, GB, JP, etc.) for flag display"
    )
    @require_guild_setup
    async def add_player_to_roster(self, interaction: discord.Interaction, user: discord.Member, ingame_name: str = None, country: str = None):
        """Add a player to the clan roster with Discord user ID."""
        try:
            guild_id = self.get_guild_id(interaction)

            # Get guild role configuration
            role_config = self.bot.db.get_guild_role_config(guild_id)
            if not role_config:
                await interaction.response.send_message(
                    "❌ Guild roles are not configured. Please run `/setup` first to configure Member, Trial, and Ally roles.",
                    ephemeral=True
                )
                return

            # Detect member_status from Discord roles
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
                # User doesn't have any of the configured roles - reject
                await interaction.response.send_message(
                    f"❌ {user.mention} doesn't have a Member, Trial, or Ally role.\n"
                    f"Please assign them one of these roles before adding to the roster.",
                    ephemeral=True
                )
                return

            # Validate and normalize country code
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

            # Use ingame_name if provided, otherwise use display_name
            player_name = ingame_name if ingame_name else user.display_name

            # Add player with Discord user ID
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

            # Get guild role configuration
            role_config = self.bot.db.get_guild_role_config(guild_id)
            if not role_config:
                await interaction.response.send_message(
                    "❌ Guild roles are not configured. Please run `/setup` first.",
                    ephemeral=True
                )
                return

            # Detect member_status from Discord roles
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

            # Link player to Discord user
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

            # Group players by team
            teams = {}
            for player in unlinked_players:
                team = player.get('team', 'Unassigned')
                if team not in teams:
                    teams[team] = []
                teams[team].append(player)

            # Display players by team
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

            # Get guild role configuration
            role_config = self.bot.db.get_guild_role_config(guild_id)
            if not role_config:
                await interaction.response.send_message(
                    "❌ Guild roles are not configured. Please run `/setup` first.",
                    ephemeral=True
                )
                return

            # Get all players with discord_user_id
            all_players = self.bot.db.get_all_players_stats(guild_id)
            linked_players = [p for p in all_players if p.get('discord_user_id')]

            if not linked_players:
                await interaction.response.send_message(
                    "❌ No players are linked to Discord accounts yet.",
                    ephemeral=True
                )
                return

            # Defer response for longer operation
            await interaction.response.defer()

            synced = 0
            changes = []

            for player in linked_players:
                discord_user_id = player.get('discord_user_id')
                current_status = player.get('member_status', 'unknown')

                # Get Discord member
                member = interaction.guild.get_member(discord_user_id)
                if not member:
                    continue

                # Detect new status from roles
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
                    # Sync role and Discord info
                    self.bot.db.sync_player_role(discord_user_id, new_status, guild_id)
                    self.bot.db.sync_player_discord_info(discord_user_id, member.display_name, member.name, guild_id)
                    changes.append(f"• **{player['player_name']}**: {current_status.title()} → {role_name}")
                    synced += 1
                elif new_status:
                    # Just sync Discord info (name changes)
                    self.bot.db.sync_player_discord_info(discord_user_id, member.display_name, member.name, guild_id)
                    synced += 1

            # Create response
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

            # Set the role configuration
            success = self.bot.db.set_guild_role_config(
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

            # Validate country code
            country = country.upper().strip()
            if len(country) != 2 or not country.isalpha():
                await interaction.response.send_message(
                    f"❌ Invalid country code '{country}'. Use 2-letter codes like US, CA, GB, JP.",
                    ephemeral=True
                )
                return

            # Determine target user
            target_user = user if user else interaction.user
            target_member = interaction.guild.get_member(target_user.id)

            if not target_member:
                await interaction.response.send_message("❌ User not found in server.", ephemeral=True)
                return

            # Check permissions - only admins/owner can set for others
            if user and user != interaction.user:
                # Setting for someone else - require admin permission
                if not has_admin_permission(interaction):
                    await interaction.response.send_message(
                        "❌ Only administrators can set country for other players.",
                        ephemeral=True
                    )
                    return

            # Update country code in database
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

            # Get flag emoji
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

            # Parse input: "@Christian:US, Connor:CA, @Cam:GB"
            pairs = [pair.strip() for pair in players_countries.split(',')]

            updated = []
            errors = []

            import re
            # Pattern to match Discord mentions: <@123456> or <@!123456>
            mention_pattern = re.compile(r'<@!?(\d+)>')

            for pair in pairs:
                if ':' not in pair:
                    errors.append(f"❌ Invalid format: `{pair}` (use @User:CC or Player:CC)")
                    continue

                player_identifier, country_code = pair.split(':', 1)
                player_identifier = player_identifier.strip()
                country_code = country_code.strip().upper()

                # Validate country code
                if len(country_code) != 2 or not country_code.isalpha():
                    errors.append(f"❌ Invalid country code: `{country_code}`")
                    continue

                # Check if it's a Discord mention
                mention_match = mention_pattern.search(player_identifier)

                if mention_match:
                    # It's a mention - extract user ID
                    user_id = int(mention_match.group(1))
                    member = interaction.guild.get_member(user_id)

                    if not member:
                        errors.append(f"❌ User not found in server: <@{user_id}>")
                        continue

                    # Update by discord_user_id
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
                    # Plain text player name
                    player_name = player_identifier

                    # Update player country by name
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

            # Build response embed
            embed = discord.Embed(
                title="🌍 Bulk Country Update",
                color=0x00ff00 if updated else 0xff0000
            )

            if updated:
                # Chunk updated players if too many
                if len(updated) <= 25:
                    embed.add_field(
                        name=f"✅ Updated {len(updated)} players",
                        value="\n".join(updated),
                        inline=False
                    )
                else:
                    # Show first 25, then count
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

    @app_commands.command(name="debugroles", description="[DEBUG] Check role filtering for /stats command")
    @require_guild_setup
    async def debug_roles(self, interaction: discord.Interaction):
        """Debug command to check why /stats shows 'No members found'."""
        await interaction.response.defer(ephemeral=True)

        guild_id = self.get_guild_id(interaction)

        # Get role configuration
        role_config = self.bot.db.get_guild_role_config(guild_id)

        debug_lines = []
        debug_lines.append("=== ROLE CONFIGURATION ===")
        if role_config and role_config.get('role_member_id'):
            member_role_id = role_config['role_member_id']

            # Try to get the role from Discord
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

        # Get all roster stats
        roster_stats = self.bot.db.get_all_players_stats(guild_id)

        linked_players = [p for p in roster_stats if p.get('discord_user_id')]
        debug_lines.append(f"Total linked players: {len(linked_players)}\n")

        players_with_role = 0
        players_without_role = 0
        players_not_in_guild = 0

        for player in linked_players:
            discord_user_id = player.get('discord_user_id')
            player_name = player.get('player_name')
            member_status = player.get('member_status', 'member')

            # Try to get the Discord member
            member = interaction.guild.get_member(discord_user_id)

            if not member:
                debug_lines.append(f"❌ {player_name} - NOT IN GUILD (ID: {discord_user_id})")
                players_not_in_guild += 1
                continue

            # Check if they have the role
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

        # Send in chunks if too long
        debug_text = "\n".join(debug_lines)
        if len(debug_text) > 1900:
            chunks = [debug_text[i:i+1900] for i in range(0, len(debug_text), 1900)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)
                else:
                    await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{debug_text}\n```", ephemeral=True)

    async def player_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for player names."""
        try:
            guild_id = self.get_guild_id(interaction)
            all_players = self.bot.db.get_all_players_stats(guild_id)

            # Filter players based on current input
            filtered = [p['player_name'] for p in all_players if current.lower() in p['player_name'].lower()]

            # Return up to 25 choices (Discord limit)
            return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]
        except Exception as e:
            logging.error(f"Error in player autocomplete: {e}")
            return []

    async def team_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for team names."""
        try:
            guild_id = self.get_guild_id(interaction)
            team_names = self.bot.db.get_guild_team_names(guild_id)
            team_names.append('Unassigned')  # Always include Unassigned option

            # Filter teams based on current input
            filtered = [name for name in team_names if current.lower() in name.lower()]

            # Return up to 25 choices (Discord limit)
            return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]
        except Exception as e:
            logging.error(f"Error in team autocomplete: {e}")
            return []

    @app_commands.command(name="assignplayers", description="Assign multiple players to a team")
    @app_commands.describe(players="Space-separated list of player names (minimum 1 player)", team_name="Team to assign players to")
    @app_commands.autocomplete(players=player_autocomplete, team_name=team_autocomplete)
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

    @app_commands.command(name="unassignplayer", description="Unassign a player from their team (set to Unassigned)")
    @app_commands.describe(player_name="Name of the player to unassign from their team")
    @app_commands.autocomplete(player_name=player_autocomplete)
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
            except discord.errors.HTTPException:
                await interaction.followup.send("❌ Error unassigning player from team", ephemeral=True)

    @app_commands.command(name="showallteams", description="Show all players organized by member status")
    @require_guild_setup
    async def show_teams(self, interaction: discord.Interaction):
        """Show all players organized by member status."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Get all active players (excluding kicked)
            all_players = self.bot.db.get_all_players_stats(guild_id)
            
            if not all_players:
                await interaction.response.send_message("❌ No players found in players table. Use `/addplayer` to add players.")
                return
            
            # Filter out kicked players and organize by member status
            status_groups = {}
            for player in all_players:
                status = player.get('member_status', 'member')
                # Skip kicked players
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
            
            # Define status info - only show Member, Trial, Ally
            status_info = {
                'member': {'icon': '👤', 'name': 'Members'},
                'trial': {'icon': '🔍', 'name': 'Trials'},
                'ally': {'icon': '🤝', 'name': 'Allies'}
            }
            
            total_players = 0
            # Display in specific order: Member, Trial, Ally (no Kicked)
            for status in ['member', 'trial', 'ally']:
                if status in status_groups and status_groups[status]:
                    players = status_groups[status]
                    info = status_info[status]
                    
                    player_list = []
                    for player in players:
                        nickname_count = len(player.get('nicknames', []))
                        nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                        player_list.append(f"• **{player['player_name']}**{nickname_text}")
                    
                    embed.add_field(
                        name=f"{info['icon']} {info['name']} ({len(players)} players)",
                        value="\n".join(player_list),
                        inline=True
                    )
                    total_players += len(players)
            
            embed.set_footer(text=f"Total active players: {total_players} | Use /setmemberstatus to change player status")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing player rosters: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving player information", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving player information", ephemeral=True)

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
    @app_commands.choices(member_status=MEMBER_STATUS_CHOICES)
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
    @require_guild_setup
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
            
            # Check for duplicate war before adding to database
            last_war_results = self.bot.db.get_last_war_for_duplicate_check(guild_id)
            is_duplicate = self.bot.db.check_for_duplicate_war(resolved_results, last_war_results)
            
            # Track if we've already responded to the interaction
            already_responded = False
            
            if is_duplicate:
                # Show duplicate warning embed with reactions
                duplicate_embed = create_duplicate_war_embed(resolved_results, races)
                
                await interaction.response.send_message(embed=duplicate_embed)
                confirmation_msg = await interaction.original_response()
                already_responded = True  # Mark that we've responded
                
                # Add reaction buttons
                await confirmation_msg.add_reaction("✅")
                await confirmation_msg.add_reaction("❌")
                
                # Wait for user reaction with timeout
                def check(reaction, user):
                    return (user == interaction.user and 
                           str(reaction.emoji) in ["✅", "❌"] and 
                           reaction.message.id == confirmation_msg.id)
                
                try:
                    reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                    
                    if str(reaction.emoji) == "❌":
                        # User canceled
                        cancel_embed = discord.Embed(
                            title="❌ War Canceled",
                            description="Duplicate war was not added to the database.",
                            color=0xff4444
                        )
                        await interaction.edit_original_response(embed=cancel_embed)
                        return
                    # If ✅, continue with adding the war (fall through to next section)
                    
                except asyncio.TimeoutError:
                    # Timeout - cancel the war
                    timeout_embed = discord.Embed(
                        title="⏰ Confirmation Timeout",
                        description="Duplicate war confirmation timed out. War was not added.",
                        color=0xff4444
                    )
                    await interaction.edit_original_response(embed=timeout_embed)
                    return

            # Store war in database
            war_id = self.bot.db.add_race_results(resolved_results, races, guild_id=guild_id)
            
            if war_id is None:
                await interaction.response.send_message("❌ Failed to add war to database. Check logs for details.", ephemeral=True)
                return
            
            # Update player statistics
            import datetime
            current_date = datetime.datetime.now().strftime('%Y-%m-%d')

            # Calculate team differential for player stats
            team_score = sum(r['score'] for r in resolved_results)
            total_points = 82 * races
            opponent_score = total_points - team_score
            team_differential = team_score - opponent_score

            stats_updated = []
            stats_failed = []

            for result in resolved_results:
                success = self.bot.db.update_player_stats(
                    result['name'],
                    result['score'],
                    result['races_played'],
                    result['war_participation'],
                    current_date,
                    guild_id,
                    team_differential
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
            
            # Send response using appropriate method based on whether we've already responded
            if already_responded:
                await interaction.edit_original_response(embed=embed, content="")
            else:
                await interaction.response.send_message(embed=embed)
            
            # Start countdown and delete (using reusable helper)
            asyncio.create_task(self.bot._countdown_and_delete_interaction(interaction, embed))
            
        except Exception as e:
            logging.error(f"Error adding war: {e}")
            # Try to send error message, but handle if interaction already responded
            try:
                await interaction.response.send_message("❌ Error adding war. Check the command format and try again.", ephemeral=True)
            except discord.errors.InteractionResponded:
                await interaction.followup.send("❌ Error adding war. Check the command format and try again.", ephemeral=True)

    @app_commands.command(name="wars", description="Show recent wars")
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
                await interaction.response.send_message("❌ No wars found.", ephemeral=True)
                return

            embed = discord.Embed(
                title="War History",
                color=0x2b2d31
            )

            for war in wars:
                war_id = war.get('id')
                war_date = war.get('war_date')
                race_count = war.get('race_count', 12)
                players_data = war.get('results', [])

                # Create player list - show race count only if not default (12)
                if players_data:
                    player_entries = []
                    for p in players_data:
                        name = p.get('name', 'Unknown')
                        score = p.get('score', 0)
                        races = p.get('races_played', race_count)
                        if races != race_count:
                            player_entries.append(f"{name} ({races}): {score}")
                        else:
                            player_entries.append(f"{name}: {score}")

                    player_list = ", ".join(player_entries)

                    # Truncate if too long
                    if len(player_list) > 900:
                        truncated = player_list[:850]
                        last_comma = truncated.rfind(', ')
                        if last_comma > 0:
                            player_list = truncated[:last_comma] + "..."
                        else:
                            player_list = truncated + "..."
                else:
                    player_list = "No players"

                embed.add_field(
                    name=f"#{war_id}  ·  {war_date}",
                    value=player_list,
                    inline=False
                )

            embed.set_footer(text=f"Showing {len(wars)} wars")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Error showing all wars: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error retrieving wars", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error retrieving wars", ephemeral=True)

    @app_commands.command(name="addplayertowar", description="Add new players to an existing war")
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
            
            embed.set_footer(text="Click ✅ Confirm or ❌ Cancel")

            # Create confirmation view with buttons (no permissions required)
            view = AddPlayerToWarConfirmView(war_id, new_players, existing_war, races, interaction.user, self, guild_id)
            await interaction.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            logging.error(f"Error appending players to war: {e}", exc_info=True)
            error_message = self._format_error_for_user(e, "Failed to add players to war")
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)

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
            
            embed.set_footer(text="Click ✅ Confirm or ❌ Cancel")

            # Create confirmation view with buttons (no permissions required)
            view = RemoveWarConfirmView(war_id, war, interaction.user, self, guild_id)
            await interaction.response.send_message(embed=embed, view=view)
                
        except Exception as e:
            logging.error(f"Error removing war: {e}", exc_info=True)
            error_message = self._format_error_for_user(e, "Failed to remove war")
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)

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
                except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to clear reactions: {e}")
                    
            except asyncio.TimeoutError:
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

    async def _add_ocr_confirmation(self, message, processed_results, guild_id: int, user_id: int, original_message):
        """Add confirmation reactions to OCR results for database submission."""
        try:
            # Add reaction buttons (embed is already set by runocr command)
            await message.add_reaction("✅")  
            await message.add_reaction("❌")
            
            # Store pending confirmation data (using the pattern from bot.py)
            if not hasattr(self.bot, 'pending_confirmations'):
                self.bot.pending_confirmations = {}
                
            confirmation_data = {
                'type': 'ocr_war_submission',
                'results': processed_results,
                'guild_id': guild_id,
                'user_id': user_id,
                'channel_id': message.channel.id,
                'original_message_obj': original_message
            }
            
            self.bot.pending_confirmations[str(message.id)] = confirmation_data

            # Start timeout task in background and track it
            timeout_task = asyncio.create_task(self._handle_ocr_confirmation_timeout(message.id, 60))
            self.bot.timeout_tasks[str(message.id)] = timeout_task
            
        except Exception as e:
            logging.error(f"Error adding OCR confirmation: {e}")

    async def _handle_ocr_confirmation_timeout(self, message_id: int, timeout_seconds: int):
        """Handle timeout for OCR confirmation."""
        try:
            await asyncio.sleep(timeout_seconds)

            # Check if still pending
            message_id_str = str(message_id)
            if message_id_str in self.bot.pending_confirmations:
                confirmation_data = self.bot.pending_confirmations[message_id_str]
                channel_id = confirmation_data.get('channel_id')

                # Clean up the confirmation
                self.bot.cleanup_confirmation(message_id_str)

                try:
                    # Get the message and update it to show expired
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)
                        expired_embed = discord.Embed(
                            title="⏰ Confirmation Expired",
                            description="The confirmation period has expired. Results were not saved.",
                            color=0x808080
                        )
                        await message.edit(embed=expired_embed)
                        await message.clear_reactions()
                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to update expired confirmation: {e}")
        except asyncio.CancelledError:
            # Task was cancelled (confirmation was handled), that's fine
            pass

    @app_commands.command(name="scanimage", description="Manually scan the most recent image in this channel (backup for when automatic OCR misses)")
    @require_guild_setup
    async def scanimage(self, interaction: discord.Interaction):
        """Manually scan the most recent image uploaded to the channel."""
        await interaction.response.defer(thinking=True)
        
        try:
            guild_id = self.get_guild_id(interaction)
            logging.info(f"🔍 Starting manual image scan for user {interaction.user.name}")
            
            # Check if an OCR channel is configured for this guild
            configured_channel_id = self.bot.db.get_ocr_channel(guild_id)
            if not configured_channel_id:
                embed = discord.Embed(
                    title="❌ No OCR Channel Set",
                    description="You need to configure an OCR channel before using image scanning.",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Setup Required",
                    value="Use `/setchannel #your-channel` to enable automatic and manual OCR processing.",
                    inline=False
                )
                embed.add_field(
                    name="📖 How it works",
                    value="• Set a channel with `/setchannel`\n• Upload images there for automatic scanning\n• Use `/scanimage` in that channel as backup",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check if current channel is the configured OCR channel
            if interaction.channel.id != configured_channel_id:
                configured_channel = self.bot.get_channel(configured_channel_id)
                channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"
                
                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Image scanning is only available in {channel_mention}",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Options",
                    value=f"• Use `/scanimage` in {channel_mention}\n• Change OCR channel with `/setchannel #new-channel`",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Search for the most recent image in the channel
            recent_image = None
            original_message = None
            async for message in interaction.channel.history(limit=50):
                for attachment in message.attachments:
                    if attachment.filename.lower().endswith('.png'):
                        recent_image = attachment
                        original_message = message  # Store the original message
                        logging.info(f"✅ Found image: {attachment.filename}")
                        break
                if recent_image:
                    break
            
            if not recent_image:
                await interaction.followup.send("❌ No recent images found in this channel (checked last 50 messages). Try uploading an image with the command!")
                return
            
            # Download image
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(recent_image.url) as response:
                        if response.status != 200:
                            await interaction.followup.send(f"❌ Failed to download image: HTTP {response.status}")
                            return
                        
                        # Create temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                            temp_path = temp_file.name
                            image_data = await response.read()
                            temp_file.write(image_data)
                            logging.info(f"✅ Image downloaded to: {temp_path}")
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to download image: {str(e)}")
                return
            
            try:
                # Use shared OCR processing logic
                guild_id = self.get_guild_id_from_interaction(interaction)

                success, embed, processed_results = await self.bot.process_ocr_image(
                    temp_path, guild_id, recent_image.filename, original_message
                )

                if not success:
                    # Show error embed briefly then remove it (like addwar does)
                    error_msg = await interaction.followup.send(embed=embed)
                    # Auto-delete the embed after 5 seconds to keep channel clean
                    asyncio.create_task(self.bot._countdown_and_delete_message(error_msg, embed, 5))
                    return

                # Success - create interactive view for confirmation (same as channel-based OCR)
                from mkw_stats.bot import OCRConfirmationView

                view = OCRConfirmationView(
                    results=processed_results,
                    guild_id=guild_id,
                    user_id=interaction.user.id,
                    original_message_obj=original_message,
                    bot=self.bot
                )

                # Create modern embed
                embed = view.create_embed()

                # Send message with view
                response_msg = await interaction.followup.send(embed=embed, view=view)

                # Store message reference in view for timeout handling
                view.message = response_msg

            finally:
                # Clean up temporary files
                try:
                    os.unlink(temp_path)
                except OSError as e:
                    logging.debug(f"Failed to delete temporary file: {e}")
                    
        except Exception as e:
            logging.error(f"Error in scanimage command: {e}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")

    @app_commands.command(name="bulkscanimage", description="Scan all images in this channel and create individual war entries")
    @app_commands.describe(limit="Maximum number of images to process (default: all images)")
    @require_guild_setup
    async def bulkscanimage(self, interaction: discord.Interaction, limit: int = None):
        """Bulk scan all images in the channel and process them sequentially."""
        await interaction.response.defer(thinking=True)
        
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)
            logging.info(f"🔍 Starting bulk image scan for user {interaction.user.name} with limit: {limit}")
            
            # Check if an OCR channel is configured for this guild
            configured_channel_id = self.bot.db.get_ocr_channel(guild_id)
            if not configured_channel_id:
                embed = discord.Embed(
                    title="❌ No OCR Channel Set",
                    description="You need to configure an OCR channel before using bulk image scanning.",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Setup Required",
                    value="Use `/setchannel #your-channel` to enable bulk OCR processing.",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check if current channel is the configured OCR channel
            if interaction.channel.id != configured_channel_id:
                configured_channel = self.bot.get_channel(configured_channel_id)
                channel_mention = configured_channel.mention if configured_channel else f"<#{configured_channel_id}>"
                
                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Bulk image scanning is only available in {channel_mention}",
                    color=0xff4444
                )
                embed.add_field(
                    name="🔧 Options",
                    value=f"• Use `/bulkscanimage` in {channel_mention}\n• Change OCR channel with `/setchannel #new-channel`",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Search for images in the channel
            images_found = []
            oldest_image_msg = None
            newest_image_msg = None
            
            # Determine search limit
            search_limit = None if limit is None else limit * 10  # Search more messages to find enough images
            
            async for message in interaction.channel.history(limit=search_limit):
                for attachment in message.attachments:
                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        if newest_image_msg is None:
                            newest_image_msg = message  # First found = newest
                        oldest_image_msg = message  # Keep updating = oldest
                        
                        images_found.append({
                            'message': message,
                            'attachment': attachment
                        })
                        
                        # Stop if we've reached the limit
                        if limit and len(images_found) >= limit:
                            break
                
                # Break outer loop too if limit reached
                if limit and len(images_found) >= limit:
                    break
            
            # Reverse the list so we process oldest images first (chronological order)
            images_found.reverse()
            
            if not images_found:
                await interaction.followup.send("❌ No images found in this channel (searched recent messages). Try uploading images first!")
                return
            
            # Create confirmation embed with date range
            embed = discord.Embed(
                title="🔍 Bulk Image Scan Ready",
                description=f"Found {len(images_found)} image{'s' if len(images_found) != 1 else ''} to process" + 
                           (f" (limited from channel total)" if limit and len(images_found) == limit else ""),
                color=0x00ff00
            )
            
            # Format date range
            if oldest_image_msg and newest_image_msg:
                oldest_time = discord.utils.format_dt(oldest_image_msg.created_at, style='f')
                newest_time = discord.utils.format_dt(newest_image_msg.created_at, style='f')
                
                embed.add_field(
                    name="📅 Date Range",
                    value=f"• **Oldest**: {oldest_time}\n• **Newest**: {newest_time}",
                    inline=False
                )
            
            # Time estimation
            estimated_minutes = max(1, (len(images_found) * 5) // 60)  # ~5 seconds per image
            if estimated_minutes == 1:
                time_str = f"~{len(images_found) * 5} seconds"
            else:
                time_str = f"~{estimated_minutes} minute{'s' if estimated_minutes > 1 else ''}"
            
            embed.add_field(
                name="⏱️ Estimated Time",
                value=time_str,
                inline=True
            )
            
            embed.add_field(
                name="❓ Confirmation",
                value=f"✅ Process {len(images_found)} image{'s' if len(images_found) != 1 else ''} | ❌ Cancel",
                inline=False
            )
            
            embed.set_footer(text="Each image will create a separate war entry • React below to confirm or cancel")
            
            # Send confirmation and add reactions
            confirmation_msg = await interaction.followup.send(embed=embed)
            await confirmation_msg.add_reaction("✅")
            await confirmation_msg.add_reaction("❌")
            
            # Store bulk scan data for confirmation handling
            bulk_scan_data = {
                'type': 'bulk_scan_confirmation',
                'images_found': images_found,
                'guild_id': guild_id,
                'user_id': interaction.user.id,
                'channel_id': interaction.channel.id,
                'limit': limit
            }
            
            self.bot.pending_confirmations[str(confirmation_msg.id)] = bulk_scan_data
            
            # No auto-expire - let user decide when to confirm/cancel
            
        except Exception as e:
            logging.error(f"Error in bulkscanimage command: {e}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")

    async def _countdown_and_delete_confirmation(self, message: discord.Message, embed: discord.Embed, countdown_seconds: int = 60):
        """Countdown and delete confirmation message for bulk scan."""
        for remaining in range(countdown_seconds, 0, -1):
            await asyncio.sleep(1)
            if remaining <= 5:  # Only show countdown for last 5 seconds
                try:
                    embed_copy = embed.copy()
                    embed_copy.set_footer(text=f"This confirmation expires in {remaining} seconds")
                    await message.edit(embed=embed_copy)
                except (discord.errors.NotFound, discord.errors.HTTPException) as e:
                    logging.debug(f"Failed to update countdown: {e}")
        
        # Clean up and delete
        try:
            message_id = str(message.id)
            if message_id in self.bot.pending_confirmations:
                del self.bot.pending_confirmations[message_id]
            await message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException) as e:
            logging.debug(f"Failed to delete message: {e}")

    @app_commands.command(name="checkpermissions", description="Check bot permissions in a channel for OCR functionality")
    @app_commands.describe(channel="Channel to check permissions for (defaults to current channel)")
    async def check_permissions(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Check bot permissions in the specified channel for OCR functionality."""
        try:
            # Use specified channel or default to current channel
            target_channel = channel if channel else interaction.channel
            
            # Get bot member in this guild
            bot_member = interaction.guild.get_member(self.bot.user.id)
            if not bot_member:
                await interaction.response.send_message("❌ Unable to get bot member information.", ephemeral=True)
                return
            
            # Get channel permissions for the bot
            channel_perms = target_channel.permissions_for(bot_member)
            
            # Required permissions for OCR functionality
            required_perms = {
                'view_channel': channel_perms.view_channel,
                'send_messages': channel_perms.send_messages,
                'read_message_history': channel_perms.read_message_history,
                'add_reactions': channel_perms.add_reactions,
                'use_application_commands': channel_perms.use_application_commands
            }
            
            # Create embed showing permission status
            embed = discord.Embed(
                title="🔐 Bot Permissions Check",
                description=f"Checking permissions in #{target_channel.name}",
                color=0x00ff00 if all(required_perms.values()) else 0xff4444
            )
            
            # Show each required permission
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
            
            # Overall status
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

    @app_commands.command(name="setchannel", description="Set the channel for automatic OCR processing of uploaded images")
    @app_commands.describe(channel="Channel where images will be automatically scanned for Mario Kart results")
    @require_guild_setup
    async def set_ocr_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for automatic OCR processing."""
        try:
            guild_id = self.get_guild_id(interaction)
            
            # Get bot member to check permissions
            bot_member = interaction.guild.get_member(self.bot.user.id)
            if not bot_member:
                await interaction.response.send_message("❌ Unable to get bot member information.", ephemeral=True)
                return
            
            # Check permissions in the target channel
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
            
            # Update the database with the OCR channel
            success = self.bot.db.set_ocr_channel(guild_id, channel.id)
            
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

    @app_commands.command(name="debugocr", description="Debug OCR results (admin only)")
    @app_commands.describe(
        image_url="URL of the image to debug with OCR"
    )
    async def debug_ocr(self, interaction: discord.Interaction, image_url: str):
        """Debug OCR processing pipeline with detailed stage output (admin server only)."""
        # Check if command is being used in admin server
        if config.ADMIN_SERVER_ID and interaction.guild_id != config.ADMIN_SERVER_ID:
            await interaction.response.send_message(
                "❌ This command is only available in the admin server.",
                ephemeral=True
            )
            return

        # Check if user is admin
        if config.ADMIN_USER_ID and interaction.user.id != config.ADMIN_USER_ID:
            await interaction.response.send_message(
                "❌ This command is restricted to the admin user.",
                ephemeral=True
            )
            return

        # Check if admin settings are configured
        if not config.ADMIN_USER_ID or not config.ADMIN_SERVER_ID:
            await interaction.response.send_message(
                "❌ Admin settings are not configured. Please set ADMIN_USER_ID and ADMIN_SERVER_ID.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            import tempfile
            import aiohttp

            # Download the image
            temp_file_path = None
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        if response.status != 200:
                            await interaction.followup.send(
                                f"❌ Failed to download image. HTTP {response.status}",
                                ephemeral=True
                            )
                            return

                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                            tmp.write(await response.read())
                            temp_file_path = tmp.name

                # Get OCR processor
                ocr_processor = self.bot.ocr_processor

                # Stage 1: Image Loading and Preprocessing
                debug_embed = discord.Embed(
                    title="🔍 OCR Debug Pipeline",
                    description="Running through all 6 debug stages...",
                    color=0x0099ff
                )

                import cv2

                # Load image
                image = cv2.imread(temp_file_path)
                if image is None:
                    await interaction.followup.send("❌ Failed to load image.", ephemeral=True)
                    return

                original_shape = image.shape
                debug_embed.add_field(
                    name="📷 Stage 1: Image Loading",
                    value=f"✅ Loaded successfully\n**Dimensions**: {original_shape[1]}x{original_shape[0]} pixels\n**Color Channels**: {original_shape[2]} (BGR)",
                    inline=False
                )

                # Stage 2: Preprocessing
                preprocessed = ocr_processor._preprocess_image_for_ocr(image.copy())
                debug_embed.add_field(
                    name="🔧 Stage 2: Preprocessing",
                    value=f"✅ Preprocessing applied\n**Techniques**: Grayscale conversion, contrast enhancement, denoising\n**Output Shape**: {preprocessed.shape}",
                    inline=False
                )

                # Stage 3: Text Detection (PaddleOCR)
                results = ocr_processor.ocr_reader.readtext(preprocessed, batch_size=1)
                if results:
                    detected_count = len(results)
                    detected_text = "\n".join([f"• {item[1]}" for item in results[:10]])  # Show first 10
                    if len(results) > 10:
                        detected_text += f"\n• ... and {len(results) - 10} more"
                else:
                    detected_text = "No text detected"
                    detected_count = 0

                debug_embed.add_field(
                    name="📝 Stage 3: Text Detection",
                    value=f"✅ PaddleOCR completed\n**Text blocks detected**: {detected_count}\n**First results**:\n{detected_text[:500]}",
                    inline=False
                )

                # Stage 4: Text Parsing
                parsed_text = "\n".join([item[1] for item in results if item[1].strip()])
                lines = parsed_text.split("\n")
                debug_embed.add_field(
                    name="🔤 Stage 4: Text Parsing",
                    value=f"✅ Text extracted\n**Lines found**: {len(lines)}\n**Sample**: {lines[:3] if lines else 'No text'}",
                    inline=False
                )

                # Stage 5: Name/Score Matching
                guild_id = interaction.guild_id
                matched_results = []
                unmatched_names = []

                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        potential_name = " ".join(parts[:-1])
                        potential_score = parts[-1]

                        try:
                            score = int(potential_score)
                            # Check if score is valid (1-180)
                            if 1 <= score <= 180:
                                # Try to match against roster
                                from difflib import get_close_matches
                                roster = self.bot.db.get_roster(guild_id)
                                roster_names = [p['name'] for p in roster]
                                matches = get_close_matches(potential_name, roster_names, n=1, cutoff=0.6)

                                if matches:
                                    matched_results.append({
                                        'detected': potential_name,
                                        'matched': matches[0],
                                        'score': score
                                    })
                                else:
                                    unmatched_names.append(f"{potential_name} ({score}pts)")
                        except ValueError:
                            unmatched_names.append(f"{potential_name} {potential_score}")

                matched_text = "\n".join([f"• {m['detected']} → **{m['matched']}** ({m['score']})" for m in matched_results[:5]])
                if len(matched_results) > 5:
                    matched_text += f"\n• ... and {len(matched_results) - 5} more"

                unmatched_text = "\n".join([f"• {u}" for u in unmatched_names[:5]])
                if len(unmatched_names) > 5:
                    unmatched_text += f"\n• ... and {len(unmatched_names) - 5} more"

                stage5_value = f"✅ Name matching completed\n**Matched**: {len(matched_results)}\n{matched_text if matched_text else 'No matches'}"
                if unmatched_names:
                    stage5_value += f"\n\n**Unmatched**: {len(unmatched_names)}\n{unmatched_text}"

                debug_embed.add_field(
                    name="🎯 Stage 5: Name/Score Matching",
                    value=stage5_value[:1024],
                    inline=False
                )

                # Stage 6: Team Detection
                team_count = 0
                if matched_results:
                    teams_detected = set()
                    for result in matched_results:
                        player = next((p for p in roster if p['name'] == result['matched']), None)
                        if player and player.get('team'):
                            teams_detected.add(player['team'])
                    team_count = len(teams_detected)

                debug_embed.add_field(
                    name="👥 Stage 6: Team Detection",
                    value=f"✅ Team analysis completed\n**Teams detected**: {team_count}\n**Total valid players**: {len(matched_results)}\n**Ready to save**: {'✅ Yes' if len(matched_results) >= 2 else '❌ Need at least 2 players'}",
                    inline=False
                )

                debug_embed.set_footer(text=f"Debug completed • {len(matched_results)} valid results found")
                await interaction.followup.send(embed=debug_embed, ephemeral=True)

            finally:
                # Clean up temp file
                if temp_file_path and os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

        except Exception as e:
            logging.error(f"Error in debug OCR: {e}")
            embed = discord.Embed(
                title="❌ Debug Error",
                description=f"An error occurred during OCR debugging:\n```\n{str(e)}\n```",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(MarioKartCommands(bot)) 