#!/usr/bin/env python3
"""
Database migration script to add player_stats table for tracking individual player statistics.

This script adds:
1. player_stats table with foreign key to roster table
2. Index on player_name for efficient queries
3. Automatic update trigger for updated_at column

Run this script once to migrate your existing database.
"""

import psycopg2
import psycopg2.pool
import logging
import sys
import os

# Add the parent directory to the path so we can import from mkw_stats
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from mkw_stats.database import DatabaseManager

def migrate_database():
    """Apply the migration to add player_stats table."""
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        # Initialize database connection
        db = DatabaseManager()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if migration has already been applied
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = 'player_stats'
                )
            """)
            
            if cursor.fetchone()[0]:
                logging.info("Migration already applied - player_stats table exists")
                return True
            
            logging.info("Starting database migration...")
            
            # Step 1: Create the player_stats table
            logging.info("Creating player_stats table...")
            cursor.execute("""
                CREATE TABLE player_stats (
                    id SERIAL PRIMARY KEY,
                    player_name VARCHAR(100) REFERENCES roster(player_name) ON DELETE CASCADE,
                    total_score INTEGER DEFAULT 0,
                    total_races INTEGER DEFAULT 0,
                    war_count INTEGER DEFAULT 0,
                    average_score DECIMAL(5,2) DEFAULT 0.0,
                    last_war_date DATE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Step 2: Create index for efficient player lookups
            logging.info("Creating index on player_name...")
            cursor.execute("""
                CREATE INDEX idx_player_stats_name ON player_stats(player_name)
            """)
            
            # Step 3: Create trigger to automatically update updated_at timestamp
            logging.info("Creating updated_at trigger...")
            cursor.execute("""
                CREATE TRIGGER update_player_stats_updated_at 
                    BEFORE UPDATE ON player_stats 
                    FOR EACH ROW 
                    EXECUTE FUNCTION update_updated_at_column()
            """)
            
            # Step 4: Initialize player_stats for existing roster players
            logging.info("Initializing player stats for existing roster players...")
            cursor.execute("""
                INSERT INTO player_stats (player_name)
                SELECT player_name FROM roster WHERE is_active = TRUE
            """)
            
            # Step 5: Verify the changes
            cursor.execute("""
                SELECT COUNT(*) FROM player_stats
            """)
            
            stats_count = cursor.fetchone()[0]
            logging.info(f"Initialized stats for {stats_count} players")
            
            # Step 6: Show sample data
            cursor.execute("""
                SELECT ps.player_name, ps.total_score, ps.war_count, r.team
                FROM player_stats ps
                JOIN roster r ON ps.player_name = r.player_name
                ORDER BY ps.player_name
                LIMIT 5
            """)
            
            sample_data = cursor.fetchall()
            logging.info(f"Sample player stats: {sample_data}")
            
            conn.commit()
            logging.info("✅ Migration completed successfully!")
            
            return True
            
    except Exception as e:
        logging.error(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Starting database migration: Add player_stats table")
    print("This will add:")
    print("- player_stats table with foreign key to roster")
    print("- Index on player_name for efficient queries")
    print("- Automatic updated_at trigger")
    print("- Initialize stats for existing roster players")
    print()
    
    confirm = input("Continue with migration? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Migration cancelled.")
        sys.exit(0)
    
    success = migrate_database()
    if success:
        print("✅ Migration completed successfully!")
        print("Your database now has player statistics tracking.")
        print("You can now use: !mkaddwar, !mkremovewar, !mklistwarhistory")
    else:
        print("❌ Migration failed. Check the logs for details.")
        sys.exit(1)