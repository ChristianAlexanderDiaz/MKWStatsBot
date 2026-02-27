#!/usr/bin/env python3
"""
PostgreSQL database system for Mario Kart clan stats.

DatabaseManager is the single entry point for all database operations.
Internally, it delegates to focused repository modules:
- PlayerRepository: Player CRUD, roster, nicknames, Discord linking
- WarRepository: War CRUD, duplicate detection
- StatsRepository: Player statistics and metrics
- GuildRepository: Guild configuration, teams, tags, roles

Usage remains unchanged:
    db = DatabaseManager()
    db.add_roster_player("Player1", guild_id=123)
    # OR use repositories directly:
    db.players.add_roster_player("Player1", guild_id=123)
"""

import psycopg2
import psycopg2.pool
import psycopg2.errors
import logging
from typing import List, Dict, Optional, Any
import os
from contextlib import contextmanager
from urllib.parse import urlparse

from .constants import (
    BOT_OWNER_ID,
    DB_POOL_MIN,
    DB_POOL_MAX,
    DB_STATEMENT_TIMEOUT,
    DB_CONNECT_TIMEOUT,
    EXCLUDED_GUILD_IDS,
)
from .repositories import PlayerRepository, WarRepository, StatsRepository, GuildRepository


class DatabaseManager:
    """Facade over domain-specific repositories.

    Provides backward-compatible method access (db.resolve_player_name())
    while organizing logic into focused repositories (db.players, db.wars, etc.).
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize PostgreSQL database connection.

        Args:
            database_url: PostgreSQL connection URL (Railway format)
                Format: postgresql://user:password@host:port/database
        """
        # Get database URL from environment or parameter
        self.database_url = (
            database_url or
            os.getenv('DATABASE_PUBLIC_URL') or
            os.getenv('DATABASE_URL') or
            os.getenv('RAILWAY_POSTGRES_URL') or
            self._build_local_url()
        )

        # Parse connection parameters
        self.connection_params = self._parse_database_url(self.database_url)

        # Create connection pool for better performance
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                DB_POOL_MIN, DB_POOL_MAX,
                **self.connection_params
            )
            logging.info("✅ PostgreSQL connection pool created successfully")
        except Exception as e:
            logging.error(f"❌ Failed to create PostgreSQL connection pool: {e}")
            raise

        # Initialize repositories
        self.players = PlayerRepository(self)
        self.wars = WarRepository(self)
        self.stats = StatsRepository(self)
        self.guilds = GuildRepository(self)

        # Initialize database schema
        self.init_database()

    def _build_local_url(self) -> str:
        """Build local PostgreSQL URL for development."""
        host = os.getenv('POSTGRES_HOST', 'localhost')
        database = os.getenv('POSTGRES_DB', 'mkw_stats_dev')
        user = os.getenv('POSTGRES_USER', os.getenv('USER', 'postgres'))
        password = os.getenv('POSTGRES_PASSWORD', '')
        port = os.getenv('POSTGRES_PORT', '5432')

        if password:
            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
        else:
            return f"postgresql://{user}@{host}:{port}/{database}"

    def _parse_database_url(self, url: str) -> Dict[str, Any]:
        """Parse DATABASE_URL into connection parameters with timeouts."""
        parsed = urlparse(url)
        params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading slash
            'user': parsed.username,
            'connect_timeout': DB_CONNECT_TIMEOUT,
            'options': f'-c statement_timeout={DB_STATEMENT_TIMEOUT}',
        }

        if parsed.password:
            params['password'] = parsed.password

        return params

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool with timeout error handling."""
        conn = None
        try:
            conn = self.connection_pool.getconn()
            yield conn
        except psycopg2.OperationalError as e:
            logging.error(f"❌ Database connection timeout or network error: {e}")
            if conn:
                conn.rollback()
            raise
        except psycopg2.errors.QueryCanceled as e:
            logging.error(f"❌ Database query timeout (exceeded 30s statement_timeout): {e}")
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def init_database(self):
        """Initialize the database tables if they don't exist."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if tables exist (check for players table now)
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'players'
                    );
                """)

                if cursor.fetchone()[0]:
                    # Tables exist, don't recreate
                    logging.info("✅ PostgreSQL tables already exist")
                    return

                # Create wars table (simplified from race_sessions)
                cursor.execute("""
                    CREATE TABLE wars (
                        id SERIAL PRIMARY KEY,
                        war_date DATE NOT NULL,
                        race_count INTEGER NOT NULL,
                        players_data JSONB NOT NULL,
                        guild_id BIGINT NOT NULL,
                        team_score INTEGER DEFAULT 0,
                        team_differential INTEGER DEFAULT 0,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # Create indexes for wars
                cursor.execute("""
                    CREATE INDEX idx_wars_guild_id ON wars(guild_id);
                    CREATE INDEX idx_wars_date ON wars(war_date DESC);
                    CREATE INDEX idx_wars_created ON wars(created_at DESC);
                """)

                # Create players table (unified roster + player_stats)
                cursor.execute("""
                    CREATE TABLE players (
                        id SERIAL PRIMARY KEY,
                        player_name VARCHAR(100) NOT NULL,
                        guild_id BIGINT NOT NULL,
                        team VARCHAR(50) DEFAULT 'Unassigned',
                        nicknames JSONB DEFAULT '[]',
                        added_by VARCHAR(100),
                        is_active BOOLEAN DEFAULT TRUE,
                        -- Statistics fields
                        total_score INTEGER DEFAULT 0,
                        total_races INTEGER DEFAULT 0,
                        war_count DECIMAL(8,3) DEFAULT 0,  -- Supports fractional wars (0.583 = 7/12 races), max 99999.999
                        average_score DECIMAL(5,2) DEFAULT 0.0,
                        last_war_date DATE,
                        -- Metadata
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(player_name, guild_id)
                    );
                """)

                # Create indexes for players
                cursor.execute("""
                    CREATE INDEX idx_players_guild_id ON players(guild_id);
                    CREATE INDEX idx_players_active ON players(is_active);
                    CREATE INDEX idx_players_team ON players(team);
                    CREATE INDEX idx_players_name ON players(player_name);
                """)

                # Create trigger to automatically update updated_at timestamp
                cursor.execute("""
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql';

                    CREATE TRIGGER update_players_updated_at
                        BEFORE UPDATE ON players
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column();
                """)

                conn.commit()
                logging.info("✅ PostgreSQL database tables created successfully")

        except Exception as e:
            logging.error(f"❌ Error initializing PostgreSQL database: {e}")
            raise

    def _validate_guild_id(self, guild_id: int, operation_name: str = "database operation") -> None:
        """Validate guild_id to prevent cross-guild data contamination."""
        if guild_id <= 0:
            error_msg = f"Invalid guild_id={guild_id} for {operation_name}. Guild ID must be positive."
            logging.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

    def get_database_info(self, guild_id: int = 0) -> Dict:
        """Get database information."""
        try:
            info = {
                'database_type': 'PostgreSQL',
                'connection_host': self.connection_params.get('host'),
                'connection_database': self.connection_params.get('database'),
                'roster_count': 0,
                'war_count': 0
            }

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM players WHERE guild_id = %s AND is_active = TRUE", (guild_id,))
                info['roster_count'] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM wars WHERE guild_id = %s", (guild_id,))
                info['war_count'] = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                """)
                info['database_size'] = cursor.fetchone()[0]

            return info

        except Exception as e:
            logging.error(f"❌ Error getting database info: {e}")
            return {'error': str(e)}

    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return cursor.fetchone()[0] == 1
        except Exception as e:
            logging.error(f"❌ PostgreSQL health check failed: {e}")
            return False

    @staticmethod
    def get_bot_owner_id() -> int:
        """Get the master admin bot owner ID."""
        return BOT_OWNER_ID

    @staticmethod
    def is_bot_owner(user_id: int) -> bool:
        """Check if a user ID is the bot owner."""
        return user_id == BOT_OWNER_ID

    def close(self):
        """Close all connections in the pool."""
        if hasattr(self, 'connection_pool'):
            self.connection_pool.closeall()
            logging.info("✅ PostgreSQL connection pool closed")


# Test the implementation
if __name__ == "__main__":
    print("🧪 Testing PostgreSQL DatabaseManager...")

    # Test with local PostgreSQL
    db = DatabaseManager()

    # Test health check
    if db.health_check():
        print("✅ PostgreSQL connection successful")

        # Use test guild_id (guild_id must be > 0 for validation)
        test_guild_id = 12345

        # Test adding roster players
        db.add_roster_player("TestPlayer", added_by="system", guild_id=test_guild_id)

        # Test adding war results
        test_results = [
            {'name': 'TestPlayer', 'score': 95},
            {'name': 'Player2', 'score': 88}
        ]

        success = db.add_race_results(test_results, guild_id=test_guild_id)
        print(f"✅ War results added: {success}")

        # Test queries
        roster = db.get_roster_players(test_guild_id)
        print(f"✅ Roster players: {roster}")

        # Test database info
        info = db.get_database_info()
        print(f"✅ Database info: {info}")

        # Initialize with test player
        db.add_roster_player("TestPlayer", added_by="system", guild_id=test_guild_id)
        print(f"✅ Added TestPlayer to roster")

        db.close()

    else:
        print("❌ PostgreSQL connection failed")
