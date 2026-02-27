"""Player statistics and leaderboard commands."""

import logging
from typing import List, Dict, Any, Optional
import discord
from discord.ext import commands
from discord import app_commands

from .base_cog import BaseCog, require_guild_setup
from ..constants import (
    SORT_DISPLAY_NAMES,
    SORT_DESCRIPTIONS,
    GLOBAL_SORT_TITLES,
)
from ..utils.formatters import country_code_to_flag, get_player_display_name


class LeaderboardView(discord.ui.View):
    """Pagination view for player statistics leaderboard."""

    def __init__(self, all_players: list, sortby: str, total_players_count: int, bot, guild_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.all_players = all_players
        self.sortby = sortby
        self.total_players_count = total_players_count
        self.bot = bot
        self.guild_id = guild_id
        self.current_page = 1
        self.players_per_page = 10
        self.total_pages = max(1, (len(all_players) + self.players_per_page - 1) // self.players_per_page)

        # Cache team tags to reduce DB calls during pagination
        self.team_tags = self.bot.db.guilds.get_all_team_tags(guild_id)

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

        # Dynamic title based on sort
        if self.sortby:
            title = f"📊 Player Statistics • Sorted by {SORT_DISPLAY_NAMES.get(self.sortby, 'Average 10')}"
        else:
            title = "📊 Player Statistics Leaderboard"

        # Get description for current sort
        description = SORT_DESCRIPTIONS.get(self.sortby) if self.sortby else 'Default ranking by average score'

        # Create embed
        embed = discord.Embed(
            title=title,
            description=f"*{description}*",
            color=0x00ff00
        )

        # Build numbered leaderboard with flags
        # Determine what to show in third column based on sort
        show_third_column = self.sortby in ['avg10', 'avgdiff', 'clutch', 'cv', 'form', 'highest', 'hotstreak', 'lastwar', 'lowest', 'potential', 'totaldiff', 'winrate']

        leaderboard_text = []
        for idx, player in enumerate(page_players):
            # Calculate actual rank number across all pages
            rank = start_idx + idx + 1

            # Get flag emoji
            country_code = player.get('country_code', '')
            flag = country_code_to_flag(country_code) if country_code else "❓"

            # Get player display name (no team tags in guild context - they're implied)
            display_name = player['player_name']

            if player.get('war_count', 0) > 0:
                avg_score = player.get('average_score', 0.0)
                war_count = float(player.get('war_count', 0))

                # Bold the column being sorted by
                # Default (None) sorts by avg, "warcount" sorts by wars
                if self.sortby is None:
                    # Bold average score
                    player_str = f"{rank}. {flag} **{display_name}** | **{avg_score:.1f}** avg | {war_count:.1f} wars"
                elif self.sortby == 'warcount':
                    # Bold war count
                    player_str = f"{rank}. {flag} **{display_name}** | {avg_score:.1f} avg | **{war_count:.1f}** wars"
                else:
                    # For other sorts (winrate, avgdiff, cv), don't bold base columns
                    player_str = f"{rank}. {flag} **{display_name}** | {avg_score:.1f} avg | {war_count:.1f} wars"

                # Add third column based on sort type (and bold it)
                if show_third_column:
                    if self.sortby == 'avg10':
                        avg10 = player.get('avg10_score')
                        if avg10 is not None:
                            player_str += f" | **{avg10:.1f}** avg10"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'avgdiff':
                        total_diff = player.get('total_team_differential', 0)
                        avg_diff = total_diff / war_count if war_count > 0 else 0
                        diff_symbol = "+" if avg_diff >= 0 else ""
                        player_str += f" | **{diff_symbol}{avg_diff:.1f}** avg diff"
                    elif self.sortby == 'clutch':
                        clutch = player.get('clutch_factor')
                        if clutch is not None:
                            clutch_symbol = "+" if clutch >= 0 else ""
                            category = self.bot.db.stats.get_clutch_category(clutch)
                            player_str += f" | **{clutch_symbol}{clutch:.2f}** ({category})"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'cv':
                        consistency = player.get('consistency_score')
                        if consistency is not None:
                            player_str += f" | **{consistency:.1f}%**"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'form':
                        form = player.get('form_score')
                        if form is not None and form > 0:
                            player_str += f" | **{form:.1f}** form"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'highest':
                        highest = player.get('highest_score', 0)
                        player_str += f" | **{highest}** highest"
                    elif self.sortby == 'hotstreak':
                        htsk = player.get('hotstreak')
                        if htsk is not None:
                            htsk_symbol = "+" if htsk >= 0 else ""
                            player_str += f" | **{htsk_symbol}{htsk:.2f}** htsk"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'lastwar':
                        last_war = player.get('last_war_date')
                        if last_war:
                            player_str += f" | **{last_war}**"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'lowest':
                        lowest = player.get('lowest_score', 0)
                        player_str += f" | **{lowest}** lowest"
                    elif self.sortby == 'potential':
                        potential = player.get('potential')
                        if potential is not None:
                            player_str += f" | **{potential:.1f}** pot"
                        else:
                            player_str += " | **N/A**"
                    elif self.sortby == 'totaldiff':
                        total_diff = player.get('total_team_differential', 0)
                        diff_symbol = "+" if total_diff >= 0 else ""
                        player_str += f" | **{diff_symbol}{total_diff}** total diff"
                    elif self.sortby == 'winrate':
                        win_pct = player.get('win_percentage', 0.0)
                        player_str += f" | **{win_pct:.1f}%**"

                leaderboard_text.append(player_str)
            else:
                leaderboard_text.append(f"{rank}. {flag} **{display_name}** | No wars yet")

        embed.add_field(
            name="Top Players",
            value="\n".join(leaderboard_text) if leaderboard_text else "No player data available",
            inline=False
        )

        # Footer with page info
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} • {self.total_players_count} Members")

        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to first page."""
        self.current_page = 1
        # Create new view instance to refresh timeout
        new_view = LeaderboardView(
            self.all_players, self.sortby, self.total_players_count, self.bot, self.guild_id
        )
        new_view.current_page = self.current_page
        new_view.update_buttons()
        await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        self.current_page = max(1, self.current_page - 1)
        # Create new view instance to refresh timeout
        new_view = LeaderboardView(
            self.all_players, self.sortby, self.total_players_count, self.bot, self.guild_id
        )
        new_view.current_page = self.current_page
        new_view.update_buttons()
        await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        self.current_page = min(self.total_pages, self.current_page + 1)
        # Create new view instance to refresh timeout
        new_view = LeaderboardView(
            self.all_players, self.sortby, self.total_players_count, self.bot, self.guild_id
        )
        new_view.current_page = self.current_page
        new_view.update_buttons()
        await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to last page."""
        self.current_page = self.total_pages
        # Create new view instance to refresh timeout
        new_view = LeaderboardView(
            self.all_players, self.sortby, self.total_players_count, self.bot, self.guild_id
        )
        new_view.current_page = self.current_page
        new_view.update_buttons()
        await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)


