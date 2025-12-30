#!/usr/bin/env python3
"""Get guild_id from a war ID."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from mkw_stats.database import DatabaseManager

db = DatabaseManager()

war_id = 995

try:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT guild_id FROM wars WHERE id = %s", (war_id,))
        result = cursor.fetchone()

        if result:
            guild_id = result[0]
            print(f"War {war_id} is from guild_id: {guild_id}")
        else:
            print(f"War {war_id} not found")
except Exception as e:
    print(f"Error: {e}")
