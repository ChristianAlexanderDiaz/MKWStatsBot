#!/usr/bin/env python3
"""
Migration Script: Add player_war_performances Table
====================================================

This migration creates a normalized table to track individual player war performances,
replacing the need to scan JSONB data in the wars table.

Performance Improvement:
- Old: O(n*m) scanning all wars JSONB
- New: O(1) indexed lookup

Run this script to:
1. Create the player_war_performances table
2. Migrate existing 359 wars from JSONB to normalized table
3. Preserve all existing data (no data loss)
"""

import sys
import os
import logging
from datetime import datetime

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


def create_player_war_performances_table(db):
    """Create the player_war_performances table with indexes."""
    logger.info("=" * 80)
    logger.info("STEP 1: Creating player_war_performances table")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if table already exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'player_war_performances'
                );
            """)

            if cursor.fetchone()[0]:
                logger.warning("⚠️  Table 'player_war_performances' already exists. Skipping creation.")
                return True

            # Create the table
            logger.info("Creating player_war_performances table...")
            cursor.execute("""
                CREATE TABLE player_war_performances (
                    id SERIAL PRIMARY KEY,
                    player_id INTEGER NOT NULL REFERENCES players(id),
                    war_id INTEGER NOT NULL REFERENCES wars(id) ON DELETE CASCADE,
                    score INTEGER NOT NULL,
                    races_played INTEGER NOT NULL,
                    war_participation DECIMAL(4,3) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(player_id, war_id)
                );
            """)

            # Create indexes for performance
            logger.info("Creating indexes...")
            cursor.execute("""
                CREATE INDEX idx_player_performances ON player_war_performances(player_id, war_id);
            """)
            cursor.execute("""
                CREATE INDEX idx_war_performances ON player_war_performances(war_id);
            """)
            cursor.execute("""
                CREATE INDEX idx_player_created ON player_war_performances(player_id, created_at DESC);
            """)

            conn.commit()
            logger.info("✅ Table and indexes created successfully!")
            return True

    except Exception as e:
        logger.error(f"❌ Error creating table: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def migrate_existing_wars(db):
    """Migrate all existing wars from JSONB to normalized table."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 2: Migrating existing wars data")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all wars
            cursor.execute("""
                SELECT id, guild_id, race_count, players_data
                FROM wars
                ORDER BY id
            """)

            all_wars = cursor.fetchall()
            total_wars = len(all_wars)
            logger.info(f"Found {total_wars} wars to migrate")

            migrated_count = 0
            skipped_count = 0
            error_count = 0

            for i, (war_id, guild_id, race_count, players_data) in enumerate(all_wars, 1):
                # Progress indicator
                if i % 50 == 0 or i == total_wars:
                    logger.info(f"Progress: {i}/{total_wars} wars processed...")

                # Extract player results from JSONB
                results = players_data.get('results', []) if players_data else []

                if not results:
                    logger.warning(f"⚠️  War #{war_id}: No player results found")
                    skipped_count += 1
                    continue

                # Process each player in this war
                for player_result in results:
                    try:
                        player_name = player_result.get('name')
                        if not player_name:
                            continue

                        # Resolve player name to ID (handles nicknames)
                        resolved_name = db.resolve_player_name(player_name, guild_id, log_level='none')

                        if not resolved_name:
                            logger.debug(f"  War #{war_id}: Could not resolve '{player_name}' (likely opponent)")
                            skipped_count += 1
                            continue

                        # Get player ID
                        cursor.execute("""
                            SELECT id FROM players
                            WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                        """, (resolved_name, guild_id))

                        player_row = cursor.fetchone()
                        if not player_row:
                            logger.debug(f"  War #{war_id}: Player '{resolved_name}' not found in database")
                            skipped_count += 1
                            continue

                        player_id = player_row[0]
                        score = player_result.get('score', 0)
                        races_played = player_result.get('races_played', race_count)
                        war_participation = player_result.get('war_participation', 1.0)

                        # Insert into player_war_performances
                        cursor.execute("""
                            INSERT INTO player_war_performances
                            (player_id, war_id, score, races_played, war_participation)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (player_id, war_id) DO NOTHING
                        """, (player_id, war_id, score, races_played, war_participation))

                        migrated_count += 1

                    except Exception as e:
                        logger.error(f"  War #{war_id}, Player '{player_name}': {e}")
                        error_count += 1

            conn.commit()

            logger.info("")
            logger.info("Migration Summary:")
            logger.info(f"  ✅ Successfully migrated: {migrated_count} player-war records")
            logger.info(f"  ⚠️  Skipped: {skipped_count} records (opponents or not found)")
            logger.info(f"  ❌ Errors: {error_count} records")

            return True

    except Exception as e:
        logger.error(f"❌ Error during migration: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def verify_migration(db):
    """Verify the migration was successful."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 3: Verifying migration")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Count total records
            cursor.execute("SELECT COUNT(*) FROM player_war_performances")
            total_records = cursor.fetchone()[0]

            # Count total wars
            cursor.execute("SELECT COUNT(*) FROM wars")
            total_wars = cursor.fetchone()[0]

            # Count total players
            cursor.execute("SELECT COUNT(*) FROM players WHERE is_active = TRUE")
            total_players = cursor.fetchone()[0]

            # Get sample data
            cursor.execute("""
                SELECT p.player_name, w.war_date, pwp.score, pwp.races_played
                FROM player_war_performances pwp
                JOIN players p ON pwp.player_id = p.id
                JOIN wars w ON pwp.war_id = w.id
                ORDER BY w.created_at DESC
                LIMIT 5
            """)
            sample_data = cursor.fetchall()

            logger.info(f"Total Records in player_war_performances: {total_records}")
            logger.info(f"Total Wars: {total_wars}")
            logger.info(f"Total Active Players: {total_players}")
            logger.info(f"Expected (approx): {total_wars * 6} records (assuming ~6 players/war)")

            logger.info("")
            logger.info("Sample Data (most recent 5):")
            for player_name, war_date, score, races_played in sample_data:
                logger.info(f"  {player_name}: {score} points, {races_played} races on {war_date}")

            # Sanity check
            expected_min = total_wars * 3  # At least 3 players per war
            expected_max = total_wars * 12  # At most 12 players per war

            if expected_min <= total_records <= expected_max:
                logger.info("")
                logger.info("✅ Migration verification PASSED!")
                return True
            else:
                logger.warning(f"⚠️  Record count outside expected range ({expected_min}-{expected_max})")
                return False

    except Exception as e:
        logger.error(f"❌ Error during verification: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """Main migration execution."""
    logger.info("")
    logger.info("🚀 Player War Performances Migration")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    try:
        # Initialize database
        db = DatabaseManager()
        logger.info("✅ Database connection established")

        # Step 1: Create table
        if not create_player_war_performances_table(db):
            logger.error("❌ Failed to create table. Aborting migration.")
            return False

        # Step 2: Migrate data
        if not migrate_existing_wars(db):
            logger.error("❌ Failed to migrate data. Aborting.")
            return False

        # Step 3: Verify
        if not verify_migration(db):
            logger.warning("⚠️  Verification had warnings. Please review.")

        logger.info("")
        logger.info("=" * 80)
        logger.info("🎉 Migration completed successfully!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next Steps:")
        logger.info("  1. Review the migration summary above")
        logger.info("  2. Test new query methods with database.py")
        logger.info("  3. Update bot code to use new table for future wars")
        logger.info("")

        db.close()
        return True

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
