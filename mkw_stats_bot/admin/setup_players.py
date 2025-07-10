#!/usr/bin/env python3
"""
Setup script to initialize all clan players with their nicknames.
Run this once to set up your player database.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mkw_stats.database import DatabaseManager

def setup_clan_players():
    """Initialize all clan players with their known nicknames."""
    
    # Initialize the database
    db = DatabaseManager("data/database/mario_kart_clan.db")
    
    # Define all clan players with their nicknames
    clan_players = {
        "Cynical": ["Cyn", "Christian", "Cynicl"],
        "rx": ["Astral", "Astralixv"],
        "Corbs": ["myst"],
        "sopt": [],
        "Dicey": [],
        "Quick": [],
        "DEMISE": ["Demise"],
        "Ami": [],
        "Benji": [],
        "Danika": [],
        "Hollow": [],
        "Jacob": [],
        "Jake": [],
        "James": [],
        "Juice": [],
        "Klefki": [],
        "Koopalings": ["Koopa"],
        "Minty": [],
        "Moon": [],
        "Mook": [],
        "Nick F": ["NickF"],
        "Vortex": [],
        "Wilbur": [],
        "yukino": ["yuki"]
    }
    
    print("🏁 Setting up Mario Kart Clan Database...")
    print(f"📁 Database: {db.db_path}")
    
    # Add all players
    for main_name, nicknames in clan_players.items():
        success = db.add_or_update_player(main_name, nicknames)
        if success:
            nickname_text = f" (nicknames: {', '.join(nicknames)})" if nicknames else ""
            print(f"✅ Added {main_name}{nickname_text}")
        else:
            print(f"❌ Failed to add {main_name}")
    
    # Show summary
    info = db.get_database_info()
    print(f"\n📊 Setup Complete!")
    print(f"   Players added: {info['player_count']}")
    print(f"   Database size: {info['file_size_kb']:.1f} KB")
    print(f"   Location: {info['database_path']}")
    
    # Test nickname resolution
    print(f"\n🔍 Testing nickname resolution:")
    test_names = ["Cynical", "Cyn", "Christian", "rx", "Astral", "Corbs", "Corby", "Quick", "Q"]
    for name in test_names:
        resolved = db.resolve_player_name(name)
        if resolved:
            print(f"   '{name}' → '{resolved}'")
        else:
            print(f"   '{name}' → NOT FOUND")

if __name__ == "__main__":
    setup_clan_players() 