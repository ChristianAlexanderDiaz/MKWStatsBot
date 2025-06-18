#!/usr/bin/env python3
"""
Nickname management tool - add, remove, or update player nicknames.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mkw_stats.database import DatabaseManager
import json

def show_all_players(db):
    """Show all players with their current nicknames."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT main_name, nicknames FROM players ORDER BY main_name")
            players = cursor.fetchall()
            
            print(f"\n📋 All Players ({len(players)} total):")
            print("-" * 60)
            for i, (main_name, nicknames_json) in enumerate(players, 1):
                nicknames = json.loads(nicknames_json)
                nickname_text = f" → {', '.join(nicknames)}" if nicknames else " → (no nicknames)"
                print(f"{i:2d}. {main_name}{nickname_text}")
            
    except Exception as e:
        print(f"❌ Error showing players: {e}")

def update_player_nicknames(db, main_name, new_nicknames):
    """Update nicknames for a specific player."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if player exists
            cursor.execute("SELECT main_name FROM players WHERE main_name = ?", (main_name,))
            if not cursor.fetchone():
                print(f"❌ Player '{main_name}' not found!")
                return False
            
            # Update nicknames
            cursor.execute('''
                UPDATE players 
                SET nicknames = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE main_name = ?
            ''', (json.dumps(new_nicknames), main_name))
            
            conn.commit()
            
            nickname_text = f"[{', '.join(new_nicknames)}]" if new_nicknames else "[none]"
            print(f"✅ Updated {main_name} nicknames: {nickname_text}")
            return True
            
    except Exception as e:
        print(f"❌ Error updating nicknames: {e}")
        return False

def interactive_nickname_manager():
    """Interactive nickname management."""
    db = DatabaseManager("database/mario_kart_clan.db")
    
    print("🏷️  Mario Kart Clan Nickname Manager")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Show all players and nicknames")
        print("2. Update player nicknames")
        print("3. Add nickname to player")
        print("4. Remove nickname from player")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == "1":
            show_all_players(db)
            
        elif choice == "2":
            show_all_players(db)
            main_name = input("\nEnter player name: ").strip()
            if not main_name:
                continue
                
            print(f"Enter new nicknames for {main_name} (comma-separated):")
            nicknames_input = input("Nicknames: ").strip()
            
            if nicknames_input:
                new_nicknames = [nick.strip() for nick in nicknames_input.split(",") if nick.strip()]
            else:
                new_nicknames = []
                
            update_player_nicknames(db, main_name, new_nicknames)
            
        elif choice == "3":
            show_all_players(db)
            main_name = input("\nEnter player name: ").strip()
            if not main_name:
                continue
                
            # Get current nicknames
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT nicknames FROM players WHERE main_name = ?", (main_name,))
                    row = cursor.fetchone()
                    if not row:
                        print(f"❌ Player '{main_name}' not found!")
                        continue
                    
                    current_nicknames = json.loads(row[0])
                    print(f"Current nicknames: {current_nicknames}")
                    
                    new_nickname = input("Enter nickname to add: ").strip()
                    if new_nickname and new_nickname not in current_nicknames:
                        current_nicknames.append(new_nickname)
                        update_player_nicknames(db, main_name, current_nicknames)
                    elif new_nickname in current_nicknames:
                        print(f"⚠️  '{new_nickname}' already exists for {main_name}")
                        
            except Exception as e:
                print(f"❌ Error: {e}")
                
        elif choice == "4":
            show_all_players(db)
            main_name = input("\nEnter player name: ").strip()
            if not main_name:
                continue
                
            # Get current nicknames
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT nicknames FROM players WHERE main_name = ?", (main_name,))
                    row = cursor.fetchone()
                    if not row:
                        print(f"❌ Player '{main_name}' not found!")
                        continue
                    
                    current_nicknames = json.loads(row[0])
                    if not current_nicknames:
                        print(f"⚠️  {main_name} has no nicknames to remove")
                        continue
                        
                    print(f"Current nicknames: {current_nicknames}")
                    
                    nickname_to_remove = input("Enter nickname to remove: ").strip()
                    if nickname_to_remove in current_nicknames:
                        current_nicknames.remove(nickname_to_remove)
                        update_player_nicknames(db, main_name, current_nicknames)
                    else:
                        print(f"⚠️  '{nickname_to_remove}' not found in {main_name}'s nicknames")
                        
            except Exception as e:
                print(f"❌ Error: {e}")
                
        elif choice == "5":
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid option. Please choose 1-5.")

def bulk_update_nicknames():
    """Bulk update nicknames from the setup script format."""
    db = DatabaseManager("database/mario_kart_clan.db")
    
    # Current clan players with nicknames
    clan_players = {
        "Cynical": ["Cyn", "Christian"],
        "rx": ["Astral", "Astralixv"],
        "Corbs": ["myst"],
        "sopt": [],
        "Dicey": [],
        "Quick": [],
        "DEMISE": ["Demise"],
        "Ami": [],
        "Benjy": [],
        "Danika": [],
        "Hollow": [],
        "Jacob": [],
        "Jake": [],
        "James": [],
        "Juice": [],
        "Klefki": ["zach"],
        "Koopalings": ["Koopa"],
        "Minty": [],
        "Moon": [],
        "Mook": [],
        "Nick F": ["NickF"],
        "Vortex": [],
        "Wilbur": [],
        "yukino": ["yuki"]
    }
    
    print("🔄 Bulk updating all player nicknames...")
    
    for main_name, nicknames in clan_players.items():
        update_player_nicknames(db, main_name, nicknames)
    
    print(f"\n✅ Bulk update complete for {len(clan_players)} players!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bulk":
        bulk_update_nicknames()
    else:
        interactive_nickname_manager() 