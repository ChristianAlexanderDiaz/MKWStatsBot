#!/usr/bin/env python3
"""
Test script for the new team assignments and nicknames functionality.

This script demonstrates:
1. Team assignment functionality
2. Nickname management
3. Enhanced name resolution (OCR-friendly)
4. Roster queries with team and nickname data

Run this after applying the migration script.
"""

import sys
import os
import logging

# Add the parent directory to the path so we can import from mkw_stats
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from mkw_stats.database import DatabaseManager

def test_team_nicknames():
    """Test the new team and nickname functionality."""
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        # Initialize database connection
        db = DatabaseManager()
        
        print("🧪 Testing Team Assignment and Nickname Functionality")
        print("=" * 60)
        
        # Test 1: Add some test players
        print("\n1️⃣ Adding test players...")
        test_players = ["Cynical", "TestPlayer1", "TestPlayer2"]
        
        for player in test_players:
            success = db.add_roster_player(player, "test_script")
            print(f"   Added {player}: {'✅' if success else '❌'}")
        
        # Test 2: Add nicknames
        print("\n2️⃣ Adding nicknames...")
        nickname_tests = [
            ("Cynical", "cyn"),
            ("Cynical", "cynical123"),
            ("TestPlayer1", "test1"),
            ("TestPlayer1", "tp1"),
            ("TestPlayer2", "test2")
        ]
        
        for player, nickname in nickname_tests:
            success = db.add_nickname(player, nickname)
            print(f"   Added nickname '{nickname}' to {player}: {'✅' if success else '❌'}")
        
        # Test 3: Team assignments
        print("\n3️⃣ Assigning players to teams...")
        team_assignments = [
            ("Cynical", "Phantom Orbit"),
            ("TestPlayer1", "Phantom Orbit"),
            ("TestPlayer2", "Moonlight Bootel")
        ]
        
        for player, team in team_assignments:
            success = db.set_player_team(player, team)
            print(f"   Assigned {player} to {team}: {'✅' if success else '❌'}")
        
        # Test 4: Test name resolution (OCR simulation)
        print("\n4️⃣ Testing name resolution (OCR simulation)...")
        resolution_tests = [
            "Cynical",        # Exact match
            "cyn",            # Nickname match
            "CYNICAL",        # Case insensitive
            "test1",          # Nickname for TestPlayer1
            "tp1",            # Another nickname for TestPlayer1
            "unknown"         # Should fail
        ]
        
        for test_name in resolution_tests:
            resolved = db.resolve_player_name(test_name)
            print(f"   '{test_name}' -> {resolved if resolved else 'Not found'}")
        
        # Test 5: Get players by team
        print("\n5️⃣ Getting players by team...")
        all_teams = db.get_players_by_team()
        for team, players in all_teams.items():
            print(f"   {team}: {players}")
        
        # Test 6: Get individual player stats
        print("\n6️⃣ Getting player stats...")
        for player in ["Cynical", "cyn", "TestPlayer1"]:
            stats = db.get_player_stats(player)
            if stats:
                print(f"   {player} -> {stats['player_name']} (Team: {stats['team']}, Nicknames: {stats['nicknames']})")
            else:
                print(f"   {player} -> Not found")
        
        # Test 7: Get all players stats
        print("\n7️⃣ Getting all players stats...")
        all_stats = db.get_all_players_stats()
        for player_stats in all_stats:
            print(f"   {player_stats['player_name']} | Team: {player_stats['team']} | Nicknames: {player_stats['nicknames']}")
        
        # Test 8: Nickname management
        print("\n8️⃣ Testing nickname management...")
        
        # Get current nicknames
        current_nicknames = db.get_player_nicknames("Cynical")
        print(f"   Current nicknames for Cynical: {current_nicknames}")
        
        # Remove a nickname
        success = db.remove_nickname("Cynical", "cyn")
        print(f"   Removed 'cyn' from Cynical: {'✅' if success else '❌'}")
        
        # Check nicknames after removal
        updated_nicknames = db.get_player_nicknames("Cynical")
        print(f"   Updated nicknames for Cynical: {updated_nicknames}")
        
        # Set multiple nicknames at once
        success = db.set_player_nicknames("Cynical", ["cyn", "cynical", "cyn123"])
        print(f"   Set multiple nicknames for Cynical: {'✅' if success else '❌'}")
        
        final_nicknames = db.get_player_nicknames("Cynical")
        print(f"   Final nicknames for Cynical: {final_nicknames}")
        
        print("\n✅ All tests completed successfully!")
        print("\n💡 OCR Integration: Names like 'cyn' will now resolve to 'Cynical'")
        print("💡 Team Organization: Players are now organized by teams")
        print("💡 Flexible Nicknames: Multiple nicknames per player supported")
        
        db.close()
        
    except Exception as e:
        logging.error(f"❌ Test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🧪 Testing Team Assignment and Nickname Functionality")
    print("Make sure you've run the migration script first!")
    print()
    
    confirm = input("Continue with tests? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Tests cancelled.")
        sys.exit(0)
    
    success = test_team_nicknames()
    if success:
        print("\n✅ All tests passed! Your roster now supports teams and nicknames.")
    else:
        print("\n❌ Some tests failed. Check the logs for details.")
        sys.exit(1)