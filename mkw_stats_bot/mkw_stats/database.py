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
from datetime import datetime
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
    
    def add_or_update_player(self, main_name: str, nicknames: List[str] = None, guild_id: int = 0) -> bool:
        """Add a new player to roster (simplified version)."""
        return self.add_roster_player(main_name, "system", guild_id)
    
    def resolve_player_name(self, name_or_nickname: str, guild_id: int = 0) -> Optional[str]:
        """Resolve a name or nickname to players table player name."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # First, check if it's an exact match with player_name
                cursor.execute("""
                    SELECT player_name FROM players 
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (name_or_nickname, guild_id))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                # Then check if it's a nickname (case-insensitive)
                cursor.execute("""
                    SELECT player_name FROM players 
                    WHERE nicknames ? %s AND guild_id = %s AND is_active = TRUE
                """, (name_or_nickname, guild_id))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                # Finally, try case-insensitive search for both name and nicknames
                cursor.execute("""
                    SELECT player_name FROM players 
                    WHERE (LOWER(player_name) = LOWER(%s) OR 
                           EXISTS (
                               SELECT 1 FROM jsonb_array_elements_text(nicknames) AS nickname
                               WHERE LOWER(nickname) = LOWER(%s)
                           ))
                    AND guild_id = %s AND is_active = TRUE
                """, (name_or_nickname, name_or_nickname, guild_id))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                return None  # Not found
                
        except Exception as e:
            logging.error(f"❌ Error resolving player name {name_or_nickname}: {e}")
            return None
    
    def add_race_results(self, results: List[Dict], race_count: int = 12, guild_id: int = 0) -> bool:
        """
        Add race results for multiple players.
        results: [{'name': 'PlayerName', 'score': 85}, ...]
        race_count: number of races in this session (default 12)
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
                
                cursor.execute("""
                    INSERT INTO wars (war_date, race_count, players_data, guild_id)
                    VALUES (%s, %s, %s, %s)
                """, (
                    datetime.now().date(),
                    race_count,
                    json.dumps(session_data),
                    guild_id
                ))
                
                # Just store the war data - no individual player tracking
                logging.info(f"War data stored with {len(results)} player results")
                
                conn.commit()
                logging.info(f"✅ Added war results for {len(results)} players")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding race results: {e}")
            return False
    
    def get_player_stats(self, name_or_nickname: str, guild_id: int = 0) -> Optional[Dict]:
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
            logging.error(f"❌ Error getting player stats: {e}")
            return None
    
    def get_all_players_stats(self, guild_id: int = 0) -> List[Dict]:
        """Get all roster players info."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames
                    FROM players 
                    WHERE guild_id = %s AND is_active = TRUE
                    ORDER BY team, player_name
                """, (guild_id,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'player_name': row[0],
                        'added_by': row[1],
                        'created_at': row[2].isoformat() if row[2] else None,
                        'updated_at': row[3].isoformat() if row[3] else None,
                        'team': row[4] if row[4] else 'Unassigned',
                        'nicknames': row[5] if row[5] else []
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"❌ Error getting all player stats: {e}")
            return []
    
    def get_recent_wars(self, limit: int = 5, guild_id: int = 0) -> List[Dict]:
        """Get recent war sessions."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT war_date, race_count, players_data, created_at
                    FROM wars
                    WHERE guild_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (guild_id, limit))
                
                results = []
                for row in cursor.fetchall():
                    session_data = row[2] if row[2] else {}
                    results.append({
                        'session_date': row[0].isoformat() if row[0] else None,
                        'race_count': row[1],
                        'results': session_data.get('results', []),
                        'created_at': row[3].isoformat() if row[3] else None
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"❌ Error getting recent wars: {e}")
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
    
    def add_roster_player(self, player_name: str, added_by: str = None, guild_id: int = 0) -> bool:
        """Add a player to the active roster."""
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
                            SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP, added_by = %s
                            WHERE player_name = %s AND guild_id = %s
                        """, (added_by, player_name, guild_id))
                        logging.info(f"✅ Reactivated player {player_name} in roster")
                else:
                    # Add new player
                    cursor.execute("""
                        INSERT INTO players (player_name, added_by, guild_id) 
                        VALUES (%s, %s, %s)
                    """, (player_name, added_by, guild_id))
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
    
    def initialize_roster_from_config(self, config_roster: List[str], guild_id: int = 0) -> bool:
        """Initialize roster table from config.CLAN_ROSTER (migration helper)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if roster is already populated
                cursor.execute("SELECT COUNT(*) FROM players WHERE guild_id = %s AND is_active = TRUE", (guild_id,))
                existing_count = cursor.fetchone()[0]
                
                if existing_count > 0:
                    logging.info(f"Roster already has {existing_count} players, skipping initialization")
                    return True
                
                # Add all config roster players
                for player in config_roster:
                    cursor.execute("""
                        INSERT INTO players (player_name, added_by, guild_id) 
                        VALUES (%s, %s, %s)
                        ON CONFLICT (player_name, guild_id) 
                        DO UPDATE SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                    """, (player, "system_migration", guild_id))
                
                conn.commit()
                logging.info(f"✅ Initialized roster with {len(config_roster)} players from config")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error initializing roster from config: {e}")
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
    def update_player_stats(self, player_name: str, score: int, races_played: int, war_participation: float, war_date: str, guild_id: int = 0) -> bool:
        """Update player statistics when a war is added with fractional war support."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and get current stats
                cursor.execute("""
                    SELECT total_score, total_races, war_count 
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                if result:
                    # Player has existing stats - UPDATE
                    new_total_score = result[0] + score
                    new_total_races = result[1] + races_played
                    new_war_count = float(result[2]) + war_participation  # Support fractional wars
                    # Correct average calculation: total_score / war_count (preserves per-war average)
                    new_average = round(new_total_score / new_war_count, 2)
                    
                    cursor.execute("""
                        UPDATE players 
                        SET total_score = %s, total_races = %s, war_count = %s, 
                            average_score = %s, last_war_date = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE player_name = %s AND guild_id = %s
                    """, (new_total_score, new_total_races, new_war_count, new_average, war_date, player_name, guild_id))
                else:
                    # Player doesn't exist - this shouldn't happen if /setup was used properly
                    logging.error(f"Player {player_name} not found in players table for guild {guild_id}")
                    return False
                
                conn.commit()
                logging.info(f"✅ Updated stats for {player_name}: +{score} points, +{races_played} races, +{war_participation} wars")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error updating player stats: {e}")
            return False
    
    def remove_player_stats(self, player_name: str, score: int, races: int, guild_id: int = 0) -> bool:
        """Remove player statistics when a war is removed."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get current stats
                cursor.execute("""
                    SELECT total_score, total_races, war_count 
                    FROM player_stats WHERE player_name = %s AND guild_id = %s
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                if not result:
                    logging.warning(f"No stats found for {player_name} to remove")
                    return False
                
                # Calculate new stats with safety checks
                new_total_score = max(0, result[0] - score)
                new_total_races = max(0, result[1] - races)
                new_war_count = max(0, result[2] - 1)
                
                # Safe average calculation - avoid division by zero
                if new_war_count > 0:
                    new_average = round(new_total_score / new_war_count, 2)
                else:
                    new_average = 0.0
                
                cursor.execute("""
                    UPDATE player_stats 
                    SET total_score = %s, total_races = %s, war_count = %s, 
                        average_score = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (new_total_score, new_total_races, new_war_count, new_average, player_name, guild_id))
                
                conn.commit()
                logging.info(f"✅ Removed stats for {player_name}: -{score} points, -{races} races")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing player stats: {e}")
            return False
    
    def get_player_statistics(self, player_name: str, guild_id: int = 0) -> Optional[Dict]:
        """Get comprehensive player statistics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT total_score, total_races, war_count, average_score, 
                           last_war_date, created_at, updated_at,
                           team, nicknames, added_by
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'player_name': player_name,
                    'total_score': result[0],
                    'total_races': result[1],
                    'war_count': result[2],
                    'average_score': float(result[3]) if result[3] else 0.0,
                    'last_war_date': result[4].isoformat() if result[4] else None,
                    'stats_created_at': result[5].isoformat() if result[5] else None,
                    'stats_updated_at': result[6].isoformat() if result[6] else None,
                    'team': result[7] if result[7] else 'Unassigned',
                    'nicknames': result[8] if result[8] else [],
                    'added_by': result[9]
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting player statistics: {e}")
            return None
    
    def get_war_by_id(self, war_id: int, guild_id: int = 0) -> Optional[Dict]:
        """Get specific war details by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, war_date, race_count, players_data, created_at
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
                    'created_at': result[4].isoformat() if result[4] else None
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting war by ID: {e}")
            return None
    
    def get_all_wars(self, limit: int = None, guild_id: int = 0) -> List[Dict]:
        """Get all wars in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
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
                
                return results
                
        except Exception as e:
            logging.error(f"❌ Error getting all wars: {e}")
            return []
    
    def remove_war_by_id(self, war_id: int, guild_id: int = 0) -> bool:
        """Remove a war by ID and update player statistics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get war details first
                war = self.get_war_by_id(war_id, guild_id)
                if not war:
                    logging.warning(f"War ID {war_id} not found")
                    return False
                
                # Update player stats by removing this war's contribution
                for result in war['results']:
                    player_name = result['name']
                    score = result['score']
                    races = war['race_count']
                    
                    # Resolve player name in case the war used a nickname
                    resolved_player = self.resolve_player_name(player_name, guild_id)
                    if resolved_player:
                        self.remove_player_stats(resolved_player, score, races, guild_id)
                
                # Delete the war
                cursor.execute("DELETE FROM wars WHERE id = %s AND guild_id = %s", (war_id, guild_id))
                
                conn.commit()
                logging.info(f"✅ Removed war ID {war_id} and updated player stats")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing war: {e}")
            return False

    # Guild Configuration Management Methods
    def get_guild_config(self, guild_id: int) -> Optional[Dict]:
        """Get guild configuration settings."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT guild_id, guild_name, team_names, allowed_channels, is_active, created_at, updated_at
                    FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'guild_id': result[0],
                    'guild_name': result[1],
                    'team_names': result[2] if result[2] else ['Phantom Orbit', 'Moonlight Bootel'],
                    'allowed_channels': result[3] if result[3] else [],
                    'is_active': result[4],
                    'created_at': result[5].isoformat() if result[5] else None,
                    'updated_at': result[6].isoformat() if result[6] else None
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting guild config: {e}")
            return None
    
    def create_guild_config(self, guild_id: int, guild_name: str = None, team_names: List[str] = None, allowed_channels: List[int] = None) -> bool:
        """Create a new guild configuration."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Set defaults
                if team_names is None:
                    team_names = ['Phantom Orbit', 'Moonlight Bootel']
                if allowed_channels is None:
                    allowed_channels = []
                
                cursor.execute("""
                    INSERT INTO guild_configs (guild_id, guild_name, team_names, allowed_channels)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        team_names = EXCLUDED.team_names,
                        allowed_channels = EXCLUDED.allowed_channels,
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, guild_name, json.dumps(team_names), json.dumps(allowed_channels)))
                
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
                    if key in ['guild_name', 'team_names', 'allowed_channels', 'is_active']:
                        if key in ['team_names', 'allowed_channels']:
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
            return config.get('team_names', ['Phantom Orbit', 'Moonlight Bootel'])
        return ['Phantom Orbit', 'Moonlight Bootel']
    
    def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is allowed for bot commands."""
        config = self.get_guild_config(guild_id)
        if config:
            allowed_channels = config.get('allowed_channels', [])
            # If no channels configured, allow all channels
            if not allowed_channels:
                return True
            return channel_id in allowed_channels
        return True  # Default to allowing all channels
    
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