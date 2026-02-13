"""
Formatting utility functions.

Moved from commands.py to eliminate duplication and enable reuse.
"""

from typing import Optional, Dict, TYPE_CHECKING

from ..constants import UNICODE_REGIONAL_INDICATOR_OFFSET, ERROR_MSG_TRUNCATE_LENGTH

if TYPE_CHECKING:
    from ..database import DatabaseManager


def country_code_to_flag(country_code: str) -> str:
    """Convert 2-letter country code to flag emoji."""
    if not country_code or len(country_code) != 2:
        return ""
    country_code = country_code.upper()
    flag = ""
    for char in country_code:
        if "A" <= char <= "Z":
            flag += chr(UNICODE_REGIONAL_INDICATOR_OFFSET + ord(char) - 65)
    return flag


def get_player_display_name(
    player_name: str,
    team_name: str,
    guild_id: int,
    db: "DatabaseManager",
    team_tags: Optional[Dict[str, str]] = None,
) -> str:
    """Return player name with team tag prefix if tag exists.

    Args:
        player_name: Player's name
        team_name: Player's team name
        guild_id: Guild ID
        db: Database manager instance
        team_tags: Optional pre-fetched team tags dict to avoid DB calls

    Returns:
        'TAG Playername' if tag exists, 'Playername' otherwise
    """
    if not team_name or team_name == "Unassigned":
        return player_name

    if team_tags is not None:
        tag = team_tags.get(team_name)
    else:
        tag = db.get_team_tag(guild_id, team_name)

    if tag:
        return f"{tag} {player_name}"
    return player_name


def format_error_for_user(error: Exception, context: str = "") -> str:
    """Convert exception to user-friendly message with technical details.

    Args:
        error: The exception that occurred
        context: Optional context about where the error occurred

    Returns:
        Formatted error message for Discord users
    """
    error_type = type(error).__name__
    error_msg = str(error)

    if len(error_msg) > ERROR_MSG_TRUNCATE_LENGTH:
        error_msg = error_msg[:ERROR_MSG_TRUNCATE_LENGTH] + "..."

    if context:
        return f"❌ {context}: {error_type} - {error_msg}"
    return f"❌ {error_type}: {error_msg}"
