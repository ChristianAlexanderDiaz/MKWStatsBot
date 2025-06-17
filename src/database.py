import os
import logging
from typing import List, Tuple, Dict, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor
import sqlite3
from src import config

class DatabaseManager:
    def __init__(self, connection_type: str = "sqlite"):
        """Initialize database connection.
        
        Args:
            connection_type: "sqlite" or "postgres"
        """
        self.connection_type = connection_type
        
        if connection_type == "postgres":
            # Get PostgreSQL connection URL from environment
            self.db_url = os.getenv('DATABASE_URL')
            if not self.db_url:
                raise ValueError("DATABASE_URL environment variable not set")
            self.init_postgres_database()
        else:
            self.db_path = config.DATABASE_PATH
            self.init_sqlite_database()
    
    def get_connection(self):
        """Get database connection based on type."""
        if self.connection_type == "postgres":
            return psycopg2.connect(self.db_url)
        else:
            return sqlite3.connect(self.db_path)
    
    def init_postgres_database(self):
        """Initialize PostgreSQL database with required tables."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Create players table
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS players (
                            id SERIAL PRIMARY KEY,
                            name TEXT UNIQUE NOT NULL,
                            total_score INTEGER DEFAULT 0,
                            race_count INTEGER DEFAULT 0,
                            average_score FLOAT DEFAULT 0.0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Create race_results table
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS race_results (
                            id SERIAL PRIMARY KEY,
                            player_name TEXT NOT NULL REFERENCES players(name),
                            score INTEGER NOT NULL,
                            race_date TEXT NOT NULL,
                            race_count INTEGER NOT NULL,
                            position INTEGER,
                            message_id TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Create pending_confirmations table
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS pending_confirmations (
                            message_id TEXT PRIMARY KEY,
                            data JSONB NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                conn.commit()
                logging.info("PostgreSQL database initialized")
                
        except Exception as e:
            logging.error(f"Error initializing PostgreSQL database: {e}")
            raise
    
    def init_sqlite_database(self):
        """Initialize SQLite database with required tables."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create players table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        total_score INTEGER DEFAULT 0,
                        race_count INTEGER DEFAULT 0,
                        average_score REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create race_results table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS race_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT NOT NULL,
                        score INTEGER NOT NULL,
                        race_date TEXT NOT NULL,
                        race_count INTEGER NOT NULL,
                        position INTEGER,
                        message_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (player_name) REFERENCES players (name)
                    )
                ''')
                
                conn.commit()
                logging.info("SQLite database initialized")
                
        except Exception as e:
            logging.error(f"Error initializing SQLite database: {e}")
            raise
    
    def add_player(self, name: str) -> bool:
        """Add a new player if they don't exist."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Insert player if not exists
                if self.connection_type == "postgres":
                    cursor.execute('''
                        INSERT INTO players (name)
                        VALUES (%s)
                        ON CONFLICT (name) DO NOTHING
                    ''', (name,))
                else:
                    cursor.execute('''
                        INSERT OR IGNORE INTO players (name)
                        VALUES (?)
                    ''', (name,))
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error(f"Error adding player: {e}")
            return False
    
    def add_race_results(self, results: List[Dict]) -> bool:
        """Add race results for multiple players."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for result in results:
                    # Add player if not exists
                    self.add_player(result['name'])
                    
                    # Insert race result
                    if self.connection_type == "postgres":
                        cursor.execute('''
                            INSERT INTO race_results 
                            (player_name, score, race_date, race_count, position, message_id)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (
                            result['name'],
                            result['score'],
                            result['race_date'],
                            result['race_count'],
                            result.get('position'),
                            result.get('message_id')
                        ))
                    else:
                        cursor.execute('''
                            INSERT INTO race_results 
                            (player_name, score, race_date, race_count, position, message_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            result['name'],
                            result['score'],
                            result['race_date'],
                            result['race_count'],
                            result.get('position'),
                            result.get('message_id')
                        ))
                
                # Update player statistics
                for result in results:
                    self.update_player_stats(result['name'])
                
                conn.commit()
                logging.info(f"Added {len(results)} race results")
                return True
                
        except Exception as e:
            logging.error(f"Error adding race results: {e}")
            return False
    
    def update_player_stats(self, player_name: str):
        """Update player's total score, race count, and average."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Calculate new stats
                if self.connection_type == "postgres":
                    cursor.execute('''
                        UPDATE players 
                        SET 
                            total_score = subquery.total,
                            race_count = subquery.races,
                            average_score = CAST(subquery.total AS FLOAT) / subquery.races
                        FROM (
                            SELECT 
                                SUM(score) as total,
                                COUNT(*) as races
                            FROM race_results
                            WHERE player_name = %s
                        ) as subquery
                        WHERE name = %s
                    ''', (player_name, player_name))
                else:
                    cursor.execute('''
                        UPDATE players 
                        SET 
                            total_score = (
                                SELECT SUM(score)
                                FROM race_results
                                WHERE player_name = ?
                            ),
                            race_count = (
                                SELECT COUNT(*)
                                FROM race_results
                                WHERE player_name = ?
                            ),
                            average_score = (
                                SELECT CAST(SUM(score) AS FLOAT) / COUNT(*)
                                FROM race_results
                                WHERE player_name = ?
                            )
                        WHERE name = ?
                    ''', (player_name, player_name, player_name, player_name))
                
                conn.commit()
                
        except Exception as e:
            logging.error(f"Error updating player stats: {e}")
    
    def get_player_stats(self, player_name: str) -> Optional[Dict]:
        """Get statistics for a specific player."""
        try:
            with self.get_connection() as conn:
                if self.connection_type == "postgres":
                    cursor = conn.cursor(cursor_factory=DictCursor)
                else:
                    cursor = conn.cursor()
                    
                cursor.execute('''
                    SELECT name, total_score, race_count, average_score
                    FROM players
                    WHERE name = ?
                ''', (player_name,))
                
                row = cursor.fetchone()
                if row:
                    if self.connection_type == "postgres":
                        return dict(row)
                    else:
                        return {
                            'name': row[0],
                            'total_score': row[1],
                            'race_count': row[2],
                            'average_score': row[3]
                        }
                return None
                
        except Exception as e:
            logging.error(f"Error getting player stats: {e}")
            return None
    
    def get_all_players_stats(self) -> List[Dict]:
        """Get statistics for all players, sorted by average score."""
        try:
            with self.get_connection() as conn:
                if self.connection_type == "postgres":
                    cursor = conn.cursor(cursor_factory=DictCursor)
                else:
                    cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT name, total_score, race_count, average_score
                    FROM players
                    WHERE race_count > 0
                    ORDER BY average_score DESC
                ''')
                
                rows = cursor.fetchall()
                if self.connection_type == "postgres":
                    return [dict(row) for row in rows]
                else:
                    return [{
                        'name': row[0],
                        'total_score': row[1],
                        'race_count': row[2],
                        'average_score': row[3]
                    } for row in rows]
                
        except Exception as e:
            logging.error(f"Error getting all player stats: {e}")
            return []
    
    def store_pending_confirmation(self, message_id: str, extracted_data: str):
        """Store data pending confirmation."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO pending_confirmations (message_id, data)
                    VALUES (%s, %s)
                ''', (message_id, extracted_data))
                conn.commit()
        except Exception as e:
            logging.error(f"Error storing pending confirmation: {e}")
    
    def get_pending_confirmation(self, message_id: str) -> Optional[str]:
        """Get pending confirmation data."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT data FROM pending_confirmations
                    WHERE message_id = %s
                ''', (message_id,))
                
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logging.error(f"Error getting pending confirmation: {e}")
            return None
    
    def remove_pending_confirmation(self, message_id: str):
        """Remove pending confirmation data."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM pending_confirmations WHERE message_id = %s
                ''', (message_id,))
                conn.commit()
        except Exception as e:
            logging.error(f"Error removing pending confirmation: {e}") 