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
                        WHERE table_schema = 'public' AND table_name = 'players'
                    );
                """)
                
                if cursor.fetchone()[0]:
                    # Tables exist, don't recreate
                    logging.info("✅ PostgreSQL tables already exist")
                    return
                
                # Create players table with PostgreSQL-specific features
                cursor.execute("""
                    CREATE TABLE players (
                        id SERIAL PRIMARY KEY,
                        main_name VARCHAR(100) UNIQUE NOT NULL,
                        nicknames JSONB DEFAULT '[]'::jsonb,
                        score_history JSONB DEFAULT '[]'::jsonb,
                        total_scores INTEGER DEFAULT 0,
                        war_count DECIMAL(10,2) DEFAULT 0.0,
                        average_score DECIMAL(10,2) DEFAULT 0.0,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for better performance
                cursor.execute("""
                    CREATE INDEX idx_players_main_name ON players(main_name);
                    CREATE INDEX idx_players_average_score ON players(average_score DESC);
                    CREATE INDEX idx_players_war_count ON players(war_count DESC);
                    CREATE INDEX idx_players_nicknames ON players USING GIN(nicknames);
                """)
                
                # Create race_sessions table
                cursor.execute("""
                    CREATE TABLE race_sessions (
                        id SERIAL PRIMARY KEY,
                        session_date DATE NOT NULL,
                        race_count INTEGER NOT NULL,
                        players_data JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for race_sessions
                cursor.execute("""
                    CREATE INDEX idx_race_sessions_date ON race_sessions(session_date DESC);
                    CREATE INDEX idx_race_sessions_created ON race_sessions(created_at DESC);
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
                    
                    CREATE TRIGGER update_players_updated_at 
                        BEFORE UPDATE ON players 
                        FOR EACH ROW 
                        EXECUTE FUNCTION update_updated_at_column();
                        
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
        """Add a new player or update existing player's nicknames."""
        try:
            if nicknames is None:
                nicknames = []
                
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if player exists
                cursor.execute("SELECT nicknames FROM players WHERE main_name = %s", (main_name,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing player's nicknames
                    existing_nicknames = existing[0] if existing[0] else []
                    # Merge nicknames (avoid duplicates)
                    all_nicknames = list(set(existing_nicknames + nicknames))
                    
                    cursor.execute("""
                        UPDATE players 
                        SET nicknames = %s
                        WHERE main_name = %s
                    """, (json.dumps(all_nicknames), main_name))
                else:
                    # Add new player
                    cursor.execute("""
                        INSERT INTO players (main_name, nicknames)
                        VALUES (%s, %s)
                    """, (main_name, json.dumps(nicknames)))
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding/updating player {main_name}: {e}")
            return False
    
    def resolve_player_name(self, name_or_nickname: str) -> Optional[str]:
        """Resolve a name or nickname to the main player name."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # First check if it's a main name
                cursor.execute("SELECT main_name FROM players WHERE main_name = %s", (name_or_nickname,))
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                # Check nicknames using PostgreSQL JSONB functionality
                cursor.execute("""
                    SELECT main_name FROM players 
                    WHERE nicknames @> %s
                """, (json.dumps([name_or_nickname]),))
                
                result = cursor.fetchone()
                if result:
                    return result[0]
                
                # Case-insensitive search as fallback
                cursor.execute("""
                    SELECT main_name, nicknames FROM players
                """)
                for main_name, nicknames_json in cursor.fetchall():
                    nicknames = nicknames_json if nicknames_json else []
                    if name_or_nickname.lower() in [nick.lower() for nick in nicknames]:
                        return main_name
                
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
                
                # Store the race session
                session_data = {
                    'race_count': race_count,
                    'results': results,
                    'timestamp': datetime.now().isoformat()
                }
                
                cursor.execute("""
                    INSERT INTO race_sessions (session_date, race_count, players_data)
                    VALUES (%s, %s, %s)
                """, (
                    datetime.now().date(),
                    race_count,
                    json.dumps(session_data)
                ))
                
                # Update each player's data
                for result in results:
                    name = result['name']
                    score = result['score']
                    
                    # Resolve to main name
                    main_name = self.resolve_player_name(name)
                    if not main_name:
                        # Add as new player if not found
                        self.add_or_update_player(name)
                        main_name = name
                    
                    # Get current player data
                    cursor.execute("""
                        SELECT score_history, total_scores 
                        FROM players WHERE main_name = %s
                    """, (main_name,))
                    
                    row = cursor.fetchone()
                    if row:
                        current_scores = row[0] if row[0] else []
                        current_total = row[1] if row[1] else 0
                    else:
                        current_scores = []
                        current_total = 0
                    
                    # Add new score
                    current_scores.append(score)
                    new_total = current_total + score
                    
                    # Calculate wars (1 war per score entry)
                    total_races = len(current_scores)
                    war_count = total_races  # 1 war per score entry
                    
                    # Calculate average score per war
                    if war_count > 0:
                        average_score = new_total / war_count
                    else:
                        average_score = 0.0
                    
                    # Update player using PostgreSQL UPSERT
                    cursor.execute("""
                        INSERT INTO players (main_name, score_history, total_scores, war_count, average_score)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (main_name) 
                        DO UPDATE SET 
                            score_history = EXCLUDED.score_history,
                            total_scores = EXCLUDED.total_scores,
                            war_count = EXCLUDED.war_count,
                            average_score = EXCLUDED.average_score
                    """, (
                        main_name,
                        json.dumps(current_scores),
                        new_total,
                        war_count,
                        average_score
                    ))
                
                conn.commit()
                logging.info(f"✅ Added race results for {len(results)} players")
                return True
                
        except Exception as e:
            logging.error(f"❌ Error adding race results: {e}")
            return False
    
    def get_player_stats(self, name_or_nickname: str) -> Optional[Dict]:
        """Get detailed stats for a player."""
        main_name = self.resolve_player_name(name_or_nickname)
        if not main_name:
            return None
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT main_name, nicknames, score_history, total_scores, 
                           war_count, average_score, updated_at
                    FROM players WHERE main_name = %s
                """, (main_name,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                score_history = row[2] if row[2] else []
                
                return {
                    'main_name': row[0],
                    'nicknames': row[1] if row[1] else [],
                    'score_history': score_history,
                    'total_scores': row[3],
                    'war_count': float(row[4]),
                    'average_score': float(row[5]),
                    'total_races': len(score_history),
                    'last_updated': row[6].isoformat() if row[6] else None
                }
                
        except Exception as e:
            logging.error(f"❌ Error getting player stats: {e}")
            return None
    
    def get_all_players_stats(self) -> List[Dict]:
        """Get stats for all players, sorted by average score."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT main_name, nicknames, score_history, total_scores, 
                           war_count, average_score, updated_at
                    FROM players 
                    WHERE war_count > 0
                    ORDER BY average_score DESC
                """)
                
                results = []
                for row in cursor.fetchall():
                    score_history = row[2] if row[2] else []
                    results.append({
                        'main_name': row[0],
                        'nicknames': row[1] if row[1] else [],
                        'score_history': score_history,
                        'total_scores': row[3],
                        'war_count': float(row[4]),
                        'average_score': float(row[5]),
                        'total_races': len(score_history),
                        'last_updated': row[6].isoformat() if row[6] else None
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"❌ Error getting all player stats: {e}")
            return []
    
    def get_recent_sessions(self, limit: int = 5) -> List[Dict]:
        """Get recent race sessions."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT session_date, race_count, players_data, created_at
                    FROM race_sessions
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                
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
            logging.error(f"❌ Error getting recent sessions: {e}")
            return []
    
    def get_database_info(self) -> Dict:
        """Get database information."""
        try:
            info = {
                'database_type': 'PostgreSQL',
                'connection_host': self.connection_params.get('host'),
                'connection_database': self.connection_params.get('database'),
                'player_count': 0,
                'session_count': 0,
                'total_wars': 0
            }
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get player count
                cursor.execute("SELECT COUNT(*) FROM players")
                info['player_count'] = cursor.fetchone()[0]
                
                # Get session count
                cursor.execute("SELECT COUNT(*) FROM race_sessions")
                info['session_count'] = cursor.fetchone()[0]
                
                # Get total wars across all players
                cursor.execute("SELECT COALESCE(SUM(war_count), 0) FROM players")
                info['total_wars'] = float(cursor.fetchone()[0])
                
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
        
        # Test adding players
        db.add_or_update_player("Cynical", ["Cyn", "Christian"])
        db.add_or_update_player("rx", ["Astral", "Astralixv"])
        
        # Test adding results
        test_results = [
            {'name': 'Cynical', 'score': 95},
            {'name': 'Cyn', 'score': 88},  # Should resolve to Cynical
            {'name': 'rx', 'score': 81}
        ]
        
        success = db.add_race_results(test_results)
        print(f"✅ Race results added: {success}")
        
        # Test queries
        stats = db.get_player_stats("Cynical")
        if stats:
            print(f"✅ Cynical stats: Avg {stats['average_score']:.1f}, Wars: {stats['war_count']}")
        
        # Test database info
        info = db.get_database_info()
        print(f"✅ Database info: {info}")
        
        db.close()
        
    else:
        print("❌ PostgreSQL connection failed")