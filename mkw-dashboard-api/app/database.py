"""
PostgreSQL database manager for MKW Dashboard API.
Adapted from mkw_stats_bot/mkw_stats/database.py to share the same database.
"""
import psycopg2
import psycopg2.pool
import json
import logging
import uuid
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager for the Dashboard API."""

    def __init__(self, database_url: str = None):
        """Initialize PostgreSQL database connection."""
        self.database_url = database_url or settings.database_url

        if not self.database_url:
            raise ValueError("DATABASE_URL is required")

        self.connection_params = self._parse_database_url(self.database_url)

        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 10,
                **self.connection_params
            )
            logger.info("PostgreSQL connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL connection pool: {e}")
            raise

        # Initialize dashboard-specific tables
        self._init_dashboard_tables()

    def _parse_database_url(self, url: str) -> Dict:
        """Parse DATABASE_URL into connection parameters."""
        parsed = urlparse(url)
        params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],
            'user': parsed.username,
        }
        if parsed.password:
            params['password'] = parsed.password
        return params

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool."""
        conn = None
        try:
            conn = self.connection_pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def _init_dashboard_tables(self):
        """Initialize dashboard-specific tables if they don't exist."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if bulk_scan_sessions table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'bulk_scan_sessions'
                    );
                """)

                if not cursor.fetchone()[0]:
                    logger.info("Creating dashboard tables...")

                    # Create bulk_scan_sessions table
                    cursor.execute("""
                        CREATE TABLE bulk_scan_sessions (
                            id SERIAL PRIMARY KEY,
                            token UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                            guild_id BIGINT NOT NULL,
                            created_by_user_id BIGINT NOT NULL,
                            status VARCHAR(20) DEFAULT 'pending',
                            total_images INTEGER DEFAULT 0,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'),
                            completed_at TIMESTAMP WITH TIME ZONE
                        );
                        CREATE INDEX idx_bulk_sessions_token ON bulk_scan_sessions(token);
                        CREATE INDEX idx_bulk_sessions_guild ON bulk_scan_sessions(guild_id);
                        CREATE INDEX idx_bulk_sessions_status ON bulk_scan_sessions(status);
                    """)

                    # Create bulk_scan_results table
                    cursor.execute("""
                        CREATE TABLE bulk_scan_results (
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
                        );
                        CREATE INDEX idx_bulk_results_session ON bulk_scan_results(session_id);
                        CREATE INDEX idx_bulk_results_status ON bulk_scan_results(review_status);
                    """)

                    # Create bulk_scan_failures table for failed images
                    cursor.execute("""
                        CREATE TABLE bulk_scan_failures (
                            id SERIAL PRIMARY KEY,
                            session_id INTEGER REFERENCES bulk_scan_sessions(id) ON DELETE CASCADE,
                            image_filename VARCHAR(255),
                            image_url TEXT,
                            error_message TEXT,
                            message_timestamp TIMESTAMP WITH TIME ZONE,
                            discord_message_id BIGINT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX idx_bulk_failures_session ON bulk_scan_failures(session_id);
                    """)

                    # Create user_sessions table
                    cursor.execute("""
                        CREATE TABLE user_sessions (
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
                        );
                        CREATE INDEX idx_user_sessions_discord_id ON user_sessions(discord_user_id);
                        CREATE INDEX idx_user_sessions_token ON user_sessions(session_token);
                    """)

                    conn.commit()
                    logger.info("Dashboard tables created successfully")
                else:
                    logger.info("Dashboard tables already exist")

        except Exception as e:
            logger.error(f"Error initializing dashboard tables: {e}")
            raise

    # ==================== PLAYER METHODS ====================

    def get_roster_players(self, guild_id: int) -> List[Dict]:
        """Get all active players for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT player_name, team, nicknames, member_status,
                           total_score, total_races, war_count, average_score,
                           last_war_date, is_active, created_at
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE
                    ORDER BY player_name
                """, (guild_id,))

                players = []
                for row in cursor.fetchall():
                    players.append({
                        'name': row[0],
                        'team': row[1],
                        'nicknames': row[2] or [],
                        'member_status': row[3] or 'member',
                        'total_score': row[4] or 0,
                        'total_races': row[5] or 0,
                        'war_count': float(row[6]) if row[6] else 0,
                        'average_score': float(row[7]) if row[7] else 0,
                        'last_war_date': row[8].isoformat() if row[8] else None,
                        'is_active': row[9],
                        'created_at': row[10].isoformat() if row[10] else None
                    })
                return players
        except Exception as e:
            logger.error(f"Error getting roster players: {e}")
            return []

    def get_all_guild_players(self, guild_id: int) -> List[Dict]:
        """Get ALL players for a guild (active and inactive)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT player_name, team, nicknames, member_status,
                           total_score, total_races, war_count, average_score,
                           last_war_date, is_active, created_at
                    FROM players
                    WHERE guild_id = %s
                    ORDER BY player_name
                """, (guild_id,))

                players = []
                for row in cursor.fetchall():
                    players.append({
                        'name': row[0],
                        'team': row[1],
                        'nicknames': row[2] or [],
                        'member_status': row[3] or 'member',
                        'total_score': row[4] or 0,
                        'total_races': row[5] or 0,
                        'war_count': float(row[6]) if row[6] else 0,
                        'average_score': float(row[7]) if row[7] else 0,
                        'last_war_date': row[8].isoformat() if row[8] else None,
                        'is_active': row[9],
                        'created_at': row[10].isoformat() if row[10] else None
                    })
                return players
        except Exception as e:
            logger.error(f"Error getting all guild players: {e}")
            return []

    def get_player_stats(self, player_name: str, guild_id: int) -> Optional[Dict]:
        """Get detailed stats for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT player_name, team, nicknames, member_status,
                           total_score, total_races, war_count, average_score,
                           last_war_date, total_team_differential, is_active
                    FROM players
                    WHERE guild_id = %s AND LOWER(player_name) = LOWER(%s)
                """, (guild_id, player_name))

                row = cursor.fetchone()
                if not row:
                    return None

                return {
                    'name': row[0],
                    'team': row[1],
                    'nicknames': row[2] or [],
                    'member_status': row[3] or 'member',
                    'total_score': row[4] or 0,
                    'total_races': row[5] or 0,
                    'war_count': float(row[6]) if row[6] else 0,
                    'average_score': float(row[7]) if row[7] else 0,
                    'last_war_date': row[8].isoformat() if row[8] else None,
                    'total_team_differential': row[9] or 0,
                    'is_active': row[10]
                }
        except Exception as e:
            logger.error(f"Error getting player stats: {e}")
            return None

    def add_player(self, player_name: str, guild_id: int,
                   member_status: str = 'member', added_by: str = None) -> bool:
        """Add a new player to the roster."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if player exists (might be inactive)
                cursor.execute("""
                    SELECT id, is_active FROM players
                    WHERE guild_id = %s AND LOWER(player_name) = LOWER(%s)
                """, (guild_id, player_name))

                existing = cursor.fetchone()
                if existing:
                    if existing[1]:  # Already active
                        return False
                    # Reactivate
                    cursor.execute("""
                        UPDATE players SET is_active = TRUE, member_status = %s
                        WHERE id = %s
                    """, (member_status, existing[0]))
                else:
                    cursor.execute("""
                        INSERT INTO players (player_name, guild_id, member_status, added_by)
                        VALUES (%s, %s, %s, %s)
                    """, (player_name, guild_id, member_status, added_by))

                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding player: {e}")
            return False

    def update_player_status(self, player_name: str, guild_id: int,
                             member_status: str) -> bool:
        """Update a player's member status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE players SET member_status = %s
                    WHERE guild_id = %s AND LOWER(player_name) = LOWER(%s)
                """, (member_status, guild_id, player_name))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating player status: {e}")
            return False

    def add_nickname(self, player_name: str, guild_id: int, nickname: str) -> bool:
        """Add a nickname to a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get current nicknames
                cursor.execute("""
                    SELECT nicknames FROM players
                    WHERE guild_id = %s AND LOWER(player_name) = LOWER(%s)
                """, (guild_id, player_name))

                row = cursor.fetchone()
                if not row:
                    return False

                nicknames = row[0] or []
                if nickname not in nicknames:
                    nicknames.append(nickname)

                cursor.execute("""
                    UPDATE players SET nicknames = %s
                    WHERE guild_id = %s AND LOWER(player_name) = LOWER(%s)
                """, (json.dumps(nicknames), guild_id, player_name))

                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding nickname: {e}")
            return False

    # ==================== WAR METHODS ====================

    def get_wars(self, guild_id: int, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Get wars for a guild with pagination."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, war_date, race_count, players_data,
                           team_score, team_differential, created_at
                    FROM wars
                    WHERE guild_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (guild_id, limit, offset))

                wars = []
                for row in cursor.fetchall():
                    players_data = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
                    wars.append({
                        'id': row[0],
                        'war_date': row[1].isoformat() if row[1] else None,
                        'race_count': row[2],
                        'players': players_data.get('results', []),
                        'team_score': row[4],
                        'team_differential': row[5],
                        'created_at': row[6].isoformat() if row[6] else None
                    })
                return wars
        except Exception as e:
            logger.error(f"Error getting wars: {e}")
            return []

    def get_war_count(self, guild_id: int) -> int:
        """Get total war count for pagination."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM wars WHERE guild_id = %s",
                    (guild_id,)
                )
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting war count: {e}")
            return 0

    def add_war(self, guild_id: int, results: List[Dict], race_count: int = 12) -> Optional[int]:
        """Add a new war to the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Calculate team score
                team_score = sum(r.get('score', 0) for r in results)
                breakeven = 41 * race_count  # 41 points per race is breakeven
                team_differential = team_score - breakeven

                # Create players_data JSON
                players_data = {
                    'results': results,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'race_count': race_count
                }

                cursor.execute("""
                    INSERT INTO wars (war_date, race_count, players_data, guild_id,
                                     team_score, team_differential)
                    VALUES (CURRENT_DATE, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (race_count, json.dumps(players_data), guild_id,
                      team_score, team_differential))

                war_id = cursor.fetchone()[0]
                conn.commit()

                logger.info(f"Created war {war_id} for guild {guild_id}")
                return war_id
        except Exception as e:
            logger.error(f"Error adding war: {e}")
            return None

    def update_player_stats(self, player_name: str, score: int, races_played: int,
                            war_participation: float, war_date: str, guild_id: int,
                            team_differential: int = 0) -> bool:
        """Update player statistics when a war is added with fractional war support."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if player exists and get current stats
                cursor.execute("""
                    SELECT total_score, total_races, war_count, total_team_differential
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if result:
                    # Player has existing stats - UPDATE
                    new_total_score = result[0] + score
                    new_total_races = result[1] + races_played
                    new_war_count = float(result[2]) + war_participation  # Support fractional wars
                    new_total_differential = (result[3] or 0) + team_differential
                    # Correct average calculation: total_score / war_count
                    new_average = round(new_total_score / new_war_count, 2) if new_war_count > 0 else 0

                    cursor.execute("""
                        UPDATE players
                        SET total_score = %s, total_races = %s, war_count = %s,
                            average_score = %s, last_war_date = %s, total_team_differential = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE player_name = %s AND guild_id = %s
                    """, (new_total_score, new_total_races, new_war_count, new_average,
                          war_date, new_total_differential, player_name, guild_id))
                    conn.commit()
                    logger.info(f"Updated stats for {player_name}: +{score} points, +{races_played} races")
                    return True
                else:
                    # Player doesn't exist - log error
                    logger.error(f"Player {player_name} not found in players table for guild {guild_id}")
                    return False

        except Exception as e:
            logger.error(f"Error updating player stats: {e}")
            return False

    def add_player_war_performance(self, player_name: str, war_id: int, score: int,
                                   races_played: int, race_count: int, guild_id: int) -> bool:
        """Add a player's war performance record."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get player_id
                cursor.execute("""
                    SELECT id FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                player_row = cursor.fetchone()
                if player_row:
                    player_id = player_row[0]
                    war_participation = races_played / race_count if race_count > 0 else 1.0

                    cursor.execute("""
                        INSERT INTO player_war_performances
                        (player_id, war_id, score, races_played, war_participation)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (player_id, war_id) DO NOTHING
                    """, (player_id, war_id, score, races_played, war_participation))
                    conn.commit()
                    return True
                else:
                    logger.warning(f"Player {player_name} not found for war performance insert")
                    return False

        except Exception as e:
            logger.error(f"Error adding player war performance: {e}")
            return False

    # ==================== STATS METHODS ====================

    def get_leaderboard(self, guild_id: int, sort_by: str = 'average_score',
                        limit: int = 50) -> List[Dict]:
        """Get leaderboard sorted by specified field."""
        valid_sorts = ['average_score', 'total_score', 'war_count', 'total_team_differential']
        if sort_by not in valid_sorts:
            sort_by = 'average_score'

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT player_name, team, member_status,
                           total_score, war_count, average_score,
                           total_team_differential, last_war_date
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE AND war_count > 0
                    ORDER BY {sort_by} DESC
                    LIMIT %s
                """, (guild_id, limit))

                leaderboard = []
                for i, row in enumerate(cursor.fetchall(), 1):
                    leaderboard.append({
                        'rank': i,
                        'name': row[0],
                        'team': row[1],
                        'member_status': row[2],
                        'total_score': row[3] or 0,
                        'war_count': float(row[4]) if row[4] else 0,
                        'average_score': float(row[5]) if row[5] else 0,
                        'total_team_differential': row[6] or 0,
                        'last_war_date': row[7].isoformat() if row[7] else None
                    })
                return leaderboard
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []

    def get_guild_overview(self, guild_id: int) -> Dict:
        """Get guild statistics overview."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get player counts by status
                cursor.execute("""
                    SELECT member_status, COUNT(*)
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE
                    GROUP BY member_status
                """, (guild_id,))
                status_counts = dict(cursor.fetchall())

                # Get total wars
                cursor.execute(
                    "SELECT COUNT(*) FROM wars WHERE guild_id = %s",
                    (guild_id,)
                )
                total_wars = cursor.fetchone()[0]

                # Get average team differential
                cursor.execute("""
                    SELECT AVG(team_differential), SUM(CASE WHEN team_differential > 0 THEN 1 ELSE 0 END),
                           SUM(CASE WHEN team_differential < 0 THEN 1 ELSE 0 END)
                    FROM wars WHERE guild_id = %s
                """, (guild_id,))
                diff_stats = cursor.fetchone()

                return {
                    'total_players': sum(status_counts.values()),
                    'member_counts': status_counts,
                    'total_wars': total_wars,
                    'average_differential': float(diff_stats[0]) if diff_stats[0] else 0,
                    'wins': diff_stats[1] or 0,
                    'losses': diff_stats[2] or 0
                }
        except Exception as e:
            logger.error(f"Error getting guild overview: {e}")
            return {}

    # ==================== BULK SCAN SESSION METHODS ====================

    def create_bulk_session(self, guild_id: int, user_id: int,
                            results: List[Dict], failed_results: List[Dict] = None) -> Optional[Dict]:
        """Create a new bulk scan session with results and optional failed results."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Create session
                cursor.execute("""
                    INSERT INTO bulk_scan_sessions (guild_id, created_by_user_id, total_images, status)
                    VALUES (%s, %s, %s, 'pending')
                    RETURNING id, token
                """, (guild_id, user_id, len(results)))

                session_id, token = cursor.fetchone()

                # Insert results
                for result in results:
                    cursor.execute("""
                        INSERT INTO bulk_scan_results
                        (session_id, image_filename, image_url, detected_players,
                         race_count, message_timestamp, discord_message_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        session_id,
                        result.get('filename'),
                        result.get('image_url'),
                        json.dumps(result.get('players', [])),
                        result.get('race_count', 12),
                        result.get('message_timestamp'),
                        result.get('discord_message_id')
                    ))

                # Insert failed results if provided
                if failed_results:
                    for failed in failed_results:
                        cursor.execute("""
                            INSERT INTO bulk_scan_failures
                            (session_id, image_filename, image_url, error_message,
                             message_timestamp, discord_message_id)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            session_id,
                            failed.get('filename'),
                            failed.get('image_url'),
                            failed.get('error_message'),
                            failed.get('message_timestamp'),
                            failed.get('discord_message_id')
                        ))

                conn.commit()
                logger.info(f"Created bulk session {token} with {len(results)} results and {len(failed_results) if failed_results else 0} failures")

                return {
                    'id': session_id,
                    'token': str(token),
                    'total_images': len(results)
                }
        except Exception as e:
            logger.error(f"Error creating bulk session: {e}")
            return None

    def get_bulk_session(self, token: str) -> Optional[Dict]:
        """Get a bulk scan session by token."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, guild_id, created_by_user_id, status,
                           total_images, created_at, expires_at
                    FROM bulk_scan_sessions
                    WHERE token = %s
                """, (token,))

                row = cursor.fetchone()
                if not row:
                    return None

                # Check if expired
                if row[6] and row[6] < datetime.now(timezone.utc):
                    return {'error': 'Session expired'}

                return {
                    'id': row[0],
                    'guild_id': str(row[1]),  # Convert to string to avoid JS precision loss
                    'created_by_user_id': row[2],
                    'status': row[3],
                    'total_images': row[4],
                    'created_at': row[5].isoformat() if row[5] else None,
                    'expires_at': row[6].isoformat() if row[6] else None
                }
        except Exception as e:
            logger.error(f"Error getting bulk session: {e}")
            return None

    def get_bulk_results(self, token: str) -> List[Dict]:
        """Get all results for a bulk scan session."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get session ID
                cursor.execute(
                    "SELECT id FROM bulk_scan_sessions WHERE token = %s",
                    (token,)
                )
                session_row = cursor.fetchone()
                if not session_row:
                    return []

                cursor.execute("""
                    SELECT id, image_filename, image_url, detected_players,
                           review_status, corrected_players, race_count,
                           message_timestamp, created_at
                    FROM bulk_scan_results
                    WHERE session_id = %s
                    ORDER BY message_timestamp ASC, created_at ASC
                """, (session_row[0],))

                results = []
                for row in cursor.fetchall():
                    detected = row[3] if isinstance(row[3], list) else json.loads(row[3]) if row[3] else []
                    corrected = row[5] if isinstance(row[5], list) else json.loads(row[5]) if row[5] else None

                    results.append({
                        'id': row[0],
                        'image_filename': row[1],
                        'image_url': row[2],
                        'detected_players': detected,
                        'review_status': row[4],
                        'corrected_players': corrected,
                        'race_count': row[6],
                        'message_timestamp': row[7].isoformat() if row[7] else None,
                        'created_at': row[8].isoformat() if row[8] else None
                    })
                return results
        except Exception as e:
            logger.error(f"Error getting bulk results: {e}")
            return []

    def get_bulk_failures(self, token: str) -> List[Dict]:
        """Get all failed images for a bulk scan session."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get session ID
                cursor.execute(
                    "SELECT id FROM bulk_scan_sessions WHERE token = %s",
                    (token,)
                )
                session_row = cursor.fetchone()
                if not session_row:
                    return []

                cursor.execute("""
                    SELECT id, image_filename, image_url, error_message,
                           message_timestamp, discord_message_id, created_at
                    FROM bulk_scan_failures
                    WHERE session_id = %s
                    ORDER BY message_timestamp ASC, created_at ASC
                """, (session_row[0],))

                failures = []
                for row in cursor.fetchall():
                    failures.append({
                        'id': row[0],
                        'image_filename': row[1],
                        'image_url': row[2],
                        'error_message': row[3],
                        'message_timestamp': row[4].isoformat() if row[4] else None,
                        'discord_message_id': row[5],
                        'created_at': row[6].isoformat() if row[6] else None
                    })
                return failures
        except Exception as e:
            logger.error(f"Error getting bulk failures: {e}")
            return []

    def convert_failure_to_result(self, failure_id: int, players: List[Dict], review_status: str = 'pending') -> Optional[Dict]:
        """Convert a failure to a result with manually entered players."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get failure details
                cursor.execute("""
                    SELECT session_id, image_filename, image_url, message_timestamp, discord_message_id
                    FROM bulk_scan_failures WHERE id = %s
                """, (failure_id,))
                failure = cursor.fetchone()
                if not failure:
                    return None

                session_id, filename, image_url, msg_ts, discord_msg_id = failure

                # Create new result from failure data
                cursor.execute("""
                    INSERT INTO bulk_scan_results
                    (session_id, image_filename, image_url, detected_players, review_status,
                     corrected_players, race_count, message_timestamp, discord_message_id)
                    VALUES (%s, %s, %s, %s, %s, %s, 12, %s, %s)
                    RETURNING id
                """, (
                    session_id, filename, image_url,
                    json.dumps(players),
                    review_status,
                    json.dumps(players),
                    msg_ts, discord_msg_id
                ))
                result_id = cursor.fetchone()[0]

                # Delete the failure
                cursor.execute("DELETE FROM bulk_scan_failures WHERE id = %s", (failure_id,))

                conn.commit()

                return {
                    'id': result_id,
                    'image_filename': filename,
                    'image_url': image_url,
                    'detected_players': players,
                    'review_status': review_status,
                    'corrected_players': players,
                    'race_count': 12,
                    'message_timestamp': msg_ts.isoformat() if msg_ts else None
                }
        except Exception as e:
            logger.error(f"Error converting failure to result: {e}")
            return None

    def update_bulk_result(self, result_id: int, review_status: str,
                           corrected_players: List[Dict] = None) -> bool:
        """Update a single bulk scan result."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bulk_scan_results
                    SET review_status = %s, corrected_players = %s,
                        reviewed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    review_status,
                    json.dumps(corrected_players) if corrected_players else None,
                    result_id
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating bulk result: {e}")
            return False

    def complete_bulk_session(self, token: str) -> bool:
        """Mark a bulk session as completed."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bulk_scan_sessions
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE token = %s
                """, (token,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error completing bulk session: {e}")
            return False

    # ==================== USER SESSION METHODS ====================

    def create_user_session(self, discord_user_id: int, discord_username: str,
                            discord_avatar: str = None,
                            guild_permissions: Dict = None) -> Optional[str]:
        """Create a new user session and return the token."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Delete any existing sessions for this user
                cursor.execute(
                    "DELETE FROM user_sessions WHERE discord_user_id = %s",
                    (discord_user_id,)
                )

                cursor.execute("""
                    INSERT INTO user_sessions
                    (discord_user_id, discord_username, discord_avatar, guild_permissions)
                    VALUES (%s, %s, %s, %s)
                    RETURNING session_token
                """, (
                    discord_user_id,
                    discord_username,
                    discord_avatar,
                    json.dumps(guild_permissions or {})
                ))

                token = cursor.fetchone()[0]
                conn.commit()
                return str(token)
        except Exception as e:
            logger.error(f"Error creating user session: {e}")
            return None

    def get_user_session(self, session_token: str) -> Optional[Dict]:
        """Get user session by token."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT discord_user_id, discord_username, discord_avatar,
                           guild_permissions, created_at, expires_at
                    FROM user_sessions
                    WHERE session_token = %s
                """, (session_token,))

                row = cursor.fetchone()
                if not row:
                    return None

                # Check if expired
                if row[5] and row[5] < datetime.now(timezone.utc):
                    return None

                # Update last active
                cursor.execute("""
                    UPDATE user_sessions SET last_active_at = CURRENT_TIMESTAMP
                    WHERE session_token = %s
                """, (session_token,))
                conn.commit()

                permissions = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}

                return {
                    'discord_user_id': row[0],
                    'discord_username': row[1],
                    'discord_avatar': row[2],
                    'guild_permissions': permissions,
                    'created_at': row[4].isoformat() if row[4] else None,
                    'expires_at': row[5].isoformat() if row[5] else None
                }
        except Exception as e:
            logger.error(f"Error getting user session: {e}")
            return None

    def delete_user_session(self, session_token: str) -> bool:
        """Delete a user session (logout)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM user_sessions WHERE session_token = %s",
                    (session_token,)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting user session: {e}")
            return False

    # ==================== GUILD CONFIG METHODS ====================

    def get_guild_config(self, guild_id: int) -> Optional[Dict]:
        """Get guild configuration."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT guild_name, team_names, ocr_channel_id, is_active
                    FROM guild_configs
                    WHERE guild_id = %s
                """, (guild_id,))

                row = cursor.fetchone()
                if not row:
                    return None

                team_names = row[1] if isinstance(row[1], list) else json.loads(row[1]) if row[1] else []

                return {
                    'guild_id': guild_id,
                    'guild_name': row[0],
                    'team_names': team_names,
                    'ocr_channel_id': row[2],
                    'is_active': row[3]
                }
        except Exception as e:
            logger.error(f"Error getting guild config: {e}")
            return None

    def get_teams(self, guild_id: int) -> List[str]:
        """Get team names for a guild."""
        config = self.get_guild_config(guild_id)
        if config:
            return config.get('team_names', [])
        return []
