"""War management commands."""

import asyncio
import logging

import discord
from discord import app_commands

from .base_cog import BaseCog, require_guild_setup


def _log_task_error(t: asyncio.Task) -> None:
    if not t.cancelled() and (exc := t.exception()):
        logging.debug(f"Background task failed: {exc}")


def create_duplicate_war_embed(resolved_results: list, races: int) -> discord.Embed:
    """Create an embed showing duplicate war detection with comparison."""
    embed = discord.Embed(
        title="⚠️ Duplicate War Detected",
        description="The war you're trying to add appears identical to your most recent war.",
        color=0xffa500
    )

    player_list = []
    for result in resolved_results:
        if result['races_played'] == races:
            player_list.append(f"**{result['name']}**: {result['score']} points")
        else:
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


class AddPlayerToWarConfirmView(discord.ui.View):
    """Confirmation view for adding players to an existing war."""

    def __init__(self, war_id: int, new_players: list, existing_war: dict, races: int,
                 user: discord.User, cog, guild_id: int):
        super().__init__(timeout=60.0)
        self.war_id = war_id
        self.new_players = new_players
        self.existing_war = existing_war
        self.races = races
        self.user = user
        self.cog = cog
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

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(view=self)

        success = self.cog.bot.db.wars.append_players_to_war_by_id(
            self.war_id, self.new_players, guild_id=self.guild_id
        )

        if success:
            submission = self.cog.bot.war_service.submit_appended_players(
                self.war_id, self.new_players, self.guild_id
            )
            stats_added = submission.stats_updated or []
            stats_failed = submission.stats_failed or []

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

    def __init__(self, war_id: int, war: dict, user: discord.User, cog, guild_id: int):
        super().__init__(timeout=60.0)
        self.war_id = war_id
        self.war = war
        self.user = user
        self.cog = cog
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

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(view=self)

        stats_reverted = self.cog.bot.db.wars.remove_war_by_id(self.war_id, guild_id=self.guild_id)

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


