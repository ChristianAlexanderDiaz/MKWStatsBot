"""Domain-specific command cogs for the Mario Kart bot."""

from .guild_cog import GuildCog
from .player_cog import PlayerCog
from .war_cog import WarCog
from .stats_cog import StatsCog
from .team_cog import TeamCog
from .nickname_cog import NicknameCog
from .member_cog import MemberCog
from .ocr_cog import OCRCog

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
