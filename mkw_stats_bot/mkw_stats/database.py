#!/usr/bin/env python3
"""
PostgreSQL database system for Mario Kart clan stats.
Each player has:
- Main name
- List of nicknames 
- Score history (list of individual race scores)
- War count (calculated from scores)
- Average score per war

Production-ready with Railway PostgreSQL deployment.
"""

import psycopg2
import psycopg2.pool
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
import os
from contextlib import contextmanager
from urllib.parse import urlparse

class DatabaseManager:
    def __init__(self, database_url: str = None):
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
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 10,  # min=1, max=10 connections
                **self.connection_params
            )
            logging.info("✅ PostgreSQL connection pool created successfully")
        except Exception as e:
            logging.error(f"❌ Failed to create PostgreSQL connection pool: {e}")
            raise
        
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
    
    def _parse_database_url(self, url: str) -> Dict:
        """Parse DATABASE_URL into connection parameters."""
        parsed = urlparse(url)
        params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading slash
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
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for wars
                cursor.execute("""
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
                        war_count INTEGER DEFAULT 0,
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
    
    def set_ocr_channel(self, guild_id: int, channel_id: int) -> bool:
        """Set the OCR channel for automatic image processing in a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Update or insert guild config with OCR channel
                cursor.execute("""
                    INSERT INTO guild_configs (guild_id, ocr_channel_id, is_active)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        ocr_channel_id = EXCLUDED.ocr_channel_id,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, channel_id))
                
                conn.commit()
                logging.info(f"✅ Set OCR channel {channel_id} for guild {guild_id}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error setting OCR channel: {e}")
            return False
    
    def get_ocr_channel(self, guild_id: int) -> Optional[int]:
        """Get the OCR channel ID for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT ocr_channel_id 
                    FROM guild_configs 
                    WHERE guild_id = %s AND is_active = TRUE
                """, (guild_id,))
                
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
                
        except Exception as e:
            logging.error(f"❌ Error getting OCR channel: {e}")
            return None
    
    def resolve_player_name(self, name_or_nickname: str, guild_id: int = 0, log_level: str = 'error') -> Optional[str]:
        """Resolve a name or nickname to players table player name.
        
        Args:
            name_or_nickname: The name or nickname to resolve
            guild_id: Guild ID for data isolation
            log_level: Logging level for database errors ('error', 'debug', 'none')
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Enhanced debug logging
                if log_level == 'debug':
                    logging.debug(f"🔍 [RESOLVE] Starting resolution for: '{name_or_nickname}' (guild_id: {guild_id})")
                
                # Strategwait y 1: Exact match with player_name
                strategy1_query = """
                    SELECT player_name FROM players 
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY1] Exact player_name match: {strategy1_query}")
                    logging.debug(f"🔍 [STRATEGY1] Parameters: ({name_or_nickname}, {guild_id})")
                    
                cursor.execute(strategy1_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY1] Found exact player_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY1] No exact player_name match found")
                
                # Strategy 2: Case-insensitive match with player_name
                strategy2_query = """
                    SELECT player_name FROM players 
                    WHERE LOWER(player_name) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY2] Case-insensitive player_name match: {strategy2_query}")
                    logging.debug(f"🔍 [STRATEGY2] Parameters: ({name_or_nickname}, {guild_id})")
                    
                cursor.execute(strategy2_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY2] Found case-insensitive player_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY2] No case-insensitive player_name match found")
                
                # Strategy 3: Exact nickname match (case-sensitive)
                strategy3_query = """
                    SELECT player_name FROM players 
                    WHERE nicknames IS NOT NULL 
                    AND nicknames ? %s 
                    AND guild_id = %s 
                    AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY3] Exact nickname match: {strategy3_query}")
                    logging.debug(f"🔍 [STRATEGY3] Parameters: ({name_or_nickname}, {guild_id})")
                    
                cursor.execute(strategy3_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY3] Found exact nickname match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY3] No exact nickname match found")
                
                # Strategy 4: Case-insensitive nickname match (Python list approach)
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY4] Starting Python list-based nickname matching")
                
                # Get all players with nicknames and check them in Python
                cursor.execute("""
                    SELECT player_name, nicknames 
                    FROM players 
                    WHERE guild_id = %s AND is_active = TRUE AND nicknames IS NOT NULL
                """, (guild_id,))
                
                nickname_results = cursor.fetchall()
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY4] Found {len(nickname_results)} players with nicknames in guild {guild_id}")
                
                for player_name, nicknames in nickname_results:
                    if log_level == 'debug':
                        logging.debug(f"🔍 [STRATEGY4] Checking {player_name}: {nicknames} (type: {type(nicknames)})")
                    
                    # Handle Python list directly (current storage format)
                    if isinstance(nicknames, list):
                        for nickname in nicknames:
                            if isinstance(nickname, str):
                                if log_level == 'debug':
                                    logging.debug(f"🔍 [STRATEGY4]   Testing nickname: '{nickname}' vs '{name_or_nickname}'")
                                    logging.debug(f"🔍 [STRATEGY4]   LOWER comparison: '{nickname.lower()}' == '{name_or_nickname.lower()}' => {nickname.lower() == name_or_nickname.lower()}")
                                
                                if nickname.lower() == name_or_nickname.lower():
                                    if log_level == 'debug':
                                        logging.debug(f"✅ [STRATEGY4] Found case-insensitive nickname match: '{nickname}' -> {player_name}")
                                    return player_name
                    elif isinstance(nicknames, dict):
                        # Handle empty dict placeholders
                        if log_level == 'debug':
                            logging.debug(f"🔍 [STRATEGY4]   Skipping dict (empty placeholder): {nicknames}")
                        continue
                    else:
                        if log_level == 'debug':
                            logging.debug(f"🔍 [STRATEGY4]   Unexpected nickname format: {type(nicknames)}")
                
                if log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY4] No case-insensitive nickname match found")
                
                # Strategy 5: Alternative JSONB case-insensitive approach (fallback)
                try:
                    strategy5_query = """
                        SELECT player_name FROM players 
                        WHERE guild_id = %s 
                        AND is_active = TRUE
                        AND nicknames IS NOT NULL
                        AND LOWER(nicknames::text) LIKE LOWER(%s)
                    """
                    if log_level == 'debug':
                        logging.debug(f"🔍 [STRATEGY5] Alternative JSONB text search: {strategy5_query}")
                        logging.debug(f"🔍 [STRATEGY5] Parameters: ({guild_id}, '%{name_or_nickname}%')")
                    
                    cursor.execute(strategy5_query, (guild_id, f'%"{name_or_nickname}"%'))
                    result = cursor.fetchone()
                    if result:
                        if log_level == 'debug':
                            logging.debug(f"✅ [STRATEGY5] Found alternative JSONB match: {result[0]}")
                        return result[0]
                    elif log_level == 'debug':
                        logging.debug(f"❌ [STRATEGY5] No alternative JSONB match found")
                        
                except Exception as e:
                    if log_level == 'debug':
                        logging.debug(f"❌ [STRATEGY5] Alternative JSONB strategy failed: {e}")

                # Strategy 6: Match display_name (Discord display name)
                strategy6_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(display_name) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY6] Display name match: {strategy6_query}")
                    logging.debug(f"🔍 [STRATEGY6] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy6_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY6] Found display_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY6] No display_name match found")

                # Strategy 7: Match discord_username (Discord username)
                strategy7_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(discord_username) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY7] Discord username match: {strategy7_query}")
                    logging.debug(f"🔍 [STRATEGY7] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy7_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY7] Found discord_username match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY7] No discord_username match found")

                # Final debugging: show all available data
                if log_level == 'debug':
                    cursor.execute("""
                        SELECT player_name, nicknames 
                        FROM players 
                        WHERE guild_id = %s AND is_active = TRUE
                    """, (guild_id,))
                    
                    all_players = cursor.fetchall()
                    logging.debug(f"🔍 [FINAL] Resolution failed for '{name_or_nickname}' in guild {guild_id}")
                    logging.debug(f"🔍 [FINAL] All active players in this guild:")
                    for player, nicknames in all_players:
                        logging.debug(f"🔍 [FINAL]   - {player}: {nicknames if nicknames else 'No nicknames'}")
                
                return None  # Not found
                
        except Exception as e:
            # Enhanced error logging
            if log_level == 'error':
                logging.error(f"❌ Database error resolving player name '{name_or_nickname}' (guild: {guild_id}): {e}")
                import traceback
                logging.error(f"❌ Full traceback: {traceback.format_exc()}")
            elif log_level == 'debug':
                logging.debug(f"🔍 Database lookup failed for '{name_or_nickname}' (expected if opponent): {e}")
            # log_level == 'none' means no logging
            return None
    
    def add_race_results(self, results: List[Dict], race_count: int = 12, guild_id: int = 0) -> Optional[int]:
        """
        Add race results for multiple players.
        results: [{'name': 'PlayerName', 'score': 85}, ...]
        race_count: number of races in this session (default 12)
        Returns: war_id if successful, None if failed
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Store the war session
                session_data = {
                    'race_count': race_count,
                    'results': results,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Use Eastern Time instead of UTC (automatically handles EST/EDT)
                import zoneinfo
                try:
                    eastern_tz = zoneinfo.ZoneInfo('America/New_York')
                    eastern_now = datetime.now(eastern_tz)
                except ImportError:
                    # Fallback for Python < 3.9 or if zoneinfo not available
                    # Use a simple EST offset (this won't handle DST automatically)
                    eastern_tz = timezone(timedelta(hours=-5))  # EST
                    eastern_now = datetime.now(eastern_tz)

                # Calculate team score and differential
                team_score = sum(result.get('score', 0) for result in results)
                total_points = 82 * race_count
                opponent_score = total_points - team_score
                team_differential = team_score - opponent_score

                cursor.execute("""
                    INSERT INTO wars (war_date, race_count, players_data, guild_id, team_score, team_differential)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    eastern_now.date(),
                    race_count,
                    json.dumps(session_data),
                    guild_id,
                    team_score,
                    team_differential
                ))
                
                war_id = cursor.fetchone()[0]

                # Insert into player_war_performances table for optimized queries
                performances_added = 0
                for result in results:
                    player_name = result.get('name')
                    resolved_name = self.resolve_player_name(player_name, guild_id, log_level='none')

                    if resolved_name:
                        # Get player_id
                        cursor.execute("""
                            SELECT id FROM players
                            WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                        """, (resolved_name, guild_id))

                        player_row = cursor.fetchone()
                        if player_row:
                            player_id = player_row[0]
                            score = result.get('score', 0)
                            races_played = result.get('races_played', race_count)
                            war_participation = result.get('war_participation', races_played / race_count if race_count > 0 else 1.0)

                            # Insert into player_war_performances
                            cursor.execute("""
                                INSERT INTO player_war_performances
                                (player_id, war_id, score, races_played, war_participation)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (player_id, war_id) DO NOTHING
                            """, (player_id, war_id, score, races_played, war_participation))
                            performances_added += 1

                conn.commit()
                logging.info(f"✅ Added war results for {len(results)} players (war ID: {war_id}, {performances_added} performances tracked)")
                return war_id
                
        except Exception as e:
            logging.error(f"❌ Error adding race results: {e}")
            return None
    
    def get_player_info(self, name_or_nickname: str, guild_id: int = 0) -> Optional[Dict]:
        """Get basic roster info for a player."""
        main_name = self.resolve_player_name(name_or_nickname, guild_id)
        if not main_name:
            return None
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (main_name, guild_id))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return {
                    'player_name': row[0],
                    'added_by': row[1],
                    'created_at': row[2].isoformat() if row[2] else None,
                    'updated_at': row[3].isoformat() if row[3] else None,
                    'team': row[4] if row[4] else 'Unassigned',
                    'nicknames': row[5] if row[5] else []
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting player info: {e}")
            return None
    
    def get_all_players_stats(self, guild_id: int = 0) -> List[Dict]:
        """Get all roster players info."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames, member_status, country_code
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE
                    ORDER BY member_status, player_name
                """, (guild_id,))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'player_name': row[0],
                        'added_by': row[1],
                        'created_at': row[2].isoformat() if row[2] else None,
                        'updated_at': row[3].isoformat() if row[3] else None,
                        'team': row[4] if row[4] else 'Unassigned',
                        'nicknames': row[5] if row[5] else [],
                        'member_status': row[6] if row[6] else 'member',
                        'country_code': row[7] if row[7] else None
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"❌ Error getting all player stats: {e}")
            return []
    
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
                
                # Get roster count
                cursor.execute("SELECT COUNT(*) FROM players WHERE guild_id = %s AND is_active = TRUE", (guild_id,))
                info['roster_count'] = cursor.fetchone()[0]
                
                # Get war count
                cursor.execute("SELECT COUNT(*) FROM wars WHERE guild_id = %s", (guild_id,))
                info['war_count'] = cursor.fetchone()[0]
                
                # Get database size
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
    
    # Roster Management Methods
    def get_roster_players(self, guild_id: int = 0) -> List[str]:
        """Get list of active roster players."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name FROM players 
                    WHERE guild_id = %s AND is_active = TRUE 
                    ORDER BY player_name
                """, (guild_id,))
                
                return [row[0] for row in cursor.fetchall()]
                
        except Exception as e:
            logging.error(f"❌ Error getting roster players: {e}")
            return []
    
    def add_roster_player(self, player_name: str, added_by: str = None, guild_id: int = 0, member_status: str = 'member') -> bool:
        """Add a player to the active roster with optional member status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player already exists
                cursor.execute("""
                    SELECT id, is_active FROM players WHERE player_name = %s AND guild_id = %s
                """, (player_name, guild_id))
                
                existing = cursor.fetchone()
                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player {player_name} is already in the active roster")
                        return False
                    else:
                        # Reactivate player
                        cursor.execute("""
                            UPDATE players 
                            SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP, added_by = %s, member_status = %s
                            WHERE player_name = %s AND guild_id = %s
                        """, (added_by, member_status, player_name, guild_id))
                        logging.info(f"✅ Reactivated player {player_name} in roster")
                else:
                    # Add new player
                    cursor.execute("""
                        INSERT INTO players (player_name, added_by, guild_id, member_status) 
                        VALUES (%s, %s, %s, %s)
                    """, (player_name, added_by, guild_id, member_status))
                    logging.info(f"✅ Added player {player_name} to roster")
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding player to roster: {e}")
            return False
    
    def remove_roster_player(self, player_name: str, guild_id: int = 0) -> bool:
        """Remove a player from the active roster (mark as inactive)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT id FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                if not cursor.fetchone():
                    logging.info(f"Player {player_name} is not in the active roster")
                    return False
                
                # Mark as inactive instead of deleting
                cursor.execute("""
                    UPDATE players 
                    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (player_name, guild_id))
                
                conn.commit()
                logging.info(f"✅ Removed player {player_name} from active roster")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing player from roster: {e}")
            return False
    

    # Team Management Methods
    def set_player_team(self, player_name: str, team: str, guild_id: int = 0) -> bool:
        """Set a player's team assignment."""
        # Get valid teams for this guild
        valid_teams = self.get_guild_team_names(guild_id)
        valid_teams.append('Unassigned')  # Always allow Unassigned
        
        if team not in valid_teams:
            logging.error(f"Invalid team '{team}'. Valid teams for guild {guild_id}: {valid_teams}")
            return False
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT id FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                if not cursor.fetchone():
                    logging.error(f"Player {player_name} not found in active roster")
                    return False
                
                # Update player's team
                cursor.execute("""
                    UPDATE players 
                    SET team = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (team, player_name, guild_id))
                
                conn.commit()
                logging.info(f"✅ Set {player_name}'s team to {team}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error setting player team: {e}")
            return False
    
    def get_players_by_team(self, team: str = None, guild_id: int = 0) -> Dict[str, List[str]]:
        """Get players organized by team, or players from a specific team."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if team:
                    # Get players from specific team
                    cursor.execute("""
                        SELECT player_name FROM players 
                        WHERE team = %s AND guild_id = %s AND is_active = TRUE
                        ORDER BY player_name
                    """, (team, guild_id))
                    
                    return {team: [row[0] for row in cursor.fetchall()]}
                else:
                    # Get all players organized by team
                    cursor.execute("""
                        SELECT team, player_name FROM players 
                        WHERE guild_id = %s AND is_active = TRUE
                        ORDER BY team, player_name
                    """, (guild_id,))
                    
                    teams = {}
                    for row in cursor.fetchall():
                        team_name, player_name = row
                        if team_name not in teams:
                            teams[team_name] = []
                        teams[team_name].append(player_name)
                    
                    return teams
                    
        except Exception as e:
            logging.error(f"❌ Error getting players by team: {e}")
            return {}
    
    def get_team_roster(self, team: str, guild_id: int = 0) -> List[str]:
        """Get list of players in a specific team."""
        team_data = self.get_players_by_team(team, guild_id)
        return team_data.get(team, [])
    
    def get_player_team(self, player_name: str, guild_id: int = 0) -> Optional[str]:
        """Get a player's current team assignment."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT team FROM players 
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logging.error(f"❌ Error getting player team: {e}")
            return None

    # Nickname Management Methods
    def add_nickname(self, player_name: str, nickname: str, guild_id: int = 0) -> bool:
        """Add a nickname to a player's nickname list."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT nicknames FROM players 
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False
                
                current_nicknames = result[0] if result[0] else []
                
                # Check if nickname already exists
                if nickname in current_nicknames:
                    logging.info(f"Nickname '{nickname}' already exists for {player_name}")
                    return False
                
                # Add new nickname
                updated_nicknames = current_nicknames + [nickname]
                
                cursor.execute("""
                    UPDATE players 
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (json.dumps(updated_nicknames), player_name, guild_id))
                
                conn.commit()
                logging.info(f"✅ Added nickname '{nickname}' to {player_name}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding nickname: {e}")
            return False
    
    def remove_nickname(self, player_name: str, nickname: str, guild_id: int = 0) -> bool:
        """Remove a nickname from a player's nickname list."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT nicknames FROM players 
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False
                
                current_nicknames = result[0] if result[0] else []
                
                # Check if nickname exists
                if nickname not in current_nicknames:
                    logging.info(f"Nickname '{nickname}' not found for {player_name}")
                    return False
                
                # Remove nickname
                updated_nicknames = [n for n in current_nicknames if n != nickname]
                
                cursor.execute("""
                    UPDATE players 
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (json.dumps(updated_nicknames), player_name, guild_id))
                
                conn.commit()
                logging.info(f"✅ Removed nickname '{nickname}' from {player_name}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing nickname: {e}")
            return False
    
    def get_player_nicknames(self, player_name: str, guild_id: int = 0) -> List[str]:
        """Get all nicknames for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT nicknames FROM players 
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                return result[0] if result and result[0] else []
                
        except Exception as e:
            logging.error(f"❌ Error getting player nicknames: {e}")
            return []
    
    def set_player_nicknames(self, player_name: str, nicknames: List[str], guild_id: int = 0) -> bool:
        """Set all nicknames for a player (replaces existing nicknames)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT id FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                if not cursor.fetchone():
                    logging.error(f"Player {player_name} not found in active roster")
                    return False
                
                # Remove duplicates while preserving order
                unique_nicknames = []
                for nickname in nicknames:
                    if nickname not in unique_nicknames:
                        unique_nicknames.append(nickname)
                
                cursor.execute("""
                    UPDATE players 
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (json.dumps(unique_nicknames), player_name, guild_id))
                
                conn.commit()
                logging.info(f"✅ Set nicknames for {player_name}: {unique_nicknames}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error setting player nicknames: {e}")
            return False

    # Player Statistics Management Methods
    def update_player_stats(self, player_name: str, score: int, races_played: int, war_participation: float, war_date: str, guild_id: int = 0, team_differential: int = 0) -> bool:
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
                    # Scale team_differential by war_participation for fractional wars
                    scaled_differential = int(team_differential * war_participation)
                    new_total_differential = (result[3] or 0) + scaled_differential
                    # Correct average calculation: total_score / war_count (preserves per-war average)
                    new_average = round(new_total_score / new_war_count, 2)

                    cursor.execute("""
                        UPDATE players
                        SET total_score = %s, total_races = %s, war_count = %s,
                            average_score = %s, last_war_date = %s, total_team_differential = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE player_name = %s AND guild_id = %s
                    """, (new_total_score, new_total_races, new_war_count, new_average, war_date, new_total_differential, player_name, guild_id))
                else:
                    # Player doesn't exist - this shouldn't happen if /setup was used properly
                    logging.error(f"Player {player_name} not found in players table for guild {guild_id}")
                    return False

                conn.commit()
                logging.info(f"✅ Updated stats for {player_name}: +{score} points, +{races_played} races, +{war_participation} wars, differential: {team_differential:+d}")
                return True

        except Exception as e:
            logging.error(f"❌ Error updating player stats: {e}")
            return False
    

    def remove_player_stats_with_participation(self, player_name: str, score: int, races_played: int, war_participation: float, guild_id: int = 0, team_differential: int = 0) -> bool:
        """Remove player statistics when a war is removed, accounting for war participation."""
        logging.info(f"🔍 Attempting to remove stats for player: {player_name}, guild_id: {guild_id}")
        logging.info(f"    Score to remove: {score}, Races: {races_played}, War participation: {war_participation}, Differential: {team_differential}")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get current stats with debug logging
                logging.info(f"🔍 Querying for player: {player_name} in guild {guild_id}")
                cursor.execute("""
                    SELECT total_score, total_races, war_count, total_team_differential
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    logging.warning(f"❌ No stats found for {player_name} in guild {guild_id} (or player inactive)")

                    # Additional debug: check if player exists at all
                    cursor.execute("SELECT player_name, guild_id, is_active FROM players WHERE player_name = %s", (player_name,))
                    all_matches = cursor.fetchall()
                    if all_matches:
                        logging.warning(f"🔍 Player '{player_name}' exists but in different states: {all_matches}")
                    else:
                        logging.warning(f"🔍 Player '{player_name}' does not exist in players table at all")
                    return False

                # Log current stats
                current_total_score, current_total_races, current_war_count, current_total_differential = result
                logging.info(f"✅ Found player {player_name}: current stats = {current_total_score} points, {current_total_races} races, {current_war_count} wars, differential: {current_total_differential}")

                # Convert Decimal to float for calculations (PostgreSQL NUMERIC returns Decimal)
                current_war_count = float(current_war_count)

                # Calculate new stats with safety checks
                new_total_score = max(0, current_total_score - score)
                new_total_races = max(0, current_total_races - races_played)
                new_war_count = max(0.0, current_war_count - war_participation)
                # Scale team_differential by war_participation for fractional wars
                scaled_differential = int(team_differential * war_participation)
                new_total_differential = (current_total_differential or 0) - scaled_differential

                logging.info(f"🔍 Calculated new stats: {new_total_score} points, {new_total_races} races, {new_war_count} wars, differential: {new_total_differential}")

                # Safe average calculation - avoid division by zero
                if new_war_count > 0:
                    new_average = round(new_total_score / new_war_count, 2)
                else:
                    new_average = 0.0

                logging.info(f"🔍 New average score: {new_average}")

                # Execute UPDATE with debug logging
                logging.info(f"🔍 Executing UPDATE for player {player_name}")
                cursor.execute("""
                    UPDATE players
                    SET total_score = %s, total_races = %s, war_count = %s,
                        average_score = %s, total_team_differential = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (new_total_score, new_total_races, new_war_count, new_average, new_total_differential, player_name, guild_id))
                
                # Check if UPDATE affected any rows
                rows_affected = cursor.rowcount
                logging.info(f"🔍 UPDATE affected {rows_affected} rows")
                
                if rows_affected == 0:
                    logging.warning(f"❌ UPDATE statement affected 0 rows for player {player_name}")
                    return False
                
                conn.commit()
                logging.info(f"✅ Successfully removed stats for {player_name}: -{score} points, -{races_played} races, -{war_participation} war participation")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing player stats with participation for {player_name}: {e}")
            import traceback
            logging.error(f"❌ Full traceback: {traceback.format_exc()}")
            return False
    
    def get_player_stats(self, player_name: str, guild_id: int = 0) -> Optional[Dict]:
        """Get comprehensive player statistics.

        Highest and lowest scores are calculated only from wars where the player
        participated in all 12 races for fair comparison across matches.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get player basic stats
                cursor.execute("""
                    SELECT id, total_score, total_races, war_count, average_score,
                           last_war_date, created_at, updated_at,
                           team, nicknames, added_by, total_team_differential, country_code
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    return None

                player_id = result[0]

                # Get highest and lowest scores from player_war_performances
                # Only include wars where player participated in all 12 races
                cursor.execute("""
                    SELECT MAX(pwp.score), MIN(pwp.score)
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s AND pwp.races_played = 12
                """, (player_id, guild_id))

                score_stats = cursor.fetchone()
                highest_score = score_stats[0] if score_stats and score_stats[0] is not None else 0
                lowest_score = score_stats[1] if score_stats and score_stats[1] is not None else 0

                # Calculate win/loss/tie record from team differentials
                cursor.execute("""
                    SELECT COUNT(CASE WHEN w.team_differential > 0 THEN 1 END),
                           COUNT(CASE WHEN w.team_differential < 0 THEN 1 END),
                           COUNT(CASE WHEN w.team_differential = 0 THEN 1 END)
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                """, (player_id, guild_id))

                record_stats = cursor.fetchone()
                wins = record_stats[0] if record_stats else 0
                losses = record_stats[1] if record_stats else 0
                ties = record_stats[2] if record_stats else 0
                total_wars = wins + losses + ties
                win_percentage = (wins / total_wars * 100) if total_wars > 0 else 0.0

                return {
                    'player_name': player_name,
                    'total_score': result[1],
                    'total_races': result[2],
                    'war_count': result[3],
                    'average_score': float(result[4]) if result[4] else 0.0,
                    'last_war_date': result[5].isoformat() if result[5] else None,
                    'stats_created_at': result[6].isoformat() if result[6] else None,
                    'stats_updated_at': result[7].isoformat() if result[7] else None,
                    'team': result[8] if result[8] else 'Unassigned',
                    'nicknames': result[9] if result[9] else [],
                    'added_by': result[10],
                    'total_team_differential': result[11] if result[11] is not None else 0,
                    'country_code': result[12] if result[12] else None,
                    'highest_score': highest_score,
                    'lowest_score': lowest_score,
                    'wins': wins,
                    'losses': losses,
                    'ties': ties,
                    'win_percentage': win_percentage
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting player stats: {e}")
            return None
    
    def get_player_stats_last_x_wars(self, player_name: str, x_wars: int, guild_id: int = 0) -> Optional[Dict]:
        """
        Get player statistics calculated from their last X wars only.
        OPTIMIZED: Uses player_war_performances table for ~200x faster lookups.

        Args:
            player_name: Name of the player
            x_wars: Number of recent wars to calculate stats from
            guild_id: Guild ID

        Returns:
            Dict with same format as get_player_stats() but calculated from last X wars,
            or None if player not found or no wars
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get player info and ID
                cursor.execute("""
                    SELECT id, team, nicknames, added_by, created_at
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                player_info = cursor.fetchone()
                if not player_info:
                    return None

                player_id = player_info[0]

                # Get last X war performances with team differential
                cursor.execute("""
                    SELECT
                        w.war_date,
                        w.race_count,
                        w.team_differential,
                        pwp.score,
                        pwp.races_played,
                        pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                    ORDER BY w.created_at DESC
                    LIMIT %s
                """, (player_id, guild_id, x_wars))

                performances = cursor.fetchall()
                if not performances:
                    return None

                # Calculate stats from performances
                total_score = 0
                total_races = 0
                total_war_participation = 0.0
                total_team_differential = 0
                last_war_date = None
                highest_score = 0
                lowest_score = None
                wins = 0
                losses = 0
                ties = 0

                for perf in performances:
                    war_date, race_count, team_diff, score, races_played, war_participation = perf
                    total_score += score
                    total_races += races_played
                    total_war_participation += float(war_participation)
                    # Scale team_differential by war_participation for fractional wars
                    scaled_differential = int((team_diff or 0) * war_participation)
                    total_team_differential += scaled_differential

                    # Calculate win/loss/tie
                    if team_diff is not None:
                        if team_diff > 0:
                            wins += 1
                        elif team_diff < 0:
                            losses += 1
                        else:
                            ties += 1

                    # Track highest/lowest scores (only for 12-race wars)
                    if races_played == 12:
                        if score > highest_score:
                            highest_score = score
                        if lowest_score is None or score < lowest_score:
                            lowest_score = score

                    if war_date and (not last_war_date or war_date > last_war_date):
                        last_war_date = war_date

                # Calculate average score
                average_score = round(total_score / total_war_participation, 2) if total_war_participation > 0 else 0.0

                # Calculate win percentage
                total_wars = wins + losses + ties
                win_percentage = (wins / total_wars * 100) if total_wars > 0 else 0.0

                # Default lowest_score to 0 if no 12-race wars found
                if lowest_score is None:
                    lowest_score = 0

                return {
                    'player_name': player_name,
                    'total_score': total_score,
                    'total_races': total_races,
                    'war_count': total_war_participation,
                    'average_score': float(average_score),
                    'last_war_date': last_war_date.isoformat() if last_war_date else None,
                    'stats_created_at': player_info[4].isoformat() if player_info[4] else None,
                    'stats_updated_at': None,  # Not applicable for calculated stats
                    'team': player_info[1] if player_info[1] else 'Unassigned',
                    'nicknames': player_info[2] if player_info[2] else [],
                    'added_by': player_info[3],
                    'total_team_differential': total_team_differential,
                    'highest_score': highest_score,
                    'lowest_score': lowest_score,
                    'wins': wins,
                    'losses': losses,
                    'ties': ties,
                    'win_percentage': win_percentage
                }

        except Exception as e:
            logging.error(f"❌ Error getting player stats for last {x_wars} wars: {e}")
            return None
    
    def get_player_distinct_war_count(self, player_name: str, guild_id: int = 0) -> int:
        """
        Get the number of distinct wars a player has participated in.
        Used for validation when requesting last X wars stats.
        OPTIMIZED: Uses player_war_performances table for ~200x faster lookups.

        Args:
            player_name: Name of the player
            guild_id: Guild ID

        Returns:
            int: Number of distinct wars the player participated in (0 if none)
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Use optimized indexed query on player_war_performances table
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM player_war_performances pwp
                    JOIN players p ON pwp.player_id = p.id
                    WHERE p.player_name = %s AND p.guild_id = %s
                """, (player_name, guild_id))

                count = cursor.fetchone()[0]
                logging.info(f"✅ Player {player_name} participated in {count} distinct wars")
                return count

        except Exception as e:
            logging.error(f"❌ Error getting distinct war count for {player_name}: {e}")
            return 0
    
    def get_war_by_id(self, war_id: int, guild_id: int = 0) -> Optional[Dict]:
        """Get specific war details by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, war_date, race_count, players_data, created_at, team_score, team_differential
                    FROM wars WHERE id = %s AND guild_id = %s
                """, (war_id, guild_id))

                result = cursor.fetchone()
                if not result:
                    return None

                session_data = result[3] if result[3] else {}
                return {
                    'id': result[0],
                    'war_date': result[1].isoformat() if result[1] else None,
                    'race_count': result[2],
                    'results': session_data.get('results', []),
                    'created_at': result[4].isoformat() if result[4] else None,
                    'team_score': result[5],
                    'team_differential': result[6]
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting war by ID: {e}")
            return None
    
    def get_all_wars(self, limit: int = None, guild_id: int = 0) -> List[Dict]:
        """Get all wars in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get recent wars in DESC order, then we'll reverse them for display
                query = """
                    SELECT id, war_date, race_count, players_data, created_at
                    FROM wars
                    WHERE guild_id = %s
                    ORDER BY created_at DESC
                """
                
                if limit:
                    query += " LIMIT %s"
                    cursor.execute(query, (guild_id, limit))
                else:
                    cursor.execute(query, (guild_id,))
                
                results = []
                for row in cursor.fetchall():
                    session_data = row[3] if row[3] else {}
                    player_count = len(session_data.get('results', []))
                    
                    results.append({
                        'id': row[0],
                        'war_date': row[1].isoformat() if row[1] else None,
                        'race_count': row[2],
                        'player_count': player_count,
                        'results': session_data.get('results', []),
                        'created_at': row[4].isoformat() if row[4] else None
                    })
                
                # Reverse the results so oldest wars appear first
                return list(reversed(results))
                
        except Exception as e:
            logging.error(f"❌ Error getting all wars: {e}")
            return []
    
    def get_last_war_for_duplicate_check(self, guild_id: int = 0) -> Optional[List[Dict]]:
        """
        Get the most recent war's player results for duplicate detection.
        Returns normalized player data for comparison: [{'name': 'Player', 'score': 85}, ...]
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT players_data
                    FROM wars
                    WHERE guild_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (guild_id,))
                
                result = cursor.fetchone()
                if not result or not result[0]:
                    return None
                
                # Extract player results from the war data
                war_data = result[0]
                player_results = war_data.get('results', [])
                
                if not player_results:
                    return None
                
                # Normalize the data for comparison (name and score only)
                normalized_results = []
                for player in player_results:
                    normalized_results.append({
                        'name': player.get('name', '').strip().lower(),
                        'score': player.get('score', 0)
                    })
                
                # Sort by name for consistent comparison
                normalized_results.sort(key=lambda x: x['name'])
                
                logging.info(f"✅ Retrieved last war data for duplicate check: {len(normalized_results)} players")
                return normalized_results
                
        except Exception as e:
            logging.error(f"❌ Error getting last war for duplicate check: {e}")
            return None
    
    @staticmethod
    def check_for_duplicate_war(new_results: List[Dict], last_war_results: Optional[List[Dict]]) -> bool:
        """
        Check if new war results are identical to the last war.
        Compares normalized player names and scores.
        
        Args:
            new_results: New war results to check
            last_war_results: Previous war results from get_last_war_for_duplicate_check()
            
        Returns:
            True if wars are identical, False otherwise
        """
        if not last_war_results or not new_results:
            return False
        
        # Normalize new results for comparison
        normalized_new = []
        for player in new_results:
            normalized_new.append({
                'name': player.get('name', '').strip().lower(),
                'score': player.get('score', 0)
            })
        
        # Sort by name for consistent comparison
        normalized_new.sort(key=lambda x: x['name'])
        
        # Compare lengths first
        if len(normalized_new) != len(last_war_results):
            return False
        
        # Compare each player entry
        for new_player, last_player in zip(normalized_new, last_war_results):
            if (new_player['name'] != last_player['name'] or 
                new_player['score'] != last_player['score']):
                return False
        
        logging.info(f"🔍 Duplicate war detected: {len(normalized_new)} players with identical names and scores")
        return True
    
    def remove_war_by_id(self, war_id: int, guild_id: int = 0) -> Optional[int]:
        """Remove a war by ID and update player statistics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get war details first
                war = self.get_war_by_id(war_id, guild_id)
                if not war:
                    logging.warning(f"War ID {war_id} not found")
                    return False
                
                # Handle data format - results should be in war['results']
                players_data = war.get('results', [])
                team_differential = war.get('team_differential', 0)
                logging.info(f"🔍 War data retrieved: {war}")
                logging.info(f"🔍 Players data from war: {players_data}")
                logging.info(f"🔍 Number of players to process: {len(players_data)}")
                logging.info(f"🔍 Team differential to remove: {team_differential}")

                # Update player stats by removing this war's contribution
                stats_reverted = 0
                for i, result in enumerate(players_data):
                    logging.info(f"🔍 Processing player {i+1}/{len(players_data)}: {result}")
                    player_name = result.get('name')
                    score = result.get('score', 0)
                    races_played = result.get('races_played', war.get('race_count', 12))
                    war_participation = result.get('war_participation', 1.0)

                    if not player_name:
                        continue

                    # Resolve player name in case the war used a nickname
                    resolved_player = self.resolve_player_name(player_name, guild_id)
                    if resolved_player:
                        # Remove stats using war participation
                        success = self.remove_player_stats_with_participation(
                            resolved_player, score, races_played, war_participation, guild_id, team_differential
                        )
                        if success:
                            stats_reverted += 1
                            logging.info(f"✅ Reverted stats for {resolved_player}: -{score} points, -{races_played} races, -{war_participation} participation")
                        else:
                            logging.warning(f"❌ Failed to revert stats for {resolved_player}")
                    else:
                        logging.warning(f"❌ Could not resolve player name: {player_name}")
                
                # Delete the war
                cursor.execute("DELETE FROM wars WHERE id = %s AND guild_id = %s", (war_id, guild_id))
                
                conn.commit()
                logging.info(f"✅ Removed war ID {war_id} and reverted stats for {stats_reverted} players")
                return stats_reverted
                
        except Exception as e:
            logging.error(f"❌ Error removing war: {e}")
            return None

    # Guild Configuration Management Methods
    def get_guild_config(self, guild_id: int) -> Optional[Dict]:
        """Get guild configuration settings."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT guild_id, guild_name, team_names, is_active, created_at, updated_at
                    FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'guild_id': result[0],
                    'guild_name': result[1],
                    'team_names': result[2] if result[2] else [],
                    'is_active': result[3],
                    'created_at': result[4].isoformat() if result[4] else None,
                    'updated_at': result[5].isoformat() if result[5] else None
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting guild config: {e}")
            return None
    
    def create_guild_config(self, guild_id: int, guild_name: str = None, team_names: List[str] = None) -> bool:
        """Create a new guild configuration."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Set defaults
                if team_names is None:
                    team_names = []
                
                cursor.execute("""
                    INSERT INTO guild_configs (guild_id, guild_name, team_names)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        team_names = EXCLUDED.team_names,
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, guild_name, json.dumps(team_names)))
                
                conn.commit()
                logging.info(f"✅ Created/updated guild config for {guild_id}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error creating guild config: {e}")
            return False
    
    def update_guild_config(self, guild_id: int, **kwargs) -> bool:
        """Update guild configuration settings."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build dynamic update query
                update_fields = []
                values = []
                
                for key, value in kwargs.items():
                    if key in ['guild_name', 'team_names', 'is_active']:
                        if key in ['team_names']:
                            update_fields.append(f"{key} = %s")
                            values.append(json.dumps(value))
                        else:
                            update_fields.append(f"{key} = %s")
                            values.append(value)
                
                if not update_fields:
                    return False
                
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                values.append(guild_id)
                
                query = f"UPDATE guild_configs SET {', '.join(update_fields)} WHERE guild_id = %s"
                cursor.execute(query, values)
                
                conn.commit()
                logging.info(f"✅ Updated guild config for {guild_id}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error updating guild config: {e}")
            return False
    
    def get_guild_team_names(self, guild_id: int) -> List[str]:
        """Get valid team names for a guild."""
        config = self.get_guild_config(guild_id)
        if config:
            return config.get('team_names', [])
        return []
    
    def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is allowed for bot commands."""
        # allowed_channels functionality deprecated in favor of ocr_channel_id
        # Default to allowing all channels
        return True
    
    # Team Management Methods
    def add_guild_team(self, guild_id: int, team_name: str) -> bool:
        """Add a new team to a guild's configuration."""
        try:
            # Validate team name
            if not self.validate_team_name(team_name):
                return False
            
            # Get current teams
            current_teams = self.get_guild_team_names(guild_id)
            
            # Check if team already exists (case-insensitive)
            if any(team.lower() == team_name.lower() for team in current_teams):
                logging.error(f"Team '{team_name}' already exists in guild {guild_id}")
                return False
            
            # Check team limit (max 5 custom teams)
            if len(current_teams) >= 5:
                logging.error(f"Guild {guild_id} has reached maximum team limit (5)")
                return False
            
            # Add team to guild config
            new_teams = current_teams + [team_name]
            success = self.update_guild_config(guild_id, team_names=new_teams)
            
            if success:
                logging.info(f"✅ Added team '{team_name}' to guild {guild_id}")
            
            return success
            
        except Exception as e:
            logging.error(f"❌ Error adding team to guild: {e}")
            return False
    
    def remove_guild_team(self, guild_id: int, team_name: str) -> bool:
        """Remove a team from a guild's configuration and move players to Unassigned."""
        try:
            # Get current teams
            current_teams = self.get_guild_team_names(guild_id)
            
            # Check if team exists (case-insensitive search)
            team_to_remove = None
            for team in current_teams:
                if team.lower() == team_name.lower():
                    team_to_remove = team
                    break
            
            if not team_to_remove:
                logging.error(f"Team '{team_name}' not found in guild {guild_id}")
                return False
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Move all players from this team to Unassigned
                cursor.execute("""
                    UPDATE players 
                    SET team = 'Unassigned', updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = %s AND team = %s
                """, (guild_id, team_to_remove))
                
                moved_players = cursor.rowcount
                
                # Remove team from guild config
                new_teams = [team for team in current_teams if team != team_to_remove]
                success = self.update_guild_config(guild_id, team_names=new_teams)
                
                if success:
                    conn.commit()
                    logging.info(f"✅ Removed team '{team_to_remove}' from guild {guild_id}, moved {moved_players} players to Unassigned")
                    return True
                else:
                    conn.rollback()
                    return False
                    
        except Exception as e:
            logging.error(f"❌ Error removing team from guild: {e}")
            return False
    
    def rename_guild_team(self, guild_id: int, old_name: str, new_name: str) -> bool:
        """Rename a team in a guild's configuration and update player assignments."""
        try:
            # Validate new team name
            if not self.validate_team_name(new_name):
                return False
            
            # Get current teams
            current_teams = self.get_guild_team_names(guild_id)
            
            # Check if old team exists (case-insensitive search)
            team_to_rename = None
            for team in current_teams:
                if team.lower() == old_name.lower():
                    team_to_rename = team
                    break
            
            if not team_to_rename:
                logging.error(f"Team '{old_name}' not found in guild {guild_id}")
                return False
            
            # Check if new name already exists (case-insensitive)
            if any(team.lower() == new_name.lower() for team in current_teams if team != team_to_rename):
                logging.error(f"Team '{new_name}' already exists in guild {guild_id}")
                return False
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Update player assignments
                cursor.execute("""
                    UPDATE players 
                    SET team = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = %s AND team = %s
                """, (new_name, guild_id, team_to_rename))
                
                updated_players = cursor.rowcount
                
                # Update guild config
                new_teams = [new_name if team == team_to_rename else team for team in current_teams]
                success = self.update_guild_config(guild_id, team_names=new_teams)
                
                if success:
                    conn.commit()
                    logging.info(f"✅ Renamed team '{team_to_rename}' to '{new_name}' in guild {guild_id}, updated {updated_players} players")
                    return True
                else:
                    conn.rollback()
                    return False
                    
        except Exception as e:
            logging.error(f"❌ Error renaming team in guild: {e}")
            return False
    
    def validate_team_name(self, team_name: str) -> bool:
        """Validate a team name according to rules."""
        if not team_name or not team_name.strip():
            logging.error("Team name cannot be empty or whitespace-only")
            return False
        
        # Length check (1-50 characters)
        if len(team_name) < 1 or len(team_name) > 50:
            logging.error(f"Team name must be 1-50 characters long, got {len(team_name)}")
            return False
        
        # Reserved name check (case-insensitive)
        if team_name.lower() == 'unassigned':
            logging.error("'Unassigned' is a reserved team name")
            return False
        
        return True
    
    def get_guild_teams_with_counts(self, guild_id: int) -> Dict[str, int]:
        """Get all teams for a guild with player counts."""
        try:
            teams = self.get_players_by_team(guild_id=guild_id)
            return {team_name: len(players) for team_name, players in teams.items()}
            
        except Exception as e:
            logging.error(f"❌ Error getting guild teams with counts: {e}")
            return {}

    def set_player_member_status(self, player_name: str, member_status: str, guild_id: int = 0) -> bool:
        """Set the member status for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Resolve player name (handles nicknames)
                resolved_player = self.resolve_player_name(player_name, guild_id)
                if not resolved_player:
                    logging.error(f"Player {player_name} not found in guild {guild_id}")
                    return False
                
                # Update member status
                cursor.execute("""
                    UPDATE players 
                    SET member_status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (member_status, resolved_player, guild_id))
                
                if cursor.rowcount == 0:
                    logging.error(f"No active player {resolved_player} found to update")
                    return False
                
                conn.commit()
                logging.info(f"✅ Updated {resolved_player} member status to {member_status}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error setting member status: {e}")
            return False

    def get_players_by_member_status(self, member_status: str, guild_id: int = 0) -> List[Dict]:
        """Get all players with a specific member status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name, team, nicknames, created_at, updated_at
                    FROM players 
                    WHERE member_status = %s AND guild_id = %s AND is_active = TRUE
                    ORDER BY player_name
                """, (member_status, guild_id))
                
                results = cursor.fetchall()
                players = []
                
                for row in results:
                    players.append({
                        'player_name': row[0],
                        'team': row[1] or 'Unassigned',
                        'nicknames': row[2] or [],
                        'created_at': row[3],
                        'updated_at': row[4],
                        'member_status': member_status
                    })
                
                return players
                
        except Exception as e:
            logging.error(f"❌ Error getting players by member status: {e}")
            return []

    def get_member_status_counts(self, guild_id: int = 0) -> Dict[str, int]:
        """Get count of players by member status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT member_status, COUNT(*) 
                    FROM players 
                    WHERE guild_id = %s AND is_active = TRUE
                    GROUP BY member_status
                """, (guild_id,))
                
                results = cursor.fetchall()
                return {status: count for status, count in results}
                
        except Exception as e:
            logging.error(f"❌ Error getting member status counts: {e}")
            return {}

    def append_players_to_war_by_id(self, war_id: int, new_players: List[Dict], guild_id: int = 0) -> bool:
        """Append new players to an existing war without modifying existing players."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get existing war data
                existing_war = self.get_war_by_id(war_id, guild_id)
                if not existing_war:
                    logging.error(f"No war found with ID {war_id} in guild {guild_id}")
                    return False
                
                existing_results = existing_war.get('results', [])
                existing_names = {player.get('name', '').lower() for player in existing_results}
                
                # Check for duplicate players
                conflicts = []
                for new_player in new_players:
                    if new_player.get('name', '').lower() in existing_names:
                        conflicts.append(new_player.get('name', 'Unknown'))
                
                if conflicts:
                    logging.error(f"Players already exist in war {war_id}: {', '.join(conflicts)}")
                    return False
                
                # Append new players to existing results
                combined_results = existing_results + new_players

                # Calculate new team score and differential
                new_team_score = sum(p.get('score', 0) for p in combined_results)
                race_count = existing_war.get('race_count', 12)
                total_points = 82 * race_count
                opponent_score = total_points - new_team_score
                new_team_differential = new_team_score - opponent_score

                # Format data in the expected dict structure
                war_data = {
                    "results": combined_results,
                    "timestamp": datetime.now().isoformat(),
                    "race_count": race_count
                }

                # Update the war with combined data and new differential
                cursor.execute("""
                    UPDATE wars
                    SET players_data = %s, team_score = %s, team_differential = %s
                    WHERE id = %s AND guild_id = %s
                """, (json.dumps(war_data), new_team_score, new_team_differential, war_id, guild_id))

                if cursor.rowcount == 0:
                    logging.error(f"No war found with ID {war_id} in guild {guild_id}")
                    return False

                conn.commit()
                logging.info(f"✅ Appended {len(new_players)} players to war {war_id}, new differential: {new_team_differential:+d}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error appending players to war by ID: {e}")
            return False

    def update_war_by_id(self, war_id: int, results: List[Dict], race_count: int, guild_id: int = 0) -> bool:
        """Update an existing war with new player data."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Format data in the expected dict structure
                war_data = {
                    "results": results,
                    "timestamp": datetime.now().isoformat(),
                    "race_count": race_count
                }
                
                # Update the war with new data
                cursor.execute("""
                    UPDATE wars 
                    SET players_data = %s, race_count = %s
                    WHERE id = %s AND guild_id = %s
                """, (json.dumps(war_data), race_count, war_id, guild_id))
                
                if cursor.rowcount == 0:
                    logging.error(f"No war found with ID {war_id} in guild {guild_id}")
                    return False
                
                conn.commit()
                logging.info(f"✅ Updated war {war_id} with {len(results)} players")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error updating war by ID: {e}")
            return False

    # Discord User ID Support Methods

    def add_roster_player_with_discord(
        self,
        discord_user_id: int,
        player_name: str,
        display_name: str,
        discord_username: str,
        member_status: str,
        added_by: str = None,
        guild_id: int = 0,
        country_code: str = None
    ) -> bool:
        """Add a player to the active roster with Discord user ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if player with this Discord ID already exists for this guild
                cursor.execute("""
                    SELECT id, is_active, player_name FROM players
                    WHERE discord_user_id = %s AND guild_id = %s
                """, (discord_user_id, guild_id))

                existing = cursor.fetchone()
                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player with Discord ID {discord_user_id} is already in the active roster as {existing[2]}")
                        return False
                    else:
                        # Reactivate player and update info
                        cursor.execute("""
                            UPDATE players
                            SET is_active = TRUE,
                                player_name = %s,
                                display_name = %s,
                                discord_username = %s,
                                member_status = %s,
                                country_code = %s,
                                updated_at = CURRENT_TIMESTAMP,
                                added_by = %s,
                                last_role_sync = CURRENT_TIMESTAMP
                            WHERE discord_user_id = %s AND guild_id = %s
                        """, (player_name, display_name, discord_username, member_status, country_code, added_by, discord_user_id, guild_id))
                        logging.info(f"✅ Reactivated player {player_name} (Discord ID: {discord_user_id})")
                else:
                    # Add new player with Discord ID
                    cursor.execute("""
                        INSERT INTO players (
                            discord_user_id, player_name, display_name, discord_username,
                            member_status, added_by, guild_id, country_code, last_role_sync
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (discord_user_id, player_name, display_name, discord_username, member_status, added_by, guild_id, country_code))
                    logging.info(f"✅ Added player {player_name} with Discord ID {discord_user_id}")

                conn.commit()
                return True

        except Exception as e:
            logging.error(f"❌ Error adding player with Discord ID to roster: {e}")
            return False

    def link_player_to_discord_user(
        self,
        player_name: str,
        discord_user_id: int,
        display_name: str,
        discord_username: str,
        member_status: str,
        guild_id: int = 0
    ) -> bool:
        """Link an existing player to a Discord user."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if player exists
                cursor.execute("""
                    SELECT id, discord_user_id FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                if result[1] is not None:
                    logging.warning(f"Player {player_name} is already linked to Discord ID {result[1]}")
                    return False

                # Link player to Discord user
                cursor.execute("""
                    UPDATE players
                    SET discord_user_id = %s,
                        display_name = %s,
                        discord_username = %s,
                        member_status = %s,
                        last_role_sync = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (discord_user_id, display_name, discord_username, member_status, player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Linked player {player_name} to Discord ID {discord_user_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error linking player to Discord user: {e}")
            return False

    def sync_player_discord_info(
        self,
        discord_user_id: int,
        display_name: str,
        discord_username: str,
        guild_id: int = 0
    ) -> bool:
        """Sync player's display name and Discord username from Discord."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET display_name = %s,
                        discord_username = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = %s AND guild_id = %s
                """, (display_name, discord_username, discord_user_id, guild_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logging.debug(f"✅ Synced Discord info for user {discord_user_id}")
                    return True
                else:
                    logging.debug(f"No player found with Discord ID {discord_user_id} in guild {guild_id}")
                    return False

        except Exception as e:
            logging.error(f"❌ Error syncing player Discord info: {e}")
            return False

    def sync_player_role(
        self,
        discord_user_id: int,
        member_status: str,
        guild_id: int = 0
    ) -> bool:
        """Sync player's member_status from their Discord role."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET member_status = %s,
                        last_role_sync = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = %s AND guild_id = %s
                """, (member_status, discord_user_id, guild_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logging.debug(f"✅ Synced role for Discord user {discord_user_id} to {member_status}")
                    return True
                else:
                    logging.debug(f"No player found with Discord ID {discord_user_id} in guild {guild_id}")
                    return False

        except Exception as e:
            logging.error(f"❌ Error syncing player role: {e}")
            return False

    def get_unlinked_players(self, guild_id: int = 0) -> List[Dict]:
        """Get all active players without a Discord user ID link."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT player_name, team, member_status, total_score, war_count
                    FROM players
                    WHERE discord_user_id IS NULL
                    AND is_active = TRUE
                    AND guild_id = %s
                    ORDER BY player_name
                """, (guild_id,))

                players = []
                for row in cursor.fetchall():
                    players.append({
                        'player_name': row[0],
                        'team': row[1],
                        'member_status': row[2],
                        'total_score': row[3],
                        'war_count': float(row[4]) if row[4] else 0
                    })

                return players

        except Exception as e:
            logging.error(f"❌ Error getting unlinked players: {e}")
            return []

    def get_guild_role_config(self, guild_id: int) -> Optional[Dict]:
        """Get the role configuration for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT role_member_id, role_trial_id, role_ally_id
                    FROM guild_configs
                    WHERE guild_id = %s AND is_active = TRUE
                """, (guild_id,))

                result = cursor.fetchone()
                if result:
                    return {
                        'role_member_id': result[0],
                        'role_trial_id': result[1],
                        'role_ally_id': result[2]
                    }
                return None

        except Exception as e:
            logging.error(f"❌ Error getting guild role config: {e}")
            return None

    def set_guild_role_config(
        self,
        guild_id: int,
        role_member_id: int,
        role_trial_id: int,
        role_ally_id: int
    ) -> bool:
        """Set the role configuration for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if guild config exists
                cursor.execute("""
                    SELECT id FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                if cursor.fetchone():
                    # Update existing config
                    cursor.execute("""
                        UPDATE guild_configs
                        SET role_member_id = %s,
                            role_trial_id = %s,
                            role_ally_id = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE guild_id = %s
                    """, (role_member_id, role_trial_id, role_ally_id, guild_id))
                else:
                    # Insert new config
                    cursor.execute("""
                        INSERT INTO guild_configs (
                            guild_id, role_member_id, role_trial_id, role_ally_id, is_active
                        )
                        VALUES (%s, %s, %s, %s, TRUE)
                    """, (guild_id, role_member_id, role_trial_id, role_ally_id))

                conn.commit()
                logging.info(f"✅ Set role config for guild {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting guild role config: {e}")
            return False

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
        
        # Test adding roster players
        db.add_roster_player("TestPlayer", "system")
        
        # Test adding war results
        test_results = [
            {'name': 'TestPlayer', 'score': 95},
            {'name': 'Player2', 'score': 88}
        ]
        
        success = db.add_race_results(test_results)
        print(f"✅ War results added: {success}")
        
        # Test queries
        roster = db.get_roster_players()
        print(f"✅ Roster players: {roster}")
        
        # Test database info
        info = db.get_database_info()
        print(f"✅ Database info: {info}")
        
        # Initialize with test player
        db.add_roster_player("TestPlayer", "system")
        print(f"✅ Added TestPlayer to roster")
        
        db.close()
        
    else:
        print("❌ PostgreSQL connection failed")