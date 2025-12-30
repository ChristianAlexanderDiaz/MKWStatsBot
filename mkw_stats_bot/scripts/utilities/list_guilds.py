#!/usr/bin/env python3
"""Quick script to list all guilds in the database."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from mkw_stats.database import DatabaseManager

db = DatabaseManager()

try:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT guild_id, guild_name, is_active FROM guild_configs ORDER BY guild_id")
        guilds = cursor.fetchall()

        print("\nGuilds in database:")
        print("-" * 80)
        for guild_id, guild_name, is_active in guilds:
            status = "ACTIVE" if is_active else "INACTIVE"
            print(f"ID: {guild_id} | Name: {guild_name!r} | Status: {status}")
        print("-" * 80)
        print(f"Total: {len(guilds)} guilds\n")
except Exception as e:
    print(f"Error: {e}")
