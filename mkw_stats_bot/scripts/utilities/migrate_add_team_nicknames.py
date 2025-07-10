#!/usr/bin/env python3
"""
Database migration script to add team assignments and nicknames to the roster table.

This script adds:
1. team_type enum with values: 'Unassigned', 'Phantom Orbit', 'Moonlight Bootel'
2. team column with default 'Unassigned' 
3. nicknames column as JSONB array
4. Indexes for efficient querying

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
    """Apply the migration to add team and nicknames columns."""
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        # Initialize database connection
        db = DatabaseManager()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if migration has already been applied
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'roster' AND column_name = 'team'
            """)
            
            if cursor.fetchone():
                logging.info("Migration already applied - team column exists")
                return True
            
            logging.info("Starting database migration...")
            
            # Step 1: Create the team enum type
            logging.info("Creating team_type enum...")
            cursor.execute("""
                CREATE TYPE team_type AS ENUM ('Unassigned', 'Phantom Orbit', 'Moonlight Bootel')
            """)
            
            # Step 2: Add team column with default 'Unassigned'
            logging.info("Adding team column...")
            cursor.execute("""
                ALTER TABLE roster 
                ADD COLUMN team team_type DEFAULT 'Unassigned' NOT NULL
            """)
            
            # Step 3: Add nicknames column as JSONB array
            logging.info("Adding nicknames column...")
            cursor.execute("""
                ALTER TABLE roster 
                ADD COLUMN nicknames JSONB DEFAULT '[]' NOT NULL
            """)
            
            # Step 4: Create indexes for efficient querying
            logging.info("Creating indexes...")
            cursor.execute("""
                CREATE INDEX idx_roster_team ON roster(team)
            """)
            
            cursor.execute("""
                CREATE INDEX idx_roster_nicknames ON roster USING GIN(nicknames)
            """)
            
            # Step 5: Verify the changes
            cursor.execute("""
                SELECT column_name, data_type, column_default 
                FROM information_schema.columns 
                WHERE table_name = 'roster' AND column_name IN ('team', 'nicknames')
                ORDER BY column_name
            """)
            
            new_columns = cursor.fetchall()
            logging.info(f"New columns added: {new_columns}")
            
            # Step 6: Show current roster with new columns
            cursor.execute("""
                SELECT player_name, team, nicknames, is_active
                FROM roster
                ORDER BY player_name
                LIMIT 10
            """)
            
            sample_data = cursor.fetchall()
            logging.info(f"Sample roster data with new columns: {sample_data}")
            
            conn.commit()
            logging.info("✅ Migration completed successfully!")
            
            return True
            
    except Exception as e:
        logging.error(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Starting database migration: Add team assignments and nicknames")
    print("This will add:")
    print("- team_type enum: 'Unassigned', 'Phantom Orbit', 'Moonlight Bootel'")
    print("- team column (default: 'Unassigned')")
    print("- nicknames JSONB column")
    print("- Indexes for efficient querying")
    print()
    
    confirm = input("Continue with migration? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Migration cancelled.")
        sys.exit(0)
    
    success = migrate_database()
    if success:
        print("✅ Migration completed successfully!")
        print("Your roster now supports team assignments and nicknames.")
    else:
        print("❌ Migration failed. Check the logs for details.")
        sys.exit(1)