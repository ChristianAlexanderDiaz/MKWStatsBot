#!/usr/bin/env python3
"""
New simplified database system for Mario Kart clan stats.
Each player has:
- Main name
- List of nicknames 
- Score history (list of individual race scores)
- War count (calculated from scores ÷ 12)
- Average score per war
"""

import sqlite3
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
import os

class DatabaseManager:
    def __init__(self, db_path: str = None, init_fresh: bool = False):
        if db_path is None:
            from . import config
            db_path = config.DATABASE_PATH
        self.db_path = db_path
        if init_fresh:
            self.init_fresh_database()
        else:
            self.init_database()
    
    def get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
        
    def init_database(self):
        """Initialize the database tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if tables exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
                if cursor.fetchone():
                    # Tables exist, don't recreate
                    return
                
                # Create players table
                cursor.execute('''
                    CREATE TABLE players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        main_name TEXT UNIQUE NOT NULL,
                        nicknames TEXT DEFAULT '[]',  -- JSON array of nicknames
                        score_history TEXT DEFAULT '[]',  -- JSON array of scores
                        total_scores INTEGER DEFAULT 0,
                        war_count REAL DEFAULT 0.0,  -- Can be decimal (e.g., 1.5 wars)
                        average_score REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create race_sessions table for tracking when results were added
                cursor.execute('''
                    CREATE TABLE race_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_date TEXT NOT NULL,
                        race_count INTEGER NOT NULL,
                        players_data TEXT NOT NULL,  -- JSON of all players and scores
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                conn.commit()
                logging.info("Database tables created successfully")
                
        except Exception as e:
            logging.error(f"Error initializing database: {e}")
            raise
    
    def init_fresh_database(self):
        """Initialize a completely fresh database, dropping existing tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Drop existing tables if they exist (fresh start)
                cursor.execute("DROP TABLE IF EXISTS players")
                cursor.execute("DROP TABLE IF EXISTS race_sessions")
                
                # Create players table
                cursor.execute('''
                    CREATE TABLE players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        main_name TEXT UNIQUE NOT NULL,
                        nicknames TEXT DEFAULT '[]',  -- JSON array of nicknames
                        score_history TEXT DEFAULT '[]',  -- JSON array of scores
                        total_scores INTEGER DEFAULT 0,
                        war_count REAL DEFAULT 0.0,  -- Can be decimal (e.g., 1.5 wars)
                        average_score REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create race_sessions table for tracking when results were added
                cursor.execute('''
                    CREATE TABLE race_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_date TEXT NOT NULL,
                        race_count INTEGER NOT NULL,
                        players_data TEXT NOT NULL,  -- JSON of all players and scores
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                conn.commit()
                logging.info("Fresh database initialized successfully")
                
        except Exception as e:
            logging.error(f"Error initializing fresh database: {e}")
            raise
    
    def add_or_update_player(self, main_name: str, nicknames: List[str] = None) -> bool:
        """Add a new player or update existing player's nicknames."""
        try:
            if nicknames is None:
                nicknames = []
                
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if player exists
                cursor.execute("SELECT nicknames FROM players WHERE main_name = ?", (main_name,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing player's nicknames
                    existing_nicknames = json.loads(existing[0])
                    # Merge nicknames (avoid duplicates)
                    all_nicknames = list(set(existing_nicknames + nicknames))
                    
                    cursor.execute('''
                        UPDATE players 
                        SET nicknames = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE main_name = ?
                    ''', (json.dumps(all_nicknames), main_name))
                else:
                    # Add new player
                    cursor.execute('''
                        INSERT INTO players (main_name, nicknames)
                        VALUES (?, ?)
                    ''', (main_name, json.dumps(nicknames)))
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error(f"Error adding/updating player {main_name}: {e}")
            return False
    
    def resolve_player_name(self, name_or_nickname: str) -> Optional[str]:
        """Resolve a name or nickname to the main player name."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # First check if it's a main name
                cursor.execute("SELECT main_name FROM players WHERE main_name = ?", (name_or_nickname,))
                if cursor.fetchone():
                    return name_or_nickname
                
                # Check nicknames
                cursor.execute("SELECT main_name, nicknames FROM players")
                for main_name, nicknames_json in cursor.fetchall():
                    nicknames = json.loads(nicknames_json)
                    if name_or_nickname.lower() in [nick.lower() for nick in nicknames]:
                        return main_name
                
                return None  # Not found
                
        except Exception as e:
            logging.error(f"Error resolving player name {name_or_nickname}: {e}")
            return None
    
    def add_race_results(self, results: List[Dict], race_count: int = 12) -> bool:
        """
        Add race results for multiple players.
        results: [{'name': 'PlayerName', 'score': 85}, ...]
        race_count: number of races in this session (default 12)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Store the race session
                session_data = {
                    'race_count': race_count,
                    'results': results,
                    'timestamp': datetime.now().isoformat()
                }
                
                cursor.execute('''
                    INSERT INTO race_sessions (session_date, race_count, players_data)
                    VALUES (?, ?, ?)
                ''', (
                    datetime.now().strftime('%Y-%m-%d'),
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
                    cursor.execute('''
                        SELECT score_history, total_scores 
                        FROM players WHERE main_name = ?
                    ''', (main_name,))
                    
                    row = cursor.fetchone()
                    if row:
                        current_scores = json.loads(row[0])
                        current_total = row[1]
                    else:
                        current_scores = []
                        current_total = 0
                    
                    # Add new score
                    current_scores.append(score)
                    new_total = current_total + score
                    
                    # Calculate wars (1 war per race score)
                    total_races = len(current_scores)
                    war_count = total_races  # 1 war per score entry
                    
                    # Calculate average score per war
                    if war_count > 0:
                        average_score = new_total / war_count
                    else:
                        average_score = 0.0
                    
                    # Update player
                    cursor.execute('''
                        UPDATE players 
                        SET score_history = ?, 
                            total_scores = ?, 
                            war_count = ?, 
                            average_score = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE main_name = ?
                    ''', (
                        json.dumps(current_scores),
                        new_total,
                        war_count,
                        average_score,
                        main_name
                    ))
                
                conn.commit()
                logging.info(f"Added race results for {len(results)} players")
                return True
                
        except Exception as e:
            logging.error(f"Error adding race results: {e}")
            return False
    
    def get_player_stats(self, name_or_nickname: str) -> Optional[Dict]:
        """Get detailed stats for a player."""
        main_name = self.resolve_player_name(name_or_nickname)
        if not main_name:
            return None
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT main_name, nicknames, score_history, total_scores, 
                           war_count, average_score, updated_at
                    FROM players WHERE main_name = ?
                ''', (main_name,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return {
                    'main_name': row[0],
                    'nicknames': json.loads(row[1]),
                    'score_history': json.loads(row[2]),
                    'total_scores': row[3],
                    'war_count': row[4],
                    'average_score': row[5],
                    'total_races': len(json.loads(row[2])),
                    'last_updated': row[6]
                }
                
        except Exception as e:
            logging.error(f"Error getting player stats: {e}")
            return None
    
    def get_all_players_stats(self) -> List[Dict]:
        """Get stats for all players, sorted by average score."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT main_name, nicknames, score_history, total_scores, 
                           war_count, average_score, updated_at
                    FROM players 
                    WHERE war_count > 0
                    ORDER BY average_score DESC
                ''')
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'main_name': row[0],
                        'nicknames': json.loads(row[1]),
                        'score_history': json.loads(row[2]),
                        'total_scores': row[3],
                        'war_count': row[4],
                        'average_score': row[5],
                        'total_races': len(json.loads(row[2])),
                        'last_updated': row[6]
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"Error getting all player stats: {e}")
            return []
    
    def get_recent_sessions(self, limit: int = 5) -> List[Dict]:
        """Get recent race sessions."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT session_date, race_count, players_data, created_at
                    FROM race_sessions
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    session_data = json.loads(row[2])
                    results.append({
                        'session_date': row[0],
                        'race_count': row[1],
                        'results': session_data.get('results', []),
                        'created_at': row[3]
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"Error getting recent sessions: {e}")
            return []
    
    def get_database_info(self) -> Dict:
        """Get database information."""
        try:
            info = {
                'database_path': os.path.abspath(self.db_path),
                'file_size_kb': 0,
                'player_count': 0,
                'session_count': 0
            }
            
            if os.path.exists(self.db_path):
                info['file_size_kb'] = os.path.getsize(self.db_path) / 1024
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("SELECT COUNT(*) FROM players")
                    info['player_count'] = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM race_sessions")
                    info['session_count'] = cursor.fetchone()[0]
            
            return info
            
        except Exception as e:
            logging.error(f"Error getting database info: {e}")
            return {'error': str(e)}

# Example usage and testing
if __name__ == "__main__":
    # Create test database
    db = MarioKartDatabase("test_mario_kart.db")
    
    # Add players with nicknames
    db.add_or_update_player("Cynical", ["Cyn", "Christian"])
    db.add_or_update_player("rx", ["Astral", "Astralixv"])
    db.add_or_update_player("Corbs", ["Corby"])
    
    # Add some test race results
    test_results = [
        {'name': 'Cynical', 'score': 95},
        {'name': 'Cyn', 'score': 88},  # Should resolve to Cynical
        {'name': 'rx', 'score': 81},
        {'name': 'Astral', 'score': 79},  # Should resolve to rx
        {'name': 'Corbs', 'score': 68},
        {'name': 'Quick', 'score': 70}  # New player
    ]
    
    db.add_race_results(test_results, race_count=12)
    
    # Test queries
    print("=== Player Stats ===")
    cynical_stats = db.get_player_stats("Cynical")
    if cynical_stats:
        print(f"Cynical: {cynical_stats}")
    
    print("\n=== All Players ===")
    all_stats = db.get_all_players_stats()
    for player in all_stats:
        print(f"{player['main_name']}: Avg {player['average_score']:.1f}, Wars: {player['war_count']:.1f}")
    
    print(f"\n=== Database Info ===")
    info = db.get_database_info()
    print(info) 