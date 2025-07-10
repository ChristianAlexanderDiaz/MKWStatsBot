#!/usr/bin/env python3
"""
Initialize simplified database with just roster and wars tables.
Adds a test player for testing !mkadd and !mkremove commands.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mkw_stats.database import DatabaseManager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

def main():
    print("🚀 Initializing simplified database...")
    
    try:
        # Initialize database manager
        db = DatabaseManager()
        
        # Check database connection
        if not db.health_check():
            print("❌ Database connection failed")
            return False
        
        print("✅ Database connection successful")
        
        # Add test player to roster
        success = db.add_roster_player("TestPlayer", "system")
        if success:
            print("✅ Added TestPlayer to roster")
        else:
            print("⚠️  TestPlayer may already exist in roster")
        
        # Check roster
        roster = db.get_roster_players()
        print(f"✅ Current roster: {roster}")
        
        # Get database info
        info = db.get_database_info()
        print(f"✅ Database info: {info}")
        
        print("\n🎉 Database initialization complete!")
        print("You can now test:")
        print("  !mkadd [playername] - to add players")
        print("  !mkremove [playername] - to remove players")
        print("  !mkroster - to view current roster")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False
    
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)