"""Nickname management commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .base_cog import BaseCog, require_guild_setup


class NicknameCog(BaseCog):
    """Nickname management commands for OCR recognition."""

    @app_commands.command(name="addnickname", description="Add a nickname to a player for OCR recognition")
    @app_commands.describe(player_name="Player to add nickname for", nickname="Nickname to add")
    @require_guild_setup
    async def add_nickname(self, interaction: discord.Interaction, player_name: str, nickname: str) -> None:
        """Add a single nickname to a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            resolved_player = await self.bot.db.players.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table. Use `/addplayer {player_name}` to add them first.", ephemeral=True)
                return

            if nickname.lower() == resolved_player.lower():
                await interaction.response.send_message(f"❌ No need to add **{nickname}** as a nickname for **{resolved_player}** - name matching is case-insensitive!", ephemeral=True)
                return

            success = await self.bot.db.players.add_nickname(resolved_player, nickname, guild_id)

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
    async def remove_nickname(self, interaction: discord.Interaction, player_name: str, nickname: str) -> None:
        """Remove a nickname from a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            resolved_player = await self.bot.db.players.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.", ephemeral=True)
                return

            success = await self.bot.db.players.remove_nickname(resolved_player, nickname, guild_id)

            if success:
                embed = discord.Embed(
                    title="✅ Nickname Removed!",
                    description=f"Removed nickname **{nickname}** from **{resolved_player}**",
                    color=0xff4444
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ Nickname **{nickname}** not found for **{resolved_player}** or couldn't be removed.", ephemeral=True)

        except Exception as e:
            logging.error(f"Error removing nickname: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error removing nickname", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error removing nickname", ephemeral=True)

    @app_commands.command(name="nicknamesfor", description="Show all nicknames for a player")
    @app_commands.describe(player_name="Player to show nicknames for")
    @require_guild_setup
    async def show_nicknames(self, interaction: discord.Interaction, player_name: str) -> None:
        """Show all nicknames for a player."""
        try:
            guild_id = self.get_guild_id(interaction)
            resolved_player = await self.bot.db.players.resolve_player_name(player_name, guild_id)
            if not resolved_player:
                await interaction.response.send_message(f"❌ Player **{player_name}** not found in players table.", ephemeral=True)
                return

            nicknames = await self.bot.db.players.get_player_nicknames(resolved_player, guild_id)

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NicknameCog(bot))