class GlobalLeaderboardView(discord.ui.View):
    """Paginated view for global cross-guild leaderboard."""

    def __init__(self, all_players: list, sortby: str, total_players_count: int, bot):
        super().__init__(timeout=300)  # 5 minute timeout
        self.all_players = all_players
        self.sortby = sortby
        self.total_players_count = total_players_count
        self.bot = bot
        self.current_page = 1
        self.players_per_page = 10
        self.total_pages = max(1, (len(all_players) + self.players_per_page - 1) // self.players_per_page)

        # Cache team tags for all guilds
        self.all_team_tags = {}  # {guild_id: {team_name: tag}}
        self._populate_team_tags()

        # Update button states
        self.update_buttons()

    def _populate_team_tags(self):
        """Populate team tags for all guilds represented in the leaderboard."""
        # Get unique guild_ids from all_players
        guild_ids = set(player.get('guild_id') for player in self.all_players if player.get('guild_id'))

        # Fetch team tags for each guild
        for guild_id in guild_ids:
            self.all_team_tags[guild_id] = self.bot.db.guilds.get_all_team_tags(guild_id)

    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        self.first_button.disabled = (self.current_page == 1)
        self.prev_button.disabled = (self.current_page == 1)
        self.next_button.disabled = (self.current_page == self.total_pages)
        self.last_button.disabled = (self.current_page == self.total_pages)

    def create_embed(self) -> discord.Embed:
        """Create embed for current page."""
        start_idx = (self.current_page - 1) * self.players_per_page
        end_idx = min(start_idx + self.players_per_page, len(self.all_players))
        page_players = self.all_players[start_idx:end_idx]

        # Title based on sortby
        sort_label = GLOBAL_SORT_TITLES.get(self.sortby, "")
        title = f"🌍 Global Leaderboard - {sort_label}" if sort_label else "🌍 Global Leaderboard"

        # Build numbered leaderboard
        leaderboard_text = []
        for idx, player in enumerate(page_players):
            rank = start_idx + idx + 1

            # Get flag emoji
            country_code = player.get('country_code', '')
            flag = country_code_to_flag(country_code) if country_code else "❓"

            # Get team tag for the player's guild (italicized before name)
            guild_id = player.get('guild_id', 0)
            team_name = player.get('team', 'Unassigned')
            team_tag = ""
            is_ally = (team_name == 'Unassigned')

            if guild_id in self.all_team_tags and team_name in self.all_team_tags[guild_id]:
                tag = self.all_team_tags[guild_id][team_name]
                team_tag = f"*{tag}* "  # Italicized tag with space

            # Get player display name with asterisk for allies
            player_name = player['player_name'][:25]
            ally_indicator = "*" if is_ally else ""
            display_name = f"{team_tag}{player_name}{ally_indicator}"

            if player.get('war_count', 0) > 0:
                avg_score = player.get('average_score', 0.0)
                war_count = float(player.get('war_count', 0))

                # Bold the column being sorted by
                if self.sortby is None or self.sortby == 'avg':
                    player_str = f"{rank}. {flag} {display_name} | **{avg_score:.1f}** avg | {war_count:.1f} wars"
                elif self.sortby == 'warcount':
                    player_str = f"{rank}. {flag} {display_name} | {avg_score:.1f} avg | **{war_count:.1f}** wars"
                else:
                    player_str = f"{rank}. {flag} {display_name} | {avg_score:.1f} avg | {war_count:.1f} wars"

                # Add third column based on sort type (and bold it)
                if self.sortby == 'avg10':
                    avg10 = player.get('avg10_score')
                    if avg10 is not None:
                        player_str += f" | **{avg10:.1f}** avg10"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'avgdiff':
                    total_diff = player.get('total_team_differential', 0)
                    avg_diff = total_diff / war_count if war_count > 0 else 0
                    diff_symbol = "+" if avg_diff >= 0 else ""
                    player_str += f" | **{diff_symbol}{avg_diff:.1f}**"
                elif self.sortby == 'clutch':
                    clutch = player.get('clutch_factor')
                    if clutch is not None:
                        clutch_symbol = "+" if clutch >= 0 else ""
                        category = self.bot.db.stats.get_clutch_category(clutch)
                        player_str += f" | **{clutch_symbol}{clutch:.2f}** ({category})"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'cv':
                    consistency = player.get('consistency_score')
                    if consistency is not None:
                        player_str += f" | **{consistency:.1f}%**"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'form':
                    form = player.get('form_score')
                    if form is not None and form > 0:
                        player_str += f" | **{form:.1f}**"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'highest':
                    highest = player.get('highest_score', 0)
                    player_str += f" | **{highest}**"
                elif self.sortby == 'hotstreak':
                    htsk = player.get('hotstreak')
                    if htsk is not None:
                        htsk_symbol = "+" if htsk >= 0 else ""
                        player_str += f" | **{htsk_symbol}{htsk:.2f}**"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'lastwar':
                    last_war = player.get('last_war_date')
                    if last_war:
                        player_str += f" | **{last_war}**"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'lowest':
                    lowest = player.get('lowest_score', 0)
                    player_str += f" | **{lowest}**"
                elif self.sortby == 'potential':
                    potential = player.get('potential')
                    if potential is not None:
                        player_str += f" | **{potential:.1f}**"
                    else:
                        player_str += " | **N/A**"
                elif self.sortby == 'totaldiff':
                    total_diff = player.get('total_team_differential', 0)
                    diff_symbol = "+" if total_diff >= 0 else ""
                    player_str += f" | **{diff_symbol}{total_diff}**"
                elif self.sortby == 'winrate':
                    win_pct = player.get('win_percentage', 0.0)
                    player_str += f" | **{win_pct:.1f}%**"

                leaderboard_text.append(player_str)
            else:
                leaderboard_text.append(f"{rank}. {flag} {display_name} | No wars")

        embed = discord.Embed(
            title=title,
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Global Rankings",
            value="\n".join(leaderboard_text) if leaderboard_text else "No player data available",
            inline=False
        )

        # Footer with page info and legend
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} • {self.total_players_count} Total Players • * = Ally (not assigned to team)")

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