class WarCog(BaseCog):
    """War management commands: add, remove, show, append players."""

    @app_commands.command(name="addwar", description="Add a war with player scores")
    @app_commands.describe(
        player_scores="Player scores in format: 'Player1: 104, Player2: 105'. For substitutes use 'Player (races): score'",
        races="Number of races played (1-12, default: 12)"
    )
    @require_guild_setup
    async def addwar_slash(self, interaction: discord.Interaction, player_scores: str, races: int = 12):
        """Add a war manually with player scores using slash command."""
        try:
            guild_id = self.get_guild_id_from_interaction(interaction)

            if not self.is_guild_initialized(guild_id):
                await interaction.response.send_message("❌ Guild not set up! Please run `/setup` first to initialize your clan.", ephemeral=True)
                return

            if races < 1 or races > 12:
                await interaction.response.send_message("❌ Race count must be between 1 and 12.", ephemeral=True)
                return

            results = []

            parts = [p.strip() for p in player_scores.split(',')]

            for part in parts:
                if ':' in part:
                    try:
                        name, score_str = part.split(':', 1)
                        name = name.strip()
                        original_name = name
                        score_str = score_str.strip()
                        base_name = name

                        individual_races = races
                        if '(' in name and ')' in name:
                            base_name = name[:name.index('(')].strip()
                            race_count_str = name[name.index('(')+1:name.index(')')].strip()
                            try:
                                individual_races = int(race_count_str)
                                name = base_name

                                if individual_races < 1:
                                    await interaction.response.send_message(f"❌ Invalid race count for {base_name}: {individual_races}. Must be at least 1.", ephemeral=True)
                                    return
                                elif individual_races >= races:
                                    if individual_races == races:
                                        await interaction.response.send_message(f"❌ {base_name}({individual_races}): If they played all {races} races, use `{base_name}: {score_str}` instead (no parentheses).", ephemeral=True)
                                    else:
                                        await interaction.response.send_message(f"❌ {base_name}({individual_races}): Cannot play {individual_races} races when war only has {races} races total.", ephemeral=True)
                                    return
                            except ValueError:
                                await interaction.response.send_message(f"❌ Invalid race count format in: `{name}`. Use PlayerName(races): Score.", ephemeral=True)
                                return

                        score = int(score_str)

                        min_score = individual_races * 1
                        max_score = individual_races * 15
                        if score < min_score or score > max_score:
                            if '(' in original_name and ')' in original_name:
                                await interaction.response.send_message(f"❌ {base_name}({individual_races}): {score} points invalid. Must be {min_score}-{max_score} points for {individual_races} races.", ephemeral=True)
                            else:
                                await interaction.response.send_message(f"❌ {name}: {score} points invalid. Must be {min_score}-{max_score} points for {individual_races} races.", ephemeral=True)
                            return

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

            resolved_results = []
            failed_players = []

            for result in results:
                resolved_player = self.bot.db.players.resolve_player_name(result['name'], guild_id)
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

            actual_war_race_count = max(result['races_played'] for result in resolved_results)

            for result in resolved_results:
                if actual_war_race_count > 0:
                    result['war_participation'] = result['races_played'] / actual_war_race_count
                else:
                    result['war_participation'] = 0.0

            last_war_results = self.bot.db.wars.get_last_war_for_duplicate_check(guild_id)
            is_duplicate = self.bot.db.wars.check_for_duplicate_war(resolved_results, last_war_results)

            already_responded = False

            if is_duplicate:
                duplicate_embed = create_duplicate_war_embed(resolved_results, actual_war_race_count)

                await interaction.response.send_message(embed=duplicate_embed)
                confirmation_msg = await interaction.original_response()
                already_responded = True

                await confirmation_msg.add_reaction("✅")
                await confirmation_msg.add_reaction("❌")

                def check(reaction, user):
                    return (user == interaction.user and
                           str(reaction.emoji) in ["✅", "❌"] and
                           reaction.message.id == confirmation_msg.id)

                try:
                    reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                    if str(reaction.emoji) == "❌":
                        cancel_embed = discord.Embed(
                            title="❌ War Canceled",
                            description="Duplicate war was not added to the database.",
                            color=0xff4444
                        )
                        await interaction.edit_original_response(embed=cancel_embed)
                        return

                except TimeoutError:
                    timeout_embed = discord.Embed(
                        title="⏰ Confirmation Timeout",
                        description="Duplicate war confirmation timed out. War was not added.",
                        color=0xff4444
                    )
                    await interaction.edit_original_response(embed=timeout_embed)
                    return

            submission = self.bot.war_service.submit_war(resolved_results, actual_war_race_count, guild_id)

            if not submission.success:
                error_msg = f"❌ Failed to add war to database. {submission.error or 'Check logs for details.'}"
                if already_responded:
                    await interaction.edit_original_response(content=error_msg)
                else:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                return

            stats_updated = submission.stats_updated or []
            stats_failed = submission.stats_failed or []

            embed = discord.Embed(
                title=f"⚔️ War Added Successfully! (ID: {submission.war_id})",
                color=0x00ff00
            )

            player_list = []
            for result in resolved_results:
                if result['races_played'] == actual_war_race_count:
                    player_list.append(f"**{result['name']}**: {result['score']} points")
                else:
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

            embed.set_footer(text="Player statistics have been automatically updated")

            if already_responded:
                await interaction.edit_original_response(embed=embed, content="")
            else:
                await interaction.response.send_message(embed=embed)

            task = asyncio.create_task(self.bot._countdown_and_delete_interaction(interaction, embed))
            task.add_done_callback(_log_task_error)

        except Exception as e:
            logging.error(f"Error adding war: {e}")
            try:
                await interaction.response.send_message("❌ Error adding war. Check the command format and try again.", ephemeral=True)
            except discord.errors.InteractionResponded:
                await interaction.followup.send("❌ Error adding war. Check the command format and try again.", ephemeral=True)

    @app_commands.command(name="wars", description="Show recent wars")
    @app_commands.describe(limit="Number of wars to show (default: 10, max: 50)")
    @require_guild_setup(defer=True)
    async def show_all_wars(self, interaction: discord.Interaction, limit: int = 10):
        """Show all wars with pagination."""
        try:
            guild_id = self.get_guild_id(interaction)

            if limit < 1 or limit > 50:
                await interaction.followup.send("❌ Limit must be between 1 and 50.", ephemeral=True)
                return

            wars = self.bot.db.wars.get_all_wars(limit, guild_id)

            if not wars:
                await interaction.followup.send("❌ No wars found.", ephemeral=True)
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
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing all wars: {e}")
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

            existing_war = self.bot.db.wars.get_war_by_id(war_id, guild_id=guild_id)
            if not existing_war:
                await interaction.response.send_message(f"❌ War ID: {war_id} not found.", ephemeral=True)
                return

            races = existing_war.get('race_count', 12)

            new_players = []
            parts = [p.strip() for p in player_scores.split(',')]

            for part in parts:
                if ':' in part:
                    try:
                        name, score_str = part.split(':', 1)
                        name = name.strip()
                        score_str = score_str.strip()

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

                        score = int(score_str)

                        min_score = individual_races * 1
                        max_score = individual_races * 15
                        if score < min_score or score > max_score:
                            await interaction.response.send_message(f"❌ {name}: {score} points invalid for {individual_races} races.", ephemeral=True)
                            return

                        resolved_player = self.bot.db.players.resolve_player_name(name, guild_id)
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

            existing_results = existing_war.get('results', [])
            existing_names = {player.get('name', '').lower() for player in existing_results}
            conflicts = []
            for new_player in new_players:
                if new_player.get('name', '').lower() in existing_names:
                    conflicts.append(new_player.get('name', 'Unknown'))

            if conflicts:
                await interaction.response.send_message(f"❌ These players already exist in war {war_id}: {', '.join(conflicts)}\nUse a different command to update existing player scores.", ephemeral=True)
                return

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

            war = self.bot.db.wars.get_war_by_id(war_id, guild_id=guild_id)
            if not war:
                await interaction.response.send_message(f"❌ War ID: {war_id} not found.", ephemeral=True)
                return

            war_date = war.get('war_date')
            race_count = war.get('race_count')

            players_data = war.get('players_data', [])
            if isinstance(players_data, dict) and 'results' in players_data:
                players_data = players_data['results']

            embed = discord.Embed(
                title=f"⚠️ Remove War ID: {war_id}",
                description=f"Are you sure you want to remove this war from **{war_date}**?",
                color=0xff4444
            )

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

            view = RemoveWarConfirmView(war_id, war, interaction.user, self, guild_id)
            await interaction.response.send_message(embed=embed, view=view)

        except Exception as e:
            logging.error(f"Error removing war: {e}", exc_info=True)
            error_message = self._format_error_for_user(e, "Failed to remove war")
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(WarCog(bot))
