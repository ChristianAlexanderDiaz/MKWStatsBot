#!/usr/bin/env python3
"""
Migration script to update war_count column to support fractional wars for substitutions.
Changes war_count from INTEGER to DECIMAL(5,3) to support values like 0.583 (7/12 races).
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
import logging

def migrate_fractional_wars():
    """Update war_count column to support decimal values."""
    try:
        db = DatabaseManager()
        
        print("🔄 Starting migration to support fractional war counts...")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check current column type
            cursor.execute("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'players' 
                AND column_name = 'war_count' 
                AND table_schema = 'public';
            """)
            
            current_type = cursor.fetchone()
            if current_type:
                print(f"Current war_count type: {current_type[0]}")
            
            # Update column type to DECIMAL(5,3)
            print("🔧 Updating war_count column to DECIMAL(5,3)...")
            cursor.execute("""
                ALTER TABLE players 
                ALTER COLUMN war_count TYPE DECIMAL(5,3);
            """)
            
            # Verify the change
            cursor.execute("""
                SELECT data_type, numeric_precision, numeric_scale
                FROM information_schema.columns 
                WHERE table_name = 'players' 
                AND column_name = 'war_count' 
                AND table_schema = 'public';
            """)
            
            new_type = cursor.fetchone()
            if new_type:
                print(f"✅ Updated war_count type: {new_type[0]} (precision: {new_type[1]}, scale: {new_type[2]})")
            
            conn.commit()
            print("✅ Migration completed successfully!")
            
            print("\n📋 What this enables:")
            print("- Support for partial war participation")
            print("- Example: Player(7): 44 = 7 races out of 12 = 0.583 wars")
            print("- Preserves per-war average calculation")
            print("- Backward compatible with existing integer values")
            
        return True
        
    except Exception as e:
        logging.error(f"❌ Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = migrate_fractional_wars()
    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)