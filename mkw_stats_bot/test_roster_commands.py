#!/usr/bin/env python3
"""
Test script to verify roster commands work correctly.
Tests !mkadd and !mkremove functionality without Discord.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mkw_stats.database import DatabaseManager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_roster_commands():
    print("🧪 Testing roster commands...")
    
    try:
        # Initialize database manager
        db = DatabaseManager()
        
        # Check database connection
        if not db.health_check():
            print("❌ Database connection failed")
            return False
        
        print("✅ Database connection successful")
        
        # Test 1: Show initial roster
        print("\n1️⃣ Testing !mkroster (initial state):")
        roster = db.get_roster_players()
        print(f"Current roster: {roster}")
        
        # Test 2: Add new player (!mkadd)
        print("\n2️⃣ Testing !mkadd NewPlayer:")
        success = db.add_roster_player("NewPlayer", "test_user")
        if success:
            print("✅ Successfully added NewPlayer")
        else:
            print("❌ Failed to add NewPlayer")
        
        # Show roster after adding
        roster = db.get_roster_players()
        print(f"Roster after adding: {roster}")
        
        # Test 3: Try to add duplicate player (!mkadd duplicate)
        print("\n3️⃣ Testing !mkadd NewPlayer (duplicate):")
        success = db.add_roster_player("NewPlayer", "test_user")
        if not success:
            print("✅ Correctly rejected duplicate player")
        else:
            print("❌ Should have rejected duplicate")
        
        # Test 4: Add another player
        print("\n4️⃣ Testing !mkadd SecondPlayer:")
        success = db.add_roster_player("SecondPlayer", "test_user")
        if success:
            print("✅ Successfully added SecondPlayer")
        else:
            print("❌ Failed to add SecondPlayer")
        
        # Show roster after adding second player
        roster = db.get_roster_players()
        print(f"Roster after adding second player: {roster}")
        
        # Test 5: Remove player (!mkremove)
        print("\n5️⃣ Testing !mkremove TestPlayer:")
        success = db.remove_roster_player("TestPlayer")
        if success:
            print("✅ Successfully removed TestPlayer")
        else:
            print("❌ Failed to remove TestPlayer")
        
        # Show roster after removing
        roster = db.get_roster_players()
        print(f"Roster after removing TestPlayer: {roster}")
        
        # Test 6: Try to remove non-existent player
        print("\n6️⃣ Testing !mkremove NonExistentPlayer:")
        success = db.remove_roster_player("NonExistentPlayer")
        if not success:
            print("✅ Correctly rejected removing non-existent player")
        else:
            print("❌ Should have rejected non-existent player")
        
        # Test 7: Final roster state
        print("\n7️⃣ Final roster state:")
        roster = db.get_roster_players()
        print(f"Final roster: {roster}")
        
        # Test 8: Database info
        print("\n8️⃣ Database info:")
        info = db.get_database_info()
        print(f"Database info: {info}")
        
        print("\n🎉 All roster command tests completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        return False
    
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    success = test_roster_commands()
    sys.exit(0 if success else 1)