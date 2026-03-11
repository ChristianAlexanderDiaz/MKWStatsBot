"""
Formatting utility functions.

Moved from commands.py to eliminate duplication and enable reuse.
"""

from typing import TYPE_CHECKING

from ..constants import ERROR_MSG_TRUNCATE_LENGTH, UNICODE_REGIONAL_INDICATOR_OFFSET

if TYPE_CHECKING:
    from ..database import DatabaseManager


def country_code_to_flag(country_code: str) -> str:
    """Convert 2-letter country code to flag emoji."""
    if not country_code or len(country_code) != 2:
        return ""
    country_code = country_code.upper()
    if not all("A" <= char <= "Z" for char in country_code):
        return ""
    flag = ""
    for char in country_code:
        flag += chr(UNICODE_REGIONAL_INDICATOR_OFFSET + ord(char) - 65)
    return flag


def get_player_display_name(
    player_name: str,
    team_name: str,
    guild_id: int,
    db: "DatabaseManager | None" = None,
    team_tags: dict[str, str] | None = None,
) -> str:
    """Return player name with team tag prefix if tag exists.

    Args:
        player_name: Player's name
        team_name: Player's team name
        guild_id: Guild ID (kept for signature compat; unused when team_tags provided)
        db: Deprecated — callers should pre-fetch team_tags instead
        team_tags: Pre-fetched team tags dict (required for asyncpg callers)

    Returns:
        'TAG Playername' if tag exists, 'Playername' otherwise
    """
    if not team_name or team_name == "Unassigned":
        return player_name

    if team_tags is not None:
        tag = team_tags.get(team_name)
    else:
        # No sync DB fallback — callers must supply team_tags
        tag = None

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
