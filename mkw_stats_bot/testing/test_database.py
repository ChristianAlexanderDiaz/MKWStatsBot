#!/usr/bin/env python3
"""
Database Testing Tool

Test database operations and simulate race result storage.
Usage: python testing/test_database.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mkw_stats.database import DatabaseManager
import json

def test_database_operations():
    """Test basic database operations."""
    print("🗃️  Testing Database Operations")
    print("=" * 40)
    
    # Initialize database
    db = DatabaseManager()
    
    # Test database info
    info = db.get_database_info()
    print(f"📊 Database Info:")
    print(f"  Location: {info['database_path']}")
    print(f"  Size: {info['file_size_kb']:.1f} KB")
    print(f"  Players: {info['player_count']}")
    print(f"  Sessions: {info['session_count']}")
    print()
    
    # Test player resolution
    print("🔍 Testing Player Name Resolution:")
    test_names = ["Cynical", "Cyn", "rx", "Astral", "Unknown"]
    for name in test_names:
        resolved = db.resolve_player_name(name)
        print(f"  '{name}' → {resolved or 'NOT FOUND'}")
    print()
    
    # Show all players
    print("👥 All Players in Database:")
    stats = db.get_all_players_stats()
    if stats:
        for player in stats[:10]:  # Show first 10
            nicknames = ", ".join(player['nicknames']) if player['nicknames'] else "None"
            print(f"  {player['main_name']}: {player['war_count']} wars, {player['average_score']:.1f} avg (nicknames: {nicknames})")
    else:
        print("  No players found. Run 'python management/setup_players.py' first.")
    print()

def simulate_race_results():
    """Simulate adding race results for testing."""
    print("🏁 Simulating Race Results")
    print("=" * 30)
    
    db = DatabaseManager()
    
    # Sample race results
    test_results = [
        {'name': 'Cynical', 'score': 85},
        {'name': 'rx', 'score': 92},
        {'name': 'Corbs', 'score': 78},
        {'name': 'Quick', 'score': 88},
        {'name': 'DEMISE', 'score': 95},
        {'name': 'Jake', 'score': 82}
    ]
    
    print("📊 Adding test results:")
    for result in test_results:
        print(f"  {result['name']}: {result['score']}")
    
    # Add to database
    success = db.add_race_results(test_results)
    
    if success:
        print("✅ Results added successfully!")
        
        # Show updated stats
        print("\n📈 Updated Player Stats:")
        for result in test_results:
            stats = db.get_player_stats(result['name'])
            if stats:
                print(f"  {stats['player_name']}: {stats['war_count']} wars, {stats['total_score']} total, {stats['average_score']:.1f} avg")
    else:
        print("❌ Failed to add results")

def test_nickname_management():
    """Test nickname management functions."""
    print("🏷️  Testing Nickname Management")
    print("=" * 35)
    
    db = DatabaseManager()
    
    # Test adding a nickname
    print("Adding test nickname 'TestNick' to Cynical...")
    success = db.add_nickname("Cynical", "TestNick")
    
    if success:
        print("✅ Nickname added successfully!")
        
        # Test resolution
        resolved = db.resolve_player_name("TestNick")
        print(f"🔍 'TestNick' resolves to: {resolved}")
        
        # Remove test nickname
        print("Removing test nickname...")
        db.remove_nickname("Cynical", "TestNick")
        print("✅ Test nickname removed")
    else:
        print("❌ Failed to add nickname")

def main():
    """Main testing function."""
    print("🧪 MKWStatsBot Database Testing Suite")
    print("=" * 50)
    print()
    
    # Test basic operations
    test_database_operations()
    
    # Ask user what to test
    print("Choose a test:")
    print("1. Simulate race results (adds test data)")
    print("2. Test nickname management")
    print("3. Exit")
    
    try:
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            print()
            simulate_race_results()
        elif choice == "2":
            print()
            test_nickname_management()
        elif choice == "3":
            print("👋 Goodbye!")
        else:
            print("❌ Invalid choice")
            
    except KeyboardInterrupt:
        print("\n👋 Testing interrupted by user")
    except Exception as e:
        print(f"❌ Error during testing: {e}")

if __name__ == "__main__":
    main() 