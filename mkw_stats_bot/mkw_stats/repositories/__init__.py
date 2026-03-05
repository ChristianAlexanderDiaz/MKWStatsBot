"""
Repository modules for the MKW Stats Bot.

Each repository handles a specific domain of database operations:
- PlayerRepository: Player CRUD, roster, nicknames, Discord linking
- WarRepository: War CRUD, duplicate detection
- StatsRepository: Player statistics and metrics
- GuildRepository: Guild configuration, teams, tags, roles
"""

from .guild_repository import GuildRepository
from .player_repository import PlayerRepository
from .stats_repository import StatsRepository
from .war_repository import WarRepository

__all__ = [
    "PlayerRepository",
    "WarRepository",
    "StatsRepository",
    "GuildRepository",
]
