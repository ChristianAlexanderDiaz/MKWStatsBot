#!/usr/bin/env python3
"""
Database migration to add 'ally' to member_status constraint.
This migration updates the check constraint to include 'ally' as a valid member_status.
"""

import sys
import os
import logging

# Add the parent directory to sys.path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
from mkw_stats.config import DATABASE_URL

def migrate_add_ally_status():
    """Add 'ally' to member_status check constraint."""
    print("🔧 Starting ally status migration...")
    
    try:
        # Initialize database connection
        db = DatabaseManager(DATABASE_URL)
        print("✅ Database connection established")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check current constraint
            cursor.execute("""
                SELECT constraint_name, check_clause
                FROM information_schema.check_constraints
                WHERE constraint_schema = CURRENT_SCHEMA()
                AND constraint_name = 'check_member_status'
            """)
            
            result = cursor.fetchone()
            if not result:
                print("⚠️  member_status constraint not found, skipping migration")
                return True
                
            current_constraint = result[1] if result else ""
            print(f"📝 Current constraint: {current_constraint}")
            
            # Check if 'ally' is already in the constraint
            if "'ally'" in current_constraint:
                print("⚠️  'ally' already exists in member_status constraint, skipping migration")
                return True
            
            print("📝 Updating member_status constraint to include 'ally'...")
            
            # Drop existing constraint
            cursor.execute("""
                ALTER TABLE players 
                DROP CONSTRAINT check_member_status
            """)
            
            # Add updated constraint with 'ally'
            cursor.execute("""
                ALTER TABLE players 
                ADD CONSTRAINT check_member_status 
                CHECK (member_status IN ('member', 'trial', 'ally', 'kicked'))
            """)
            
            conn.commit()
            print("✅ member_status constraint updated successfully")
            
            # Verify the migration
            cursor.execute("""
                SELECT COUNT(*) as total_players,
                       COUNT(CASE WHEN member_status = 'member' THEN 1 END) as members,
                       COUNT(CASE WHEN member_status = 'trial' THEN 1 END) as trials,
                       COUNT(CASE WHEN member_status = 'ally' THEN 1 END) as allies,
                       COUNT(CASE WHEN member_status = 'kicked' THEN 1 END) as kicked
                FROM players
            """)
            
            result = cursor.fetchone()
            print(f"📊 Migration verification:")
            print(f"   Total players: {result[0]}")
            print(f"   Members: {result[1]}")
            print(f"   Trials: {result[2]}")
            print(f"   Allies: {result[3]}")
            print(f"   Kicked: {result[4]}")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        logging.error(f"Ally status migration error: {e}")
        return False

def main():
    """Run the migration."""
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 MKW Stats Bot - Add Ally Status Migration")
    print("=" * 50)
    
    success = migrate_add_ally_status()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("🎯 Next steps:")
        print("   1. 'ally' is now a valid member_status")
        print("   2. Test ally status functionality")
        print("   3. Update documentation if needed")
    else:
        print("\n❌ Migration failed!")
        print("🔍 Check logs for details")
        sys.exit(1)

if __name__ == "__main__":
    main()