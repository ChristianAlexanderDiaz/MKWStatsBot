#!/usr/bin/env python3
"""
Database migration to add member_status column to players table.
This migration adds a member_status field with options: member, trial, kicked.
Default value is 'member' for existing players.
"""

import sys
import os
import logging

# Add the parent directory to sys.path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
from mkw_stats.config import DATABASE_URL

def migrate_add_member_status():
    """Add member_status column to players table."""
    print("🔧 Starting member_status column migration...")
    
    try:
        # Initialize database connection
        db = DatabaseManager(DATABASE_URL)
        print("✅ Database connection established")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if member_status column already exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'players' AND column_name = 'member_status'
            """)
            
            if cursor.fetchone():
                print("⚠️  member_status column already exists, skipping migration")
                return True
            
            print("📝 Adding member_status column to players table...")
            
            # Add member_status column with default value 'member'
            cursor.execute("""
                ALTER TABLE players 
                ADD COLUMN member_status VARCHAR(10) DEFAULT 'member'
            """)
            
            # Add check constraint to ensure valid values
            cursor.execute("""
                ALTER TABLE players 
                ADD CONSTRAINT check_member_status 
                CHECK (member_status IN ('member', 'trial', 'kicked'))
            """)
            
            # Update all existing players to have 'member' status (redundant but explicit)
            cursor.execute("""
                UPDATE players 
                SET member_status = 'member' 
                WHERE member_status IS NULL
            """)
            
            # Create index for efficient member status queries
            cursor.execute("""
                CREATE INDEX idx_players_member_status ON players(member_status, guild_id)
            """)
            
            conn.commit()
            print("✅ member_status column added successfully")
            
            # Verify the migration
            cursor.execute("""
                SELECT COUNT(*) as total_players,
                       COUNT(CASE WHEN member_status = 'member' THEN 1 END) as members,
                       COUNT(CASE WHEN member_status = 'trial' THEN 1 END) as trials,
                       COUNT(CASE WHEN member_status = 'kicked' THEN 1 END) as kicked
                FROM players
            """)
            
            result = cursor.fetchone()
            print(f"📊 Migration verification:")
            print(f"   Total players: {result[0]}")
            print(f"   Members: {result[1]}")
            print(f"   Trials: {result[2]}")
            print(f"   Kicked: {result[3]}")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        logging.error(f"Member status migration error: {e}")
        return False

def main():
    """Run the migration."""
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 MKW Stats Bot - Member Status Migration")
    print("=" * 50)
    
    success = migrate_add_member_status()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("🎯 Next steps:")
        print("   1. Update bot commands to use member_status")
        print("   2. Test new member status functionality")
        print("   3. Update documentation")
    else:
        print("\n❌ Migration failed!")
        print("🔍 Check logs for details")
        sys.exit(1)

if __name__ == "__main__":
    main()