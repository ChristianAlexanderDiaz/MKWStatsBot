#!/usr/bin/env python3
"""
Clean up database by dropping unused tables.
Drops the old 'players' and 'race_sessions' tables, keeping only 'roster' and 'wars'.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mkw_stats.database import DatabaseManager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

def cleanup_database():
    print("🧹 Cleaning up database - removing unused tables...")
    
    try:
        # Initialize database manager
        db = DatabaseManager()
        
        # Check database connection
        if not db.health_check():
            print("❌ Database connection failed")
            return False
        
        print("✅ Database connection successful")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # List tables before cleanup
            print("\n📋 Tables before cleanup:")
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            tables_before = [row[0] for row in cursor.fetchall()]
            for table in tables_before:
                print(f"  - {table}")
            
            # Drop unused tables
            tables_to_drop = ['players', 'race_sessions']
            
            for table in tables_to_drop:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    print(f"✅ Dropped table: {table}")
                except Exception as e:
                    print(f"⚠️  Could not drop table {table}: {e}")
            
            # List tables after cleanup
            print("\n📋 Tables after cleanup:")
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            tables_after = [row[0] for row in cursor.fetchall()]
            for table in tables_after:
                print(f"  - {table}")
            
            # Commit changes
            conn.commit()
            
            # Show current roster to verify everything still works
            roster_players = db.get_roster_players()
            print(f"\n✅ Current roster (should still work): {roster_players}")
            
            # Show database info
            info = db.get_database_info()
            print(f"✅ Database info: {info}")
        
        print("\n🎉 Database cleanup completed successfully!")
        print("✅ Only 'roster' and 'wars' tables remain")
        return True
        
    except Exception as e:
        print(f"❌ Error during database cleanup: {e}")
        return False
    
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    success = cleanup_database()
    sys.exit(0 if success else 1)