"""
Validation utility functions.

Extracted from commands.py to eliminate duplication across cogs and services.
"""

from typing import Tuple, TYPE_CHECKING

import discord

from ..constants import BOT_OWNER_ID
from .. import config

if TYPE_CHECKING:
    from ..database import DatabaseManager


def validate_score(score: int, races: int) -> Tuple[bool, str]:
    """Validate a player's score for a given race count.

    Returns:
        (is_valid, error_message) tuple
    """
    practical_min = races
    practical_max = races * 15

    if score < practical_min or score > practical_max:
        return False, f"Score {score} invalid for {races} races (expected {practical_min}-{practical_max})"
    return True, ""


def validate_race_count(races: int) -> Tuple[bool, str]:
    """Validate race count is within allowed range.

    Returns:
        (is_valid, error_message) tuple
    """
    if races < config.MIN_RACE_COUNT or races > config.MAX_RACE_COUNT:
        return False, f"Race count must be {config.MIN_RACE_COUNT}-{config.MAX_RACE_COUNT}"
    return True, ""


def has_admin_permission(interaction: discord.Interaction) -> bool:
    """Check if user has admin permission (server admin, server owner, or bot owner)."""
    from ..database import DatabaseManager
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == interaction.guild.owner_id
        or DatabaseManager.is_bot_owner(interaction.user.id)
    )
