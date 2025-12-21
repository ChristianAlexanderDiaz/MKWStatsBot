#!/usr/bin/env python3
"""
Custom fix script for specific players in Guild 1130655044547657739

Fixes:
1. Tay/TayUSA - Merge and recalculate
2. Jsaav - Reactivate and recalculate
3. AJ→AyyJayy, Michel→MicheL, Zon→ZonX24, peetzyn→Peetzyn - Recalculate with unresolved names
"""

import sys
import os
sys.path.insert(0, '/Users/cynical/Documents/Results/mkw_stats_bot')

from mkw_stats.database import DatabaseManager
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(message)s')

GUILD_ID = 1130655044547657739

# Mapping of unresolved names to actual player names
NAME_MAPPINGS = {
    'AJ': 'AyyJayy',
    'Michel': 'MicheL',
    'Zon': 'ZonX24',
    'peetzyn': 'Peetzyn',
    'TayUSA': 'Tay',
    'Jsaav': 'Jsaav'
}


def reset_player_stats(db, player_name, guild_id):
    """Reset player stats and delete performance records."""
    logging.info(f"  🔄 Resetting stats for {player_name}...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get player ID
        cursor.execute("""
            SELECT id FROM players
            WHERE player_name = %s AND guild_id = %s
        """, (player_name, guild_id))
        result = cursor.fetchone()
        if not result:
            logging.error(f"  ❌ Player {player_name} not found")
            return None

        player_id = result[0]

        # Delete existing performance records
        cursor.execute("""
            DELETE FROM player_war_performances WHERE player_id = %s
        """, (player_id,))
        deleted = cursor.rowcount
        logging.info(f"  🗑️  Deleted {deleted} performance records")

        # Reset stats to 0
        cursor.execute("""
            UPDATE players SET
                total_score = 0,
                total_races = 0,
                war_count = 0,
                average_score = 0.0,
                total_team_differential = 0,
                last_war_date = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (player_id,))

        conn.commit()
        logging.info(f"  ✅ Stats reset for {player_name}")
        return player_id


def recalculate_stats(db, player_name, alternate_names, guild_id):
    """Recalculate stats from all wars where player appears under any name."""
    logging.info(f"  📊 Recalculating stats for {player_name}...")
    logging.info(f"     Looking for names: {', '.join(alternate_names)}")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get player ID
        cursor.execute("""
            SELECT id FROM players WHERE player_name = %s AND guild_id = %s
        """, (player_name, guild_id))
        result = cursor.fetchone()
        if not result:
            logging.error(f"  ❌ Player {player_name} not found")
            return

        player_id = result[0]

        # Get all wars
        cursor.execute("""
            SELECT id, war_date, race_count, players_data, team_differential
            FROM wars WHERE guild_id = %s
            ORDER BY war_date
        """, (guild_id,))

        total_score = 0
        total_races = 0
        war_count = 0
        total_team_differential = 0
        performances_created = 0
        last_war_date = None

        for row in cursor.fetchall():
            war_id, war_date, race_count, players_data, team_diff = row

            if not players_data or 'results' not in players_data:
                continue

            # Find player in this war under any alternate name
            player_result = None
            for result in players_data['results']:
                if result.get('name') in alternate_names:
                    player_result = result
                    break

            if not player_result:
                continue

            # Extract data
            score = player_result.get('score', 0)
            races = player_result.get('races', 12)
            war_participation = races / race_count if race_count > 0 else 1.0

            # Create performance record
            try:
                cursor.execute("""
                    INSERT INTO player_war_performances
                    (player_id, war_id, score, races_played, war_participation)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (player_id, war_id) DO NOTHING
                """, (player_id, war_id, score, races, war_participation))

                if cursor.rowcount > 0:
                    performances_created += 1

                # Accumulate stats
                total_score += score
                total_races += races
                war_count += 1
                total_team_differential += (team_diff or 0)
                last_war_date = war_date

            except Exception as e:
                logging.error(f"  ❌ Error creating performance record: {e}")

        # Update player stats
        if war_count > 0:
            average_score = total_score / war_count

            cursor.execute("""
                UPDATE players SET
                    total_score = %s,
                    total_races = %s,
                    war_count = %s,
                    average_score = %s,
                    total_team_differential = %s,
                    last_war_date = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (total_score, total_races, war_count, average_score,
                  total_team_differential, last_war_date, player_id))

        conn.commit()

        logging.info(f"  ✅ Recalculated: {war_count} wars, {total_score} total score, avg {average_score:.2f}")
        logging.info(f"     Created {performances_created} performance records")


def main():
    logging.info("=" * 80)
    logging.info("CUSTOM PLAYER FIX SCRIPT")
    logging.info(f"Guild ID: {GUILD_ID}")
    logging.info("=" * 80)

    db = DatabaseManager()

    # Fix 1: Tay/TayUSA (merge)
    logging.info("\n🔧 FIX 1: Tay/TayUSA (same person)")
    logging.info("-" * 80)

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Add TayUSA as nickname to Tay
        cursor.execute("""
            SELECT nicknames FROM players
            WHERE player_name = %s AND guild_id = %s
        """, ('Tay', GUILD_ID))
        result = cursor.fetchone()

        if result:
            nicknames = result[0] or []
            if 'TayUSA' not in nicknames:
                nicknames.append('TayUSA')
                cursor.execute("""
                    UPDATE players SET nicknames = %s::jsonb
                    WHERE player_name = %s AND guild_id = %s
                """, (json.dumps(nicknames), 'Tay', GUILD_ID))
                conn.commit()
                logging.info("  ✅ Added 'TayUSA' as nickname to Tay")

    reset_player_stats(db, 'Tay', GUILD_ID)
    recalculate_stats(db, 'Tay', ['Tay', 'TayUSA'], GUILD_ID)

    # Fix 2: Jsaav (reactivate)
    logging.info("\n🔧 FIX 2: Jsaav (reactivate)")
    logging.info("-" * 80)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE players SET is_active = TRUE
            WHERE player_name = %s AND guild_id = %s
        """, ('Jsaav', GUILD_ID))
        conn.commit()
        logging.info("  ✅ Reactivated Jsaav")

    reset_player_stats(db, 'Jsaav', GUILD_ID)
    recalculate_stats(db, 'Jsaav', ['Jsaav'], GUILD_ID)

    # Fix 3: AJ→AyyJayy
    logging.info("\n🔧 FIX 3: AJ→AyyJayy")
    logging.info("-" * 80)
    reset_player_stats(db, 'AyyJayy', GUILD_ID)
    recalculate_stats(db, 'AyyJayy', ['AyyJayy', 'AJ', 'Ajay'], GUILD_ID)

    # Fix 4: Michel→MicheL
    logging.info("\n🔧 FIX 4: Michel→MicheL")
    logging.info("-" * 80)
    reset_player_stats(db, 'MicheL', GUILD_ID)
    recalculate_stats(db, 'MicheL', ['MicheL', 'Michel', 'Unc'], GUILD_ID)

    # Fix 5: Zon→ZonX24
    logging.info("\n🔧 FIX 5: Zon→ZonX24")
    logging.info("-" * 80)
    reset_player_stats(db, 'ZonX24', GUILD_ID)
    recalculate_stats(db, 'ZonX24', ['ZonX24', 'Zon', 'Megumi'], GUILD_ID)

    # Fix 6: peetzyn→Peetzyn
    logging.info("\n🔧 FIX 6: peetzyn→Peetzyn")
    logging.info("-" * 80)
    reset_player_stats(db, 'Peetzyn', GUILD_ID)
    recalculate_stats(db, 'Peetzyn', ['Peetzyn', 'peetzyn', 'Peet'], GUILD_ID)

    db.close()

    logging.info("\n" + "=" * 80)
    logging.info("✅ ALL FIXES COMPLETED")
    logging.info("=" * 80)


if __name__ == '__main__':
    response = input("\n⚠️  This will reset and recalculate stats for 6 players. Continue? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        main()
    else:
        print("❌ Cancelled by user")
