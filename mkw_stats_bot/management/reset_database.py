#!/usr/bin/env python3
"""
Database reset tool - clears all scores and statistics while keeping player names and nicknames.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mkw_stats.database import DatabaseManager
import json

def reset_player_stats():
    """Reset all player statistics while keeping names and nicknames."""
    
    db = DatabaseManager("database/mario_kart_clan.db")
    
    print("🔄 Resetting Mario Kart Clan Database...")
    print("⚠️  This will clear all scores and statistics but keep player names and nicknames.")
    
    # Confirm reset
    confirm = input("Are you sure you want to reset all statistics? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Reset cancelled.")
        return
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current players with their nicknames
            cursor.execute("SELECT main_name, nicknames FROM players")
            current_players = cursor.fetchall()
            
            print(f"📋 Found {len(current_players)} players to reset...")
            
            # Reset all player statistics
            cursor.execute('''
                UPDATE players 
                SET score_history = ?, 
                    total_scores = 0, 
                    war_count = 0, 
                    average_score = 0.0,
                    updated_at = CURRENT_TIMESTAMP
            ''', (json.dumps([]),))
            
            # Clear all race sessions
            cursor.execute("DELETE FROM race_sessions")
            
            conn.commit()
            
            print("✅ Database reset complete!")
            print(f"   Players kept: {len(current_players)}")
            print("   All scores, wars, and sessions cleared")
            print("   Player names and nicknames preserved")
            
            # Show preserved players
            print("\n📋 Preserved Players:")
            for main_name, nicknames_json in current_players:
                nicknames = json.loads(nicknames_json)
                nickname_text = f" (nicknames: {', '.join(nicknames)})" if nicknames else ""
                print(f"   {main_name}{nickname_text}")
            
    except Exception as e:
        print(f"❌ Error resetting database: {e}")

if __name__ == "__main__":
    reset_player_stats() 