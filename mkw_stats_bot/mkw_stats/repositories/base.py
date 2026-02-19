"""
Base repository providing shared database access.

All domain repositories inherit from this class to get
connection pool access and common validation helpers.
"""

import logging
from contextlib import contextmanager


class BaseRepository:
    """Base class for all repositories. Provides connection pool access."""

    def __init__(self, db_manager):
        """
        Args:
            db_manager: DatabaseManager instance (provides connection pool)
        """
        self._db = db_manager

    @contextmanager
    def get_connection(self):
        """Delegate to DatabaseManager's connection pool."""
        with self._db.get_connection() as conn:
            yield conn

    def _validate_guild_id(self, guild_id: int, operation_name: str = "database operation") -> None:
        """Validate guild_id to prevent cross-guild data contamination."""
        if guild_id <= 0:
            error_msg = f"Invalid guild_id={guild_id} for {operation_name}. Guild ID must be positive."
            logging.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
