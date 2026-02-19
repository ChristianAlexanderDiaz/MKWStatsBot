"""
Centralized Discord embed creation.

Eliminates duplicated embed patterns across bot.py, commands.py, and handlers.
"""

import discord
from typing import List, Dict, Optional

from ..constants import (
    COLOR_SUCCESS,
    COLOR_ERROR,
    COLOR_WARNING,
    COLOR_INFO,
    COLOR_EXPIRED,
    COLOR_PURPLE,
    COLOR_DARK_EMBED,
    SORT_DISPLAY_NAMES,
    SORT_DESCRIPTIONS,
)


class EmbedBuilder:
    """Static factory methods for creating consistently-styled Discord embeds."""

    @staticmethod
    def success(title: str, description: str = "", **kwargs) -> discord.Embed:
        return discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=COLOR_SUCCESS,
            **kwargs,
        )

    @staticmethod
    def error(title: str, description: str = "", **kwargs) -> discord.Embed:
        return discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=COLOR_ERROR,
            **kwargs,
        )

    @staticmethod
    def warning(title: str, description: str = "", **kwargs) -> discord.Embed:
        return discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=COLOR_WARNING,
            **kwargs,
        )

    @staticmethod
    def info(title: str, description: str = "", **kwargs) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=COLOR_INFO,
            **kwargs,
        )

    @staticmethod
    def purple(title: str, description: str = "", **kwargs) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=COLOR_PURPLE,
            **kwargs,
        )

    @staticmethod
    def dark(title: str, description: str = "", **kwargs) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=COLOR_DARK_EMBED,
            **kwargs,
        )

    @staticmethod
    def expired(message: str = "The confirmation period has expired. Results were not saved.") -> discord.Embed:
        return discord.Embed(
            title="⏰ Confirmation Expired",
            description=message,
            color=COLOR_EXPIRED,
        )

    @staticmethod
    def war_saved(
        resolved_results: List[Dict],
        race_count: int,
        team_score: int,
        opponent_score: int,
        differential: int,
        war_id: Optional[int] = None,
    ) -> discord.Embed:
        """Build the standard war-saved embed used by OCR and manual addwar flows."""
        result_emoji = "🏆" if differential > 0 else ("🤝" if differential == 0 else "😢")

        title = f"{result_emoji} War Results Saved!"
        description = (
            f"**Score:** {team_score} - {opponent_score} ({differential:+d})\n"
            f"**Races:** {race_count}\n"
            f"**Players:** {len(resolved_results)}"
        )
        if war_id:
            description += f"\n**War ID:** {war_id}"

        embed = discord.Embed(title=title, description=description, color=COLOR_SUCCESS)

        # Add player scores
        player_lines = []
        for r in resolved_results:
            name = r.get("name", r.get("player_name", "Unknown"))
            score = r.get("score", 0)
            player_lines.append(f"**{name}**: {score}")

        if player_lines:
            embed.add_field(
                name="Player Scores",
                value="\n".join(player_lines),
                inline=False,
            )

        return embed

    @staticmethod
    def ocr_results(
        results: List[Dict],
        filename: str,
        race_count: int = 12,
        warnings: Optional[List[str]] = None,
    ) -> discord.Embed:
        """Build the OCR results detected embed for confirmation."""
        embed = discord.Embed(
            title="🔍 Race Results Detected",
            description=f"**Source:** {filename}\n**Races:** {race_count}",
            color=COLOR_INFO,
        )

        if warnings:
            embed.add_field(
                name="⚠️ Warnings",
                value="\n".join(f"• {w}" for w in warnings),
                inline=False,
            )

        player_lines = []
        for i, r in enumerate(results, 1):
            name = r.get("name", "Unknown")
            score = r.get("score", 0)
            player_lines.append(f"{i}. **{name}**: {score}")

        if player_lines:
            embed.add_field(
                name="Player Scores",
                value="\n".join(player_lines),
                inline=False,
            )

        embed.set_footer(text="✅ = Save | ❌ = Cancel | ✏️ = Edit")
        return embed

    @staticmethod
    def bulk_progress(current: int, total: int, filename: str = "") -> discord.Embed:
        """Build bulk scan progress embed."""
        pct = (current / total * 100) if total > 0 else 0
        bar_filled = int(pct / 10)
        bar_empty = 10 - bar_filled
        progress_bar = "█" * bar_filled + "░" * bar_empty

        description = f"Processing image {current}/{total}\n{progress_bar} {pct:.0f}%"
        if filename:
            description += f"\n📄 {filename}"

        return discord.Embed(
            title="🔄 Bulk Scan in Progress",
            description=description,
            color=COLOR_INFO,
        )
