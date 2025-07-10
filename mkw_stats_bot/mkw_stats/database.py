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
                
                # Check if tables exist
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'roster'
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
                
                # Create roster table for dynamic clan member management
                cursor.execute("""
                    CREATE TABLE roster (
                        id SERIAL PRIMARY KEY,
                        player_name VARCHAR(100) UNIQUE NOT NULL,
                        added_by VARCHAR(100),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for roster
                cursor.execute("""
                    CREATE INDEX idx_roster_player_name ON roster(player_name);
                    CREATE INDEX idx_roster_active ON roster(is_active);
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
                        
                    CREATE TRIGGER update_roster_updated_at 
                        BEFORE UPDATE ON roster 
                        FOR EACH ROW 
                        EXECUTE FUNCTION update_updated_at_column();
                """)
                
                conn.commit()
                logging.info("✅ PostgreSQL database tables created successfully")
                
        except Exception as e:
            logging.error(f"❌ Error initializing PostgreSQL database: {e}")
            raise
    
    def add_or_update_player(self, main_name: str, nicknames: List[str] = None) -> bool:
        """Add a new player to roster (simplified version)."""
        return self.add_roster_player(main_name, "system")
    
    def resolve_player_name(self, name_or_nickname: str) -> Optional[str]:
        """Resolve a name or nickname to roster player name."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # First, check if it's an exact match with player_name
                cursor.execute("""
                    SELECT player_name FROM roster 
                    WHERE player_name = %s AND is_active = TRUE
                """, (name_or_nickname,))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                # Then check if it's a nickname (case-insensitive)
                cursor.execute("""
                    SELECT player_name FROM roster 
                    WHERE nicknames ? %s AND is_active = TRUE
                """, (name_or_nickname,))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                # Finally, try case-insensitive search for both name and nicknames
                cursor.execute("""
                    SELECT player_name FROM roster 
                    WHERE (LOWER(player_name) = LOWER(%s) OR 
                           EXISTS (
                               SELECT 1 FROM jsonb_array_elements_text(nicknames) AS nickname
                               WHERE LOWER(nickname) = LOWER(%s)
                           ))
                    AND is_active = TRUE
                """, (name_or_nickname, name_or_nickname))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                return None  # Not found
                
        except Exception as e:
            logging.error(f"❌ Error resolving player name {name_or_nickname}: {e}")
            return None
    
    def add_race_results(self, results: List[Dict], race_count: int = 12) -> bool:
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
                    INSERT INTO wars (war_date, race_count, players_data)
                    VALUES (%s, %s, %s)
                """, (
                    datetime.now().date(),
                    race_count,
                    json.dumps(session_data)
                ))
                
                # Just store the war data - no individual player tracking
                logging.info(f"War data stored with {len(results)} player results")
                
                conn.commit()
                logging.info(f"✅ Added war results for {len(results)} players")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding race results: {e}")
            return False
    
    def get_player_stats(self, name_or_nickname: str) -> Optional[Dict]:
        """Get basic roster info for a player."""
        main_name = self.resolve_player_name(name_or_nickname)
        if not main_name:
            return None
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames
                    FROM roster WHERE player_name = %s AND is_active = TRUE
                """, (main_name,))
                
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
    
    def get_all_players_stats(self) -> List[Dict]:
        """Get all roster players info."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames
                    FROM roster 
                    WHERE is_active = TRUE
                    ORDER BY team, player_name
                """)
                
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
    
    def get_recent_wars(self, limit: int = 5) -> List[Dict]:
        """Get recent war sessions."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT war_date, race_count, players_data, created_at
                    FROM wars
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                
                results = []
                for row in cursor.fetchall():
                    session_data = row[2] if row[2] else {}
                    results.append({
                        'war_date': row[0].isoformat() if row[0] else None,
                        'race_count': row[1],
                        'results': session_data.get('results', []),
                        'created_at': row[3].isoformat() if row[3] else None
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"❌ Error getting recent wars: {e}")
            return []
    
    def get_database_info(self) -> Dict:
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
                cursor.execute("SELECT COUNT(*) FROM roster WHERE is_active = TRUE")
                info['roster_count'] = cursor.fetchone()[0]
                
                # Get war count
                cursor.execute("SELECT COUNT(*) FROM wars")
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
    def get_roster_players(self) -> List[str]:
        """Get list of active roster players."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT player_name FROM roster 
                    WHERE is_active = TRUE 
                    ORDER BY player_name
                """)
                
                return [row[0] for row in cursor.fetchall()]
                
        except Exception as e:
            logging.error(f"❌ Error getting roster players: {e}")
            return []
    
    def add_roster_player(self, player_name: str, added_by: str = None) -> bool:
        """Add a player to the active roster."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player already exists
                cursor.execute("""
                    SELECT id, is_active FROM roster WHERE player_name = %s
                """, (player_name,))
                
                existing = cursor.fetchone()
                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player {player_name} is already in the active roster")
                        return False
                    else:
                        # Reactivate player
                        cursor.execute("""
                            UPDATE roster 
                            SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP, added_by = %s
                            WHERE player_name = %s
                        """, (added_by, player_name))
                        logging.info(f"✅ Reactivated player {player_name} in roster")
                else:
                    # Add new player
                    cursor.execute("""
                        INSERT INTO roster (player_name, added_by) 
                        VALUES (%s, %s)
                    """, (player_name, added_by))
                    logging.info(f"✅ Added player {player_name} to roster")
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding player to roster: {e}")
            return False
    
    def remove_roster_player(self, player_name: str) -> bool:
        """Remove a player from the active roster (mark as inactive)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT id FROM roster WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
                if not cursor.fetchone():
                    logging.info(f"Player {player_name} is not in the active roster")
                    return False
                
                # Mark as inactive instead of deleting
                cursor.execute("""
                    UPDATE roster 
                    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s
                """, (player_name,))
                
                conn.commit()
                logging.info(f"✅ Removed player {player_name} from active roster")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing player from roster: {e}")
            return False
    
    def initialize_roster_from_config(self, config_roster: List[str]) -> bool:
        """Initialize roster table from config.CLAN_ROSTER (migration helper)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if roster is already populated
                cursor.execute("SELECT COUNT(*) FROM roster WHERE is_active = TRUE")
                existing_count = cursor.fetchone()[0]
                
                if existing_count > 0:
                    logging.info(f"Roster already has {existing_count} players, skipping initialization")
                    return True
                
                # Add all config roster players
                for player in config_roster:
                    cursor.execute("""
                        INSERT INTO roster (player_name, added_by) 
                        VALUES (%s, %s)
                        ON CONFLICT (player_name) 
                        DO UPDATE SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                    """, (player, "system_migration"))
                
                conn.commit()
                logging.info(f"✅ Initialized roster with {len(config_roster)} players from config")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error initializing roster from config: {e}")
            return False

    # Team Management Methods
    def set_player_team(self, player_name: str, team: str) -> bool:
        """Set a player's team assignment."""
        valid_teams = ['Unassigned', 'Phantom Orbit', 'Moonlight Bootel']
        
        if team not in valid_teams:
            logging.error(f"Invalid team '{team}'. Valid teams: {valid_teams}")
            return False
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT id FROM roster WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
                if not cursor.fetchone():
                    logging.error(f"Player {player_name} not found in active roster")
                    return False
                
                # Update player's team
                cursor.execute("""
                    UPDATE roster 
                    SET team = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND is_active = TRUE
                """, (team, player_name))
                
                conn.commit()
                logging.info(f"✅ Set {player_name}'s team to {team}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error setting player team: {e}")
            return False
    
    def get_players_by_team(self, team: str = None) -> Dict[str, List[str]]:
        """Get players organized by team, or players from a specific team."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if team:
                    # Get players from specific team
                    cursor.execute("""
                        SELECT player_name FROM roster 
                        WHERE team = %s AND is_active = TRUE
                        ORDER BY player_name
                    """, (team,))
                    
                    return {team: [row[0] for row in cursor.fetchall()]}
                else:
                    # Get all players organized by team
                    cursor.execute("""
                        SELECT team, player_name FROM roster 
                        WHERE is_active = TRUE
                        ORDER BY team, player_name
                    """)
                    
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
    
    def get_team_roster(self, team: str) -> List[str]:
        """Get list of players in a specific team."""
        team_data = self.get_players_by_team(team)
        return team_data.get(team, [])
    
    def get_player_team(self, player_name: str) -> Optional[str]:
        """Get a player's current team assignment."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT team FROM roster 
                    WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
                result = cursor.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logging.error(f"❌ Error getting player team: {e}")
            return None

    # Nickname Management Methods
    def add_nickname(self, player_name: str, nickname: str) -> bool:
        """Add a nickname to a player's nickname list."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT nicknames FROM roster 
                    WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
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
                    UPDATE roster 
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND is_active = TRUE
                """, (json.dumps(updated_nicknames), player_name))
                
                conn.commit()
                logging.info(f"✅ Added nickname '{nickname}' to {player_name}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding nickname: {e}")
            return False
    
    def remove_nickname(self, player_name: str, nickname: str) -> bool:
        """Remove a nickname from a player's nickname list."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT nicknames FROM roster 
                    WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
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
                    UPDATE roster 
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND is_active = TRUE
                """, (json.dumps(updated_nicknames), player_name))
                
                conn.commit()
                logging.info(f"✅ Removed nickname '{nickname}' from {player_name}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing nickname: {e}")
            return False
    
    def get_player_nicknames(self, player_name: str) -> List[str]:
        """Get all nicknames for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT nicknames FROM roster 
                    WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
                result = cursor.fetchone()
                return result[0] if result and result[0] else []
                
        except Exception as e:
            logging.error(f"❌ Error getting player nicknames: {e}")
            return []
    
    def set_player_nicknames(self, player_name: str, nicknames: List[str]) -> bool:
        """Set all nicknames for a player (replaces existing nicknames)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists and is active
                cursor.execute("""
                    SELECT id FROM roster WHERE player_name = %s AND is_active = TRUE
                """, (player_name,))
                
                if not cursor.fetchone():
                    logging.error(f"Player {player_name} not found in active roster")
                    return False
                
                # Remove duplicates while preserving order
                unique_nicknames = []
                for nickname in nicknames:
                    if nickname not in unique_nicknames:
                        unique_nicknames.append(nickname)
                
                cursor.execute("""
                    UPDATE roster 
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND is_active = TRUE
                """, (json.dumps(unique_nicknames), player_name))
                
                conn.commit()
                logging.info(f"✅ Set nicknames for {player_name}: {unique_nicknames}")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error setting player nicknames: {e}")
            return False

    # Player Statistics Management Methods
    def update_player_stats(self, player_name: str, score: int, races: int, war_date: str) -> bool:
        """Update player statistics when a war is added."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player stats record exists
                cursor.execute("""
                    SELECT total_score, total_races, war_count 
                    FROM player_stats WHERE player_name = %s
                """, (player_name,))
                
                result = cursor.fetchone()
                if result:
                    # Player has existing stats - UPDATE
                    new_total_score = result[0] + score
                    new_total_races = result[1] + races
                    new_war_count = result[2] + 1
                    # Correct average calculation: total_score / war_count
                    new_average = round(new_total_score / new_war_count, 2)
                    
                    cursor.execute("""
                        UPDATE player_stats 
                        SET total_score = %s, total_races = %s, war_count = %s, 
                            average_score = %s, last_war_date = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE player_name = %s
                    """, (new_total_score, new_total_races, new_war_count, new_average, war_date, player_name))
                else:
                    # Player's first war - INSERT new record
                    # For first war: average = score / 1
                    average_score = round(score / 1, 2)
                    cursor.execute("""
                        INSERT INTO player_stats (player_name, total_score, total_races, war_count, average_score, last_war_date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (player_name, score, races, 1, average_score, war_date))
                
                conn.commit()
                logging.info(f"✅ Updated stats for {player_name}: +{score} points, +{races} races")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error updating player stats: {e}")
            return False
    
    def remove_player_stats(self, player_name: str, score: int, races: int) -> bool:
        """Remove player statistics when a war is removed."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get current stats
                cursor.execute("""
                    SELECT total_score, total_races, war_count 
                    FROM player_stats WHERE player_name = %s
                """, (player_name,))
                
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
                    WHERE player_name = %s
                """, (new_total_score, new_total_races, new_war_count, new_average, player_name))
                
                conn.commit()
                logging.info(f"✅ Removed stats for {player_name}: -{score} points, -{races} races")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing player stats: {e}")
            return False
    
    def get_player_statistics(self, player_name: str) -> Optional[Dict]:
        """Get comprehensive player statistics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT ps.total_score, ps.total_races, ps.war_count, ps.average_score, 
                           ps.last_war_date, ps.created_at, ps.updated_at,
                           r.team, r.nicknames, r.added_by
                    FROM player_stats ps
                    JOIN roster r ON ps.player_name = r.player_name
                    WHERE ps.player_name = %s AND r.is_active = TRUE
                """, (player_name,))
                
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
    
    def get_war_by_id(self, war_id: int) -> Optional[Dict]:
        """Get specific war details by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, war_date, race_count, players_data, created_at
                    FROM wars WHERE id = %s
                """, (war_id,))
                
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
    
    def get_all_wars(self, limit: int = None) -> List[Dict]:
        """Get all wars in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT id, war_date, race_count, players_data, created_at
                    FROM wars
                    ORDER BY created_at DESC
                """
                
                if limit:
                    query += " LIMIT %s"
                    cursor.execute(query, (limit,))
                else:
                    cursor.execute(query)
                
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
    
    def remove_war_by_id(self, war_id: int) -> bool:
        """Remove a war by ID and update player statistics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get war details first
                war = self.get_war_by_id(war_id)
                if not war:
                    logging.warning(f"War ID {war_id} not found")
                    return False
                
                # Update player stats by removing this war's contribution
                for result in war['results']:
                    player_name = result['name']
                    score = result['score']
                    races = war['race_count']
                    
                    # Resolve player name in case the war used a nickname
                    resolved_player = self.resolve_player_name(player_name)
                    if resolved_player:
                        self.remove_player_stats(resolved_player, score, races)
                
                # Delete the war
                cursor.execute("DELETE FROM wars WHERE id = %s", (war_id,))
                
                conn.commit()
                logging.info(f"✅ Removed war ID {war_id} and updated player stats")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error removing war: {e}")
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