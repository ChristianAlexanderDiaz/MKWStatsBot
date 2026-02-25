"""Member status management commands."""

import logging
import discord
from discord import app_commands

from .base_cog import BaseCog, require_guild_setup, MEMBER_STATUS_CHOICES
from ..utils.formatters import get_player_display_name


class MemberCog(BaseCog):
    """Member status tracking commands."""

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

            resolved_player = self.bot.db.players.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return

            success = self.bot.db.players.set_player_member_status(resolved_player, member_status, guild_id)

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

            trials = self.bot.db.players.get_players_by_member_status('trial', guild_id)

            embed = discord.Embed(
                title="🔍 Trial Members",
                color=0xffa500
            )

            if trials:
                trial_list = []
                for player in trials:
                    team_name = player.get('team', 'Unassigned')
                    display_name = get_player_display_name(player['player_name'], team_name, guild_id, self.bot.db)
                    nickname_count = len(player.get('nicknames', []))
                    nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                    team_text = f" - {team_name}" if team_name != 'Unassigned' else ""
                    trial_list.append(f"• **{display_name}**{team_text}{nickname_text}")

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

            kicked = self.bot.db.players.get_players_by_member_status('kicked', guild_id)

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


async def setup(bot):
    await bot.add_cog(MemberCog(bot))
