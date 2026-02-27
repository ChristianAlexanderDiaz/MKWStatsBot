"""
Repository modules for the MKW Stats Bot.

Each repository handles a specific domain of database operations:
- PlayerRepository: Player CRUD, roster, nicknames, Discord linking
- WarRepository: War CRUD, duplicate detection
- StatsRepository: Player statistics and metrics
- GuildRepository: Guild configuration, teams, tags, roles
"""

from .player_repository import PlayerRepository
from .war_repository import WarRepository
from .stats_repository import StatsRepository
from .guild_repository import GuildRepository

__all__ = [
    "PlayerRepository",
    "WarRepository",
    "StatsRepository",
    "GuildRepository",
]
