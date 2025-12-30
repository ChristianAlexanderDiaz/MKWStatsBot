#!/usr/bin/env python3
"""
Migration Script: Recalculate Team Differentials
=================================================

This migration fixes the team differential calculation bug where differentials
were calculated against breakeven (492) instead of opponent score.

Bug Details:
- Old calculation: team_score - 492
- Correct calculation: team_score - (total_points - team_score)
  where total_points = 82 * race_count

This script will:
1. Recalculate team_differential for all wars in the specified guild(s)
2. Recalculate total_team_differential for all affected players
3. Is idempotent - safe to run multiple times

Usage:
    python recalculate_team_differentials.py --guild COOK    # Fix "Let Him Cook" only
    python recalculate_team_differentials.py --guild ALL     # Fix all guilds
"""

import sys
import os
import argparse
import logging
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from mkw_stats.database import DatabaseManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_guild_id_by_name(db, guild_name):
    """Get guild_id by guild name."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT guild_id, guild_name FROM guild_configs WHERE guild_name = %s AND is_active = TRUE
            """, (guild_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return None
    except Exception as e:
        logger.error(f"Error getting guild ID: {e}")
        return None


def get_all_guild_ids(db):
    """Get all guild IDs."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id, guild_name FROM guild_configs WHERE is_active = TRUE ORDER BY guild_id")
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting all guild IDs: {e}")
        return []


def recalculate_war_differentials(db, guild_id):
    """Recalculate team_differential for all wars in a guild."""
    logger.info(f"📊 Recalculating war differentials for guild {guild_id}...")

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all wars for this guild
            cursor.execute("""
                SELECT id, team_score, race_count, team_differential
                FROM wars
                WHERE guild_id = %s
                ORDER BY id
            """, (guild_id,))

            wars = cursor.fetchall()
            logger.info(f"   Found {len(wars)} wars to process")

            updated_count = 0
            unchanged_count = 0

            for war in wars:
                war_id, team_score, race_count, old_differential = war

                # Calculate correct differential
                total_points = 82 * race_count
                opponent_score = total_points - team_score
                correct_differential = team_score - opponent_score

                # Only update if different
                if old_differential != correct_differential:
                    cursor.execute("""
                        UPDATE wars
                        SET team_differential = %s
                        WHERE id = %s
                    """, (correct_differential, war_id))

                    logger.info(f"   War {war_id}: {old_differential:+d} → {correct_differential:+d} (team: {team_score}, opp: {opponent_score})")
                    updated_count += 1
                else:
                    unchanged_count += 1

            conn.commit()
            logger.info(f"✅ Updated {updated_count} wars, {unchanged_count} already correct")
            return updated_count

    except Exception as e:
        logger.error(f"❌ Error recalculating war differentials: {e}")
        return 0


def recalculate_player_differentials(db, guild_id):
    """Recalculate total_team_differential for all players in a guild."""
    logger.info(f"👥 Recalculating player differentials for guild {guild_id}...")

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all active players in this guild
            cursor.execute("""
                SELECT id, player_name, total_team_differential
                FROM players
                WHERE guild_id = %s AND is_active = TRUE
                ORDER BY player_name
            """, (guild_id,))

            players = cursor.fetchall()
            logger.info(f"   Found {len(players)} players to process")

            updated_count = 0
            unchanged_count = 0

            for player in players:
                player_id, player_name, old_differential = player

                # Calculate correct total from all war performances
                cursor.execute("""
                    SELECT w.team_differential, pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                """, (player_id, guild_id))

                performances = cursor.fetchall()

                # Sum up scaled differentials
                correct_total = 0
                for team_diff, war_participation in performances:
                    scaled_diff = int(team_diff * float(war_participation))
                    correct_total += scaled_diff

                # Only update if different
                old_diff_value = old_differential if old_differential is not None else 0
                if old_diff_value != correct_total:
                    cursor.execute("""
                        UPDATE players
                        SET total_team_differential = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (correct_total, player_id))

                    logger.info(f"   {player_name}: {old_diff_value:+d} → {correct_total:+d}")
                    updated_count += 1
                else:
                    unchanged_count += 1

            conn.commit()
            logger.info(f"✅ Updated {updated_count} players, {unchanged_count} already correct")
            return updated_count

    except Exception as e:
        logger.error(f"❌ Error recalculating player differentials: {e}")
        return 0


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Recalculate team differentials')
    parser.add_argument('--guild', required=True,
                        help='Guild to migrate: numeric guild_id or ALL (for all guilds)')
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Team Differential Recalculation Migration")
    logger.info("=" * 80)

    # Initialize database
    db = DatabaseManager()

    # Determine which guilds to process
    guilds_to_process = []

    if args.guild.upper() == 'ALL':
        all_guilds = get_all_guild_ids(db)
        if not all_guilds:
            logger.error("No guilds found in database")
            return 1
        guilds_to_process = all_guilds
        logger.info(f"Processing all {len(guilds_to_process)} guilds")
    else:
        # Assume it's a guild_id number
        try:
            guild_id = int(args.guild)
            guilds_to_process = [(guild_id, f"Guild {guild_id}")]
            logger.info(f"Processing single guild ID: {guild_id}")
        except ValueError:
            logger.error(f"Invalid guild parameter: {args.guild}")
            logger.error("Use a numeric guild_id or 'ALL'")
            return 1

    logger.info("")

    # Process each guild
    total_wars_updated = 0
    total_players_updated = 0

    for guild_id, guild_name in guilds_to_process:
        logger.info(f"🔧 Processing: {guild_name} (ID: {guild_id})")
        logger.info("-" * 80)

        # Step 1: Recalculate war differentials
        wars_updated = recalculate_war_differentials(db, guild_id)
        total_wars_updated += wars_updated

        # Step 2: Recalculate player differentials
        players_updated = recalculate_player_differentials(db, guild_id)
        total_players_updated += players_updated

        logger.info("")

    # Summary
    logger.info("=" * 80)
    logger.info("Migration Complete!")
    logger.info("=" * 80)
    logger.info(f"✅ Guilds processed: {len(guilds_to_process)}")
    logger.info(f"✅ Wars updated: {total_wars_updated}")
    logger.info(f"✅ Players updated: {total_players_updated}")
    logger.info("")
    logger.info("💡 This migration is idempotent - safe to run again if needed")
    logger.info("=" * 80)

    return 0


if __name__ == '__main__':
    sys.exit(main())
