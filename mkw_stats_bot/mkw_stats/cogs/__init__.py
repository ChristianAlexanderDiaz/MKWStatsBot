"""Domain-specific command cogs for the Mario Kart bot."""

from .guild_cog import GuildCog
from .member_cog import MemberCog
from .nickname_cog import NicknameCog
from .ocr_cog import OCRCog
from .player_cog import PlayerCog
from .stats_cog import StatsCog
from .team_cog import TeamCog
from .war_cog import WarCog

__all__ = [
    "GuildCog",
    "PlayerCog",
    "WarCog",
    "StatsCog",
    "TeamCog",
    "NicknameCog",
    "MemberCog",
    "OCRCog",
]
