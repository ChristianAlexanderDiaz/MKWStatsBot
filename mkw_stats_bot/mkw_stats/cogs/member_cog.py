"""Member status management commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..utils.formatters import get_player_display_name
from .base_cog import MEMBER_STATUS_CHOICES, BaseCog, require_guild_setup


class MemberCog(BaseCog):
    """Member status tracking commands."""

    @app_commands.command(name="setmemberstatus", description="Set the member status for a player")
    @app_commands.describe(
        player_name="Player to set status for",
        member_status="New member status"
    )
    @app_commands.choices(member_status=MEMBER_STATUS_CHOICES)
    @require_guild_setup
    async def set_member_status(self, interaction: discord.Interaction, player_name: str, member_status: str) -> None:
        """Set the member status for a player."""
        try:
            guild_id = self.get_guild_id(interaction)

            resolved_player = await self.bot.db.players.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.")
                return

            success = await self.bot.db.players.set_player_member_status(resolved_player, member_status, guild_id)

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
    @require_guild_setup(defer=True)
    async def show_trials(self, interaction: discord.Interaction) -> None:
        """Show all trial members."""
        try:
            guild_id = self.get_guild_id(interaction)

            trials = await self.bot.db.players.get_players_by_member_status('trial', guild_id)

            embed = discord.Embed(
                title="🔍 Trial Members",
                color=0xffa500
            )

            team_tags = await self.bot.db.guilds.get_all_team_tags(guild_id)

            if trials:
                trial_list = []
                for player in trials:
                    team_name = player.get('team', 'Unassigned')
                    display_name = get_player_display_name(player['player_name'], team_name, team_tags=team_tags)
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
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing trials: {e}")
            await interaction.followup.send("❌ Error retrieving trial members", ephemeral=True)

    @app_commands.command(name="showkicked", description="Show all kicked members")
    @require_guild_setup(defer=True)
    async def show_kicked(self, interaction: discord.Interaction) -> None:
        """Show all kicked members."""
        try:
            guild_id = self.get_guild_id(interaction)

            kicked = await self.bot.db.players.get_players_by_member_status('kicked', guild_id)

            embed = discord.Embed(
                title="🚫 Kicked Members",
                color=0xff4444
            )

            if kicked:
                kicked_list = []
                for player in kicked:
                    nickname_count = len(player.get('nicknames', []))
                    nickname_text = f" ({nickname_count} nicknames)" if nickname_count > 0 else ""
                    team_text = f" - {player.get('team', 'Unassigned')}" if player.get('team', 'Unassigned') != 'Unassigned' else ""
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
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing kicked members: {e}")
            await interaction.followup.send("❌ Error retrieving kicked members", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemberCog(bot))
