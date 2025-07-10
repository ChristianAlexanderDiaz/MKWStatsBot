#!/usr/bin/env python3
"""
Script to check the Mario Kart clan database.
Shows player stats, recent sessions, and database info.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mkw_stats.database import DatabaseManager

def show_all_stats(db):
    """Show stats for all players."""
    players = db.get_all_players_stats()
    
    if not players:
        print("📊 No player stats found (no races recorded yet)")
        return
    
    print(f"🏆 Player Rankings ({len(players)} players with race data):")
    print("-" * 80)
    
    # Sort players by average score
    for i, player in enumerate(players, 1):
        
        # Show nicknames
        nicknames_text = f" ({', '.join(player['nicknames'])})" if player['nicknames'] else ""
        
        # Show player name and nicknames
        print(f"{i:2d}. {player['main_name']:15s}{nicknames_text}")
        print(f"    Average: {player['average_score']:6.1f} | Wars: {player['war_count']:5.2f} | Races: {player['total_races']:2d} | Total: {player['total_scores']:4d}")
        
        # Show recent scores (last 5)
        recent_scores = player['score_history'][-5:] if len(player['score_history']) > 5 else player['score_history']
        print(f"    Recent scores: {recent_scores}")
        print()

def show_player_detail(db, name):
    """Show detailed stats for a specific player."""
    player = db.get_player_stats(name)
    
    if not player:
        print(f"❌ Player '{name}' not found")
        
        # Show available players
        print("\n📋 Available players:")
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT main_name, nicknames FROM players ORDER BY main_name")
            for main_name, nicknames_json in cursor.fetchall():
                import json
                nicknames = json.loads(nicknames_json)
                nickname_text = f" (nicknames: {', '.join(nicknames)})" if nicknames else ""
                print(f"   {main_name}{nickname_text}")
        return
    
    print(f"📊 Detailed Stats for {player['main_name']}")
    print("=" * 50)
    
    if player['nicknames']:
        print(f"Nicknames: {', '.join(player['nicknames'])}")
    
    print(f"Total Races: {player['total_races']}")
    print(f"Total Score: {player['total_scores']}")
    print(f"Wars Completed: {player['war_count']:.2f}")
    print(f"Average Score: {player['average_score']:.1f}")
    print(f"Last Updated: {player['last_updated']}")
    
    if player['score_history']:
        print(f"\n🏁 Score History ({len(player['score_history'])} races):")
        scores = player['score_history']
        
        # Group by wars (every 12 races)
        for war_num in range(0, len(scores), 12):
            war_scores = scores[war_num:war_num+12]
            war_total = sum(war_scores)
            war_label = f"War {war_num//12 + 1}" if len(war_scores) == 12 else f"Partial War {war_num//12 + 1}"
            
            print(f"   {war_label}: {war_scores} (Total: {war_total})")

def show_recent_sessions(db):
    """Show recent race sessions."""
    sessions = db.get_recent_sessions(10)
    
    if not sessions:
        print("📅 No race sessions found")
        return
    
    print(f"📅 Recent Race Sessions ({len(sessions)} sessions):")
    print("-" * 60)
    
    for session in sessions:
        print(f"Date: {session['session_date']} | Races: {session['race_count']} | Players: {len(session['results'])}")
        print(f"Saved: {session['created_at']}")
        
        # Show results
        for result in session['results']:
            print(f"   {result['name']:12s}: {result['score']:3d}")
        print()

def show_database_info(db):
    """Show database information."""
    info = db.get_database_info()
    
    print("🗃️ Database Information:")
    print(f"   Location: {info['database_path']}")
    print(f"   Size: {info['file_size_kb']:.1f} KB")
    print(f"   Players: {info['player_count']}")
    print(f"   Sessions: {info['session_count']}")

def main():
    db = DatabaseManager("database/mario_kart_clan.db")
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "player" and len(sys.argv) > 2:
            player_name = " ".join(sys.argv[2:])
            show_player_detail(db, player_name)
        elif command == "sessions":
            show_recent_sessions(db)
        elif command == "info":
            show_database_info(db)
        else:
            print("❌ Invalid command")
            print("Usage:")
            print("  python check_clan_db.py                    # Show all player stats")
            print("  python check_clan_db.py player Cynical     # Show specific player")
            print("  python check_clan_db.py sessions           # Show recent sessions") 
            print("  python check_clan_db.py info               # Show database info")
    else:
        # Default: show all stats and database info
        show_all_stats(db)
        print()
        show_database_info(db)
        
        print(f"\n💡 Usage:")
        print(f"  python check_clan_db.py player Cynical     # Show specific player")
        print(f"  python check_clan_db.py sessions           # Show recent sessions")
        print(f"  python check_clan_db.py info               # Show database info")

if __name__ == "__main__":
    main() 