class StatsCog(BaseCog):
    """Player statistics and leaderboard commands."""

    def _filter_active_members(self, roster_stats: List[Dict[str, Any]], interaction: discord.Interaction, role_config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter roster for active members based on Discord roles.

        Args:
            roster_stats: List of all players from database
            interaction: Discord interaction for guild context
            role_config: Guild role configuration

        Returns:
            List of players who are active members
        """
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

        return member_stats

    def _sort_player_stats(self, players_with_stats: List[Dict[str, Any]], sortby: Optional[str], guild_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Sort player statistics by specified criteria.

        Args:
            players_with_stats: List of players with war statistics
            sortby: Sort criteria (avg10, avgdiff, clutch, cv, form, highest, hotstreak, lastwar, lowest, potential, totaldiff, warcount, winrate)
            guild_id: Guild ID for database queries (required for some sorting options)

        Returns:
            Sorted list of player statistics
        """
        if sortby and sortby.lower() == 'avg10':
            players_filtered = [p for p in players_with_stats if p.get('avg10_score') is not None]
            players_filtered.sort(key=lambda x: x.get('avg10_score', 0), reverse=True)
            players_with_stats = players_filtered
        elif sortby and sortby.lower() == 'avgdiff':
            players_with_stats.sort(
                key=lambda x: x.get('total_team_differential', 0) / x.get('war_count', 1) if x.get('war_count', 1) > 0 else 0,
                reverse=True
            )
        elif sortby and sortby.lower() == 'clutch':
            players_filtered = [p for p in players_with_stats if p.get('clutch_factor') is not None]
            players_filtered.sort(key=lambda x: x.get('clutch_factor', 0), reverse=True)
            players_with_stats = players_filtered
        elif sortby and sortby.lower() == 'cv':
            players_with_cv = [p for p in players_with_stats if p.get('war_count', 0) >= 2]
            players_with_cv.sort(key=lambda x: x.get('consistency_score', 0), reverse=True)
            players_with_stats = players_with_cv
        elif sortby and sortby.lower() == 'form':
            players_filtered = [p for p in players_with_stats if p.get('form_score') is not None and p.get('form_score', 0) > 0]
            players_filtered.sort(key=lambda x: x.get('form_score', 0), reverse=True)
            players_with_stats = players_filtered
        elif sortby and sortby.lower() == 'highest':
            players_with_stats.sort(key=lambda x: x.get('highest_score', 0), reverse=True)
        elif sortby and sortby.lower() == 'hotstreak':
            players_filtered = [p for p in players_with_stats if p.get('hotstreak') is not None]
            players_filtered.sort(key=lambda x: x.get('hotstreak', 0), reverse=True)
            players_with_stats = players_filtered
        elif sortby and sortby.lower() == 'lastwar':
            players_filtered = [p for p in players_with_stats if p.get('last_war_date') is not None]
            players_filtered.sort(key=lambda x: x.get('last_war_date', ''), reverse=True)
            players_with_stats = players_filtered
        elif sortby and sortby.lower() == 'lowest':
            players_with_stats.sort(key=lambda x: x.get('lowest_score', 0), reverse=True)
        elif sortby and sortby.lower() == 'potential':
            players_filtered = [p for p in players_with_stats if p.get('potential') is not None]
            players_filtered.sort(key=lambda x: x.get('potential', 0), reverse=True)
            players_with_stats = players_filtered
        elif sortby and sortby.lower() == 'totaldiff':
            players_with_stats.sort(key=lambda x: x.get('total_team_differential', 0), reverse=True)
        elif sortby and sortby.lower() == 'warcount':
            players_with_stats.sort(key=lambda x: x.get('war_count', 0), reverse=True)
        elif sortby and sortby.lower() == 'winrate':
            players_with_stats.sort(key=lambda x: x.get('win_percentage', 0), reverse=True)
        else:
            # Default: sort by average score
            players_with_stats.sort(key=lambda x: x.get('average_score', 0), reverse=True)

        return players_with_stats

    async def _display_player_stats(self, interaction: discord.Interaction, player_name: str, stats: Dict[str, Any], lastxwars: Optional[int] = None, guild_id: Optional[int] = None) -> None:
        """Display individual player statistics with embed."""
        from datetime import datetime

        # Get flag emoji
        country_code = stats.get('country_code', '')
        flag = country_code_to_flag(country_code) if country_code else ""
        flag_prefix = f"{flag} " if flag else ""

        # Get player display name with team tag
        team_name = stats.get('team', 'Unassigned')
        display_name = get_player_display_name(stats['player_name'], team_name, guild_id, self.bot.db)

        # Determine title and color based on context
        if lastxwars is not None:
            title_text = f"{flag_prefix}{display_name} (Last {lastxwars} Wars)"
            scope_text = f"Last {lastxwars} Wars"
        else:
            title_text = f"{flag_prefix}{display_name}"
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

        # Performance Overview (highest, average, avg10, lowest scores)
        highest_score = stats.get('highest_score', 0)
        avg_score = stats.get('average_score', 0.0)
        lowest_score = stats.get('lowest_score', 0)

        # Use cached avg10 and form metrics from stats dict
        avg10_score = None
        htsk_score = None
        overall_avg = avg_score
        form_score = stats.get('form_score')

        if lastxwars == 10:
            avg10_score = avg_score
            overall_stats = self.bot.db.stats.get_player_stats(player_name, guild_id)
            if overall_stats:
                fetched_avg = overall_stats.get('average_score')
                if fetched_avg is not None and fetched_avg > 0:
                    overall_avg = fetched_avg
        else:
            avg10_score = stats.get('avg10_score')
            war_count = stats.get('war_count', 0)
            if avg10_score is None and war_count >= 10:
                self.bot.db.stats._refresh_volatile_metrics(player_name, guild_id)
                updated_stats = self.bot.db.stats.get_player_stats(player_name, guild_id)
                if updated_stats:
                    avg10_score = updated_stats.get('avg10_score')
                    form_score = updated_stats.get('form_score')

        # Use cached hotstreak if available, calculate from avg10 if needed
        if stats.get('hotstreak') is not None:
            htsk_score = stats.get('hotstreak')
        elif avg10_score is not None and avg10_score > 0 and overall_avg > 0:
            htsk_score = avg10_score - overall_avg

        # Add soccer-style rating indicator for clarity
        form_display = ""
        if form_score is not None:
            if form_score >= 9.0:
                indicator = " ⭐"  # World class
            elif form_score >= 8.0:
                indicator = " 🔥"  # Excellent/Hot
            elif form_score >= 7.0:
                indicator = " ↑"  # Good/Rising
            elif form_score < 6.0:
                indicator = " ↓"  # Below average
            else:
                indicator = ""  # Average (6.0-6.9), no indicator needed
            form_display = f"\nForm:       {form_score:.1f}{indicator}"

        # Build performance text with avg10, Form, and HtSk
        if avg10_score is not None and htsk_score is not None and form_score is not None:
            htsk_sign = "+" if htsk_score >= 0 else ""
            performance_text = f"```\nHighest:    {highest_score}\nAverage:    {avg_score:.1f}\navg10:      {avg10_score:.1f}{form_display}\nHtSk:       {htsk_sign}{htsk_score:.2f}\nLowest:     {lowest_score}\n```"
        elif avg10_score is not None and htsk_score is not None:
            htsk_sign = "+" if htsk_score >= 0 else ""
            performance_text = f"```\nHighest:    {highest_score}\nAverage:    {avg_score:.1f}\navg10:      {avg10_score:.1f}\nHtSk:       {htsk_sign}{htsk_score:.2f}\nLowest:     {lowest_score}\n```"
        elif avg10_score is not None:
            performance_text = f"```\nHighest:    {highest_score}\nAverage:    {avg_score:.1f}\navg10:      {avg10_score:.1f}\nLowest:     {lowest_score}\n```"
        else:
            performance_text = f"```\nHighest:    {highest_score}\nAverage:    {avg_score:.1f}\nLowest:     {lowest_score}\n```"

        embed.add_field(name="⚔️ Performance", value=performance_text, inline=True)

        # Consistency Score (0-100%, where 100 = perfectly consistent)
        consistency_score = stats.get('consistency_score')
        if consistency_score is not None:
            consistency_text = f"```\n{consistency_score:.1f}%\n```"
        else:
            consistency_text = "```\nN/A\n(Need 2+ wars)\n```"
        embed.add_field(name="📊 Consistency", value=consistency_text, inline=True)

        # Clutch Factor (performance in close wars)
        clutch_factor = stats.get('clutch_factor')
        if clutch_factor is None and float(stats.get('war_count', 0)) >= 2:
            clutch_factor = self.bot.db.stats.get_player_clutch_factor(player_name, guild_id)
            if clutch_factor is not None:
                stats['clutch_factor'] = clutch_factor

        if clutch_factor is not None:
            clutch_symbol = "+" if clutch_factor >= 0 else ""
            clutch_category = self.bot.db.stats.get_clutch_category(clutch_factor)
            clutch_text = f"```\n{clutch_symbol}{clutch_factor:.2f}\n{clutch_category}\n```"
        else:
            clutch_text = "```\nN/A\n(Need 2+ wars)\n```"
        embed.add_field(name="⚡ Clutch Factor", value=clutch_text, inline=True)

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

        # Last 10 War Scores
        last_scores = self.bot.db.stats.get_player_last_war_scores(player_name, limit=10, guild_id=guild_id)
        if last_scores:
            scores_list = []
            for score in last_scores:
                score_value = score['score']
                race_count = score.get('race_count', 12)
                if race_count != 12:
                    scores_list.append(f"{score_value} ({race_count})")
                else:
                    scores_list.append(str(score_value))
            scores_text = f"```\n{', '.join(scores_list)}\n```"
            embed.add_field(name="📜 Last 10 Wars", value=scores_text, inline=False)

        # Footer
        embed.set_footer(text=f"Guild-Specific {scope_text}")

        await interaction.followup.send(embed=embed)

    async def _display_leaderboard(self, interaction: discord.Interaction, guild_id: int, member_stats: list, sortby: str):
        """Display leaderboard with pagination for all members."""
        # Get war statistics for members who have them
        players_with_stats = []
        players_without_stats = []

        for roster_player in member_stats:
            war_stats = self.bot.db.stats.get_player_stats(roster_player['player_name'], guild_id)
            if war_stats:
                # For volatile metrics that need refreshing (first access after war change)
                if sortby in ['avg10', 'hotstreak', 'form', 'clutch', 'potential']:
                    player_name = roster_player['player_name']
                    war_count = war_stats.get('war_count', 0)

                    # Map sortby to metric key and required minimum wars
                    metric_requirements = {
                        'avg10': ('avg10_score', 10),
                        'hotstreak': ('hotstreak', 10),
                        'form': ('form_score', 10),
                        'clutch': ('clutch_factor', 2),
                        'potential': ('potential', 10),
                    }

                    metric_key, min_wars = metric_requirements.get(sortby, (None, 0))

                    # If metric is NULL but player has enough wars, refresh cache
                    if metric_key and war_stats.get(metric_key) is None and war_count >= min_wars:
                        self.bot.db.stats._refresh_volatile_metrics(player_name, guild_id)
                        war_stats = self.bot.db.stats.get_player_stats(player_name, guild_id)

                    # Fetch clutch factor for Clutch sorting
                    if sortby == 'clutch':
                        clutch_factor = self.bot.db.stats.get_player_clutch_factor(player_name, guild_id)
                        war_stats['clutch_factor'] = clutch_factor

                    # Fetch potential for Potential sorting
                    if sortby == 'potential':
                        potential = self.bot.db.stats.get_player_potential(player_name, guild_id)
                        war_stats['potential'] = potential

                players_with_stats.append(war_stats)
            else:
                players_without_stats.append(roster_player)

        # Sort players with stats by sortby parameter
        players_with_stats = self._sort_player_stats(players_with_stats, sortby, guild_id)

        # Combine and sort all players - those with stats first, then without stats
        all_players = players_with_stats + players_without_stats

        # Use pagination view for leaderboard
        view = LeaderboardView(all_players, sortby, len(all_players), self.bot, guild_id)
        embed = view.create_embed()

        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="stats", description="View player statistics or leaderboard")
    @app_commands.describe(
        player="Player name to view stats for (optional - shows leaderboard if empty)",
        sortby="Leaderboard sort method",
        lastxwars="Show stats for last X wars only (optional - shows all-time if empty)"
    )
    @app_commands.choices(
        sortby=[
            app_commands.Choice(name="Average 10", value="avg10"),
            app_commands.Choice(name="Average Team Differential", value="avgdiff"),
            app_commands.Choice(name="Clutch Factor", value="clutch"),
            app_commands.Choice(name="Consistency", value="cv"),
            app_commands.Choice(name="Form", value="form"),
            app_commands.Choice(name="Highest Score", value="highest"),
            app_commands.Choice(name="Hotstreak", value="hotstreak"),
            app_commands.Choice(name="Last War", value="lastwar"),
            app_commands.Choice(name="Lowest", value="lowest"),
            app_commands.Choice(name="Potential", value="potential"),
            app_commands.Choice(name="Total Differential", value="totaldiff"),
            app_commands.Choice(name="Number of Wars", value="warcount"),
            app_commands.Choice(name="Win Rate", value="winrate")
        ],
        lastxwars=[
            app_commands.Choice(name="Last 5 Wars", value=5),
            app_commands.Choice(name="Last 10 Wars", value=10),
            app_commands.Choice(name="Last 20 Wars", value=20),
            app_commands.Choice(name="Last 50 Wars", value=50),
            app_commands.Choice(name="Last 100 Wars", value=100)
        ]
    )
    @require_guild_setup(defer=True)
    async def stats_slash(
        self,
        interaction: discord.Interaction,
        player: Optional[str] = None,
        sortby: Optional[str] = None,
        lastxwars: Optional[int] = None
    ):
        """View statistics for a specific player or all players."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)

            # Auto-default to Discord user if lastxwars is specified but player is not
            if not player and lastxwars is not None:
                # Look up player by Discord user ID
                with self.bot.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT player_name
                        FROM players
                        WHERE discord_user_id = %s AND guild_id = %s AND is_active = TRUE
                    """, (interaction.user.id, guild_id))
                    result = cursor.fetchone()

                    if result:
                        player = result[0]
                    else:
                        await interaction.followup.send(
                            "❌ You're not linked to a player in this guild. Ask an admin to add you with `/addplayer`.",
                            ephemeral=True
                        )
                        return

            if player:
                # Resolve nickname to actual player name first
                resolved_player = self.bot.db.players.resolve_player_name(player, guild_id)
                if not resolved_player:
                    await interaction.followup.send(f"❌ No player found with name or nickname: {player}", ephemeral=True)
                    return

                # Handle lastxwars parameter validation and stats retrieval
                if lastxwars is not None:
                    if lastxwars < 1:
                        await interaction.followup.send("❌ Must be at least 1 war.", ephemeral=True)
                        return

                    distinct_wars = self.bot.db.stats.get_player_distinct_war_count(resolved_player, guild_id)
                    if distinct_wars == 0:
                        await interaction.followup.send(f"❌ {resolved_player} hasn't participated in any wars yet.", ephemeral=True)
                        return

                    if lastxwars > distinct_wars:
                        await interaction.followup.send(f"❌ {resolved_player} has only participated in {distinct_wars} wars, can't show last {lastxwars}.", ephemeral=True)
                        return

                    stats = self.bot.db.stats.get_player_stats_last_x_wars(resolved_player, lastxwars, guild_id)
                else:
                    stats = self.bot.db.stats.get_player_stats(resolved_player, guild_id)

                if stats:
                    await self._display_player_stats(interaction, resolved_player, stats, lastxwars, guild_id)
                else:
                    roster_stats = self.bot.db.players.get_player_info(resolved_player, guild_id)
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

                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send(f"❌ No stats found for player: {player}", ephemeral=True)
            else:
                # Get all player statistics from players table
                roster_stats = self.bot.db.players.get_all_players_stats(guild_id)

                # Get guild role configuration to check actual Discord roles
                role_config = self.bot.db.guilds.get_guild_role_config(guild_id)

                # Filter for active members
                member_stats = self._filter_active_members(roster_stats, interaction, role_config)

                if not member_stats:
                    await interaction.followup.send("❌ No members found with the Member role in Discord.", ephemeral=True)
                    return

                # Display leaderboard
                await self._display_leaderboard(interaction, guild_id, member_stats, sortby)

        except Exception as e:
            logging.error(f"Error in stats command: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving stats.", ephemeral=True)

    @app_commands.command(
        name="leaderboard",
        description="🌍 View global cross-guild leaderboard sorted by various metrics"
    )
    @app_commands.describe(
        sortby="Metric to sort by (default: average score)"
    )
    @app_commands.choices(sortby=[
        app_commands.Choice(name="Average - Overall average score", value="avg"),
        app_commands.Choice(name="Avg10 - Average of last 10 wars (10+ wars)", value="avg10"),
        app_commands.Choice(name="Average Differential - Average team differential", value="avgdiff"),
        app_commands.Choice(name="Clutch - Clutch factor in close games (2+ wars)", value="clutch"),
        app_commands.Choice(name="Consistency - Score consistency (2+ wars)", value="cv"),
        app_commands.Choice(name="Form - Current form score (10+ wars)", value="form"),
        app_commands.Choice(name="Highest - Highest single war score", value="highest"),
        app_commands.Choice(name="Hotstreak - Recent performance trend (10+ wars)", value="hotstreak"),
        app_commands.Choice(name="Last War - Most recent war date", value="lastwar"),
        app_commands.Choice(name="Lowest - Lowest single war score", value="lowest"),
        app_commands.Choice(name="Potential - Performance ceiling (10+ wars)", value="potential"),
        app_commands.Choice(name="Total Differential - Total team differential", value="totaldiff"),
        app_commands.Choice(name="War Count - Number of wars played", value="warcount"),
        app_commands.Choice(name="Win Rate - Win percentage", value="winrate"),
    ])
    async def leaderboard_slash(
        self,
        interaction: discord.Interaction,
        sortby: Optional[str] = None
    ):
        """Display global cross-guild leaderboard."""
        await interaction.response.defer()

        # Default sortby to 'avg'
        if sortby is None:
            sortby = 'avg'

        # Global minimum war threshold for leaderboard data quality
        MIN_WARS_FOR_LEADERBOARD = 20

        try:
            # Get all players across all guilds (excludes testing guilds via env var)
            all_players_basic = self.bot.db.players.get_all_players_stats_global()

            if not all_players_basic:
                await interaction.followup.send(
                    "❌ No active players found in the database.",
                    ephemeral=True
                )
                return

            # Get full stats for each player (cached metrics)
            players_with_stats = []
            for player_basic in all_players_basic:
                player_name = player_basic['player_name']
                guild_id = player_basic['guild_id']

                # Get full stats including cached metrics
                stats = self.bot.db.stats.get_player_stats(player_name, guild_id)
                if stats and stats.get('war_count', 0) >= MIN_WARS_FOR_LEADERBOARD:
                    # Add guild_id to stats for guild identification
                    stats['guild_id'] = guild_id
                    players_with_stats.append(stats)

            if not players_with_stats:
                await interaction.followup.send(
                    f"❌ No players found with {MIN_WARS_FOR_LEADERBOARD}+ wars. Global leaderboard requires players to have at least {MIN_WARS_FOR_LEADERBOARD} wars for data quality.",
                    ephemeral=True
                )
                return

            # Trigger volatile metrics refresh if needed (same as guild leaderboard)
            if sortby in ['avg10', 'hotstreak', 'form', 'clutch', 'potential']:
                metric_key = {
                    'avg10': 'avg10_score',
                    'hotstreak': 'hotstreak',
                    'form': 'form_score',
                    'clutch': 'clutch_factor',
                    'potential': 'potential'
                }.get(sortby, sortby)

                for stats in players_with_stats:
                    if stats.get(metric_key) is None and stats.get('war_count', 0) >= MIN_WARS_FOR_LEADERBOARD:
                        self.bot.db.stats._refresh_volatile_metrics(
                            stats['player_name'],
                            stats['guild_id']
                        )
                        # Re-fetch stats
                        refreshed = self.bot.db.stats.get_player_stats(
                            stats['player_name'],
                            stats['guild_id']
                        )
                        if refreshed:
                            stats.update(refreshed)

                        # Explicitly populate clutch_factor and potential if needed
                        if sortby == 'clutch' and stats.get('clutch_factor') is None:
                            clutch = self.bot.db.stats.get_player_clutch_factor(
                                stats['player_name'],
                                stats['guild_id']
                            )
                            if clutch is not None:
                                stats['clutch_factor'] = clutch

                        if sortby == 'potential' and stats.get('potential') is None:
                            potential = self.bot.db.stats.get_player_potential(
                                stats['player_name'],
                                stats['guild_id']
                            )
                            if potential is not None:
                                stats['potential'] = potential

            # Sort using existing method (works cross-guild)
            players_with_stats = self._sort_player_stats(
                players_with_stats,
                sortby,
                guild_id=0  # Not used for global leaderboard
            )

            # Display with GlobalLeaderboardView
            view = GlobalLeaderboardView(
                players_with_stats,
                sortby,
                len(players_with_stats),
                self.bot
            )
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.error(f"❌ Error in /leaderboard command: {e}")
            import traceback
            logging.error(traceback.format_exc())
            await interaction.followup.send(
                "❌ An error occurred while generating the leaderboard.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
