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

import logging
import os
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

import psycopg2
import psycopg2.errors
import psycopg2.pool

from .constants import (
    BOT_OWNER_ID,
    DB_CONNECT_TIMEOUT,
    DB_POOL_MAX,
    DB_POOL_MIN,
    DB_STATEMENT_TIMEOUT,
)
from .repositories import (
    GuildRepository,
    PlayerRepository,
    StatsRepository,
    WarRepository,
)


class DatabaseManager:
    """Facade over domain-specific repositories.

    Provides backward-compatible method access (db.resolve_player_name())
    while organizing logic into focused repositories (db.players, db.wars, etc.).
    """

    def __init__(self, database_url: str | None = None):
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

    def _parse_database_url(self, url: str) -> dict[str, Any]:
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
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def init_database(self):
        """Initialize the database tables if they don't exist.

        Uses CREATE TABLE IF NOT EXISTS throughout so this method is safe to
        call on a fully-initialized database (no-op) and on partially-initialized
        databases (only missing tables are created).
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # wars
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS wars (
                        id SERIAL PRIMARY KEY,
                        war_date DATE NOT NULL,
                        race_count INTEGER NOT NULL,
                        players_data JSONB NOT NULL,
                        guild_id BIGINT NOT NULL,
                        team_score INTEGER DEFAULT 0,
                        team_differential INTEGER DEFAULT 0,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_wars_guild_id ON wars(guild_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_wars_date ON wars(war_date DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_wars_created ON wars(created_at DESC)")

                # players
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS players (
                        id SERIAL PRIMARY KEY,
                        player_name VARCHAR(100) NOT NULL,
                        guild_id BIGINT NOT NULL,
                        team VARCHAR(50) DEFAULT 'Unassigned',
                        nicknames JSONB DEFAULT '[]',
                        added_by VARCHAR(100),
                        is_active BOOLEAN DEFAULT TRUE,
                        total_score INTEGER DEFAULT 0,
                        total_races INTEGER DEFAULT 0,
                        war_count DECIMAL(8,3) DEFAULT 0,
                        average_score DECIMAL(5,2) DEFAULT 0.0,
                        last_war_date DATE,
                        discord_user_id BIGINT,
                        discord_username VARCHAR(100),
                        display_name VARCHAR(100),
                        member_status VARCHAR(20) DEFAULT 'member',
                        country_code CHAR(2),
                        last_role_sync TIMESTAMP WITH TIME ZONE,
                        total_team_differential INTEGER DEFAULT 0,
                        -- Stable cached metrics (recalculated on every war add/remove)
                        score_stddev DECIMAL(6,2) DEFAULT 0.0,
                        consistency_score DECIMAL(5,2),
                        highest_score INTEGER DEFAULT 0,
                        lowest_score INTEGER DEFAULT 0,
                        wins INTEGER DEFAULT 0,
                        losses INTEGER DEFAULT 0,
                        ties INTEGER DEFAULT 0,
                        win_percentage DECIMAL(5,2) DEFAULT 0.0,
                        -- Volatile cached metrics (invalidated on war add/remove, recalculated lazily)
                        avg10_score DECIMAL(5,2),
                        form_score DECIMAL(5,2),
                        clutch_factor DECIMAL(5,2),
                        potential DECIMAL(5,2),
                        hotstreak DECIMAL(5,2),
                        cached_metrics_updated_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(player_name, guild_id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_guild_id ON players(guild_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_active ON players(is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_name ON players(player_name)")

                # Ensure all columns exist on players (handles pre-existing tables missing migrated columns)
                for col_sql in [
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_user_id BIGINT",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_username VARCHAR(100)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS display_name VARCHAR(100)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS member_status VARCHAR(20) DEFAULT 'member'",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS country_code CHAR(2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_role_sync TIMESTAMP WITH TIME ZONE",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS war_count DECIMAL(8,3) DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS average_score DECIMAL(5,2) DEFAULT 0.0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_war_date DATE",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS total_score INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS total_races INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS team VARCHAR(50) DEFAULT 'Unassigned'",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS nicknames JSONB DEFAULT '[]'",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS total_team_differential INTEGER DEFAULT 0",
                    # Stable cached metrics
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS score_stddev DECIMAL(6,2) DEFAULT 0.0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS consistency_score DECIMAL(5,2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS highest_score INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS lowest_score INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS wins INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS losses INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS ties INTEGER DEFAULT 0",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS win_percentage DECIMAL(5,2) DEFAULT 0.0",
                    # Volatile cached metrics
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS avg10_score DECIMAL(5,2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS form_score DECIMAL(5,2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS clutch_factor DECIMAL(5,2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS potential DECIMAL(5,2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS hotstreak DECIMAL(5,2)",
                    "ALTER TABLE players ADD COLUMN IF NOT EXISTS cached_metrics_updated_at TIMESTAMP WITH TIME ZONE",
                ]:
                    cursor.execute(col_sql)

                # Ensure all columns exist on wars
                for col_sql in [
                    "ALTER TABLE wars ADD COLUMN IF NOT EXISTS team_score INTEGER DEFAULT 0",
                    "ALTER TABLE wars ADD COLUMN IF NOT EXISTS team_differential INTEGER DEFAULT 0",
                ]:
                    cursor.execute(col_sql)

                # guild_configs
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guild_configs (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT UNIQUE NOT NULL,
                        guild_name VARCHAR(255),
                        team_names JSONB DEFAULT '[]',
                        ocr_channel_id BIGINT,
                        is_active BOOLEAN DEFAULT TRUE,
                        role_member_id BIGINT,
                        role_trial_id BIGINT,
                        role_ally_id BIGINT,
                        team_tags JSONB DEFAULT '{}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_guild_configs_guild_id ON guild_configs(guild_id)")

                # Ensure all columns exist on guild_configs (handles pre-existing tables missing migrated columns)
                for col_sql in [
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS guild_name VARCHAR(255)",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS team_names JSONB DEFAULT '[]'",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS ocr_channel_id BIGINT",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS role_member_id BIGINT",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS role_trial_id BIGINT",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS role_ally_id BIGINT",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS team_tags JSONB DEFAULT '{}'",
                    "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
                ]:
                    cursor.execute(col_sql)

                # player_war_performances
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS player_war_performances (
                        id SERIAL PRIMARY KEY,
                        player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                        war_id INTEGER NOT NULL REFERENCES wars(id) ON DELETE CASCADE,
                        score INTEGER NOT NULL,
                        races_played INTEGER NOT NULL,
                        war_participation DECIMAL(4,3) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(player_id, war_id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_performances ON player_war_performances(player_id, war_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_war_performances ON player_war_performances(war_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_created ON player_war_performances(player_id, created_at DESC)")

                # bulk_scan_sessions (dashboard)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bulk_scan_sessions (
                        id SERIAL PRIMARY KEY,
                        token UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                        guild_id BIGINT NOT NULL,
                        created_by_user_id BIGINT NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        total_images INTEGER DEFAULT 0,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'),
                        completed_at TIMESTAMP WITH TIME ZONE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulk_sessions_token ON bulk_scan_sessions(token)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulk_sessions_guild ON bulk_scan_sessions(guild_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulk_sessions_status ON bulk_scan_sessions(status)")

                # bulk_scan_results (dashboard)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bulk_scan_results (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES bulk_scan_sessions(id) ON DELETE CASCADE,
                        image_filename VARCHAR(255),
                        image_url TEXT,
                        detected_players JSONB NOT NULL,
                        review_status VARCHAR(20) DEFAULT 'pending',
                        corrected_players JSONB,
                        race_count INTEGER DEFAULT 12,
                        message_timestamp TIMESTAMP WITH TIME ZONE,
                        discord_message_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        reviewed_at TIMESTAMP WITH TIME ZONE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulk_results_session ON bulk_scan_results(session_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulk_results_status ON bulk_scan_results(review_status)")

                # bulk_scan_failures (dashboard)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bulk_scan_failures (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES bulk_scan_sessions(id) ON DELETE CASCADE,
                        image_filename VARCHAR(255),
                        image_url TEXT,
                        error_message TEXT,
                        message_timestamp TIMESTAMP WITH TIME ZONE,
                        discord_message_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulk_failures_session ON bulk_scan_failures(session_id)")

                # user_sessions (dashboard OAuth)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id SERIAL PRIMARY KEY,
                        discord_user_id BIGINT NOT NULL,
                        discord_username VARCHAR(100),
                        discord_avatar VARCHAR(255),
                        session_token UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                        access_token_encrypted TEXT,
                        refresh_token_encrypted TEXT,
                        guild_permissions JSONB DEFAULT '{}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '7 days'),
                        last_active_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_discord_id ON user_sessions(discord_user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)")

                # updated_at trigger (players)
                cursor.execute("""
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql'
                """)
                cursor.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'update_players_updated_at'
                        ) THEN
                            CREATE TRIGGER update_players_updated_at
                                BEFORE UPDATE ON players
                                FOR EACH ROW
                                EXECUTE FUNCTION update_updated_at_column();
                        END IF;
                    END $$
                """)

                conn.commit()
                logging.info("✅ PostgreSQL database tables initialized successfully")

        except Exception as e:
            logging.error(f"❌ Error initializing PostgreSQL database: {e}")
            raise

    def _validate_guild_id(self, guild_id: int, operation_name: str = "database operation") -> None:
        """Validate guild_id to prevent cross-guild data contamination."""
        if guild_id <= 0:
            error_msg = f"Invalid guild_id={guild_id} for {operation_name}. Guild ID must be positive."
            logging.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

    def get_database_info(self, guild_id: int = 0) -> dict:
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
        print("✅ Added TestPlayer to roster")

        db.close()

    else:
        print("❌ PostgreSQL connection failed")
