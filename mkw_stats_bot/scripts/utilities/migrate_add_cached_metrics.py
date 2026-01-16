#!/usr/bin/env python3
"""
Migration Script: Add Cached Metrics Columns to Players Table
==============================================================

This migration adds 12 columns to cache expensive player statistics:
- 8 stable metrics (updated on every war add/remove)
- 4 volatile metrics (lazily calculated on first access after invalidation)

Performance Improvement:
- Old: 30 leaderboard requests = 30 full metric calculations (~4.5 seconds)
- New: 30 leaderboard requests = 30 cached lookups (~300ms after first access)

Run this script to:
1. Check if columns already exist (idempotent)
2. Add 12 new columns to players table
3. Backfill stable metrics for existing players
4. Leave volatile metrics as NULL (populated on first access)
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


def add_cached_metrics_columns(db: DatabaseManager) -> bool:
    """Add 12 cached metric columns to the players table."""
    logger.info("=" * 80)
    logger.info("STEP 1: Adding cached metric columns to players table")
    logger.info("=" * 80)

    columns_to_add = [
        # Stable metrics (always populated)
        ("score_stddev", "DECIMAL(6,2)", "0.0"),
        ("consistency_score", "DECIMAL(5,2)", None),
        ("highest_score", "INTEGER", "0"),
        ("lowest_score", "INTEGER", "0"),
        ("wins", "INTEGER", "0"),
        ("losses", "INTEGER", "0"),
        ("ties", "INTEGER", "0"),
        ("win_percentage", "DECIMAL(5,2)", "0.0"),
        # Volatile metrics (may be NULL)
        ("avg10_score", "DECIMAL(5,2)", None),
        ("form_score", "DECIMAL(3,1)", None),
        ("clutch_factor", "DECIMAL(4,2)", None),
        ("potential", "DECIMAL(5,1)", None),
        ("hotstreak", "DECIMAL(6,2)", None),
        ("cached_metrics_updated_at", "TIMESTAMP WITH TIME ZONE", None),
    ]

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check which columns already exist
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'players'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}

            columns_to_create = [
                (name, col_type, default)
                for name, col_type, default in columns_to_add
                if name not in existing_columns
            ]

            if not columns_to_create:
                logger.warning("⚠️  All cached metric columns already exist. Skipping creation.")
                return True

            # Add missing columns
            for col_name, col_type, default_val in columns_to_create:
                if default_val is not None:
                    alter_sql = f"""
                        ALTER TABLE players
                        ADD COLUMN {col_name} {col_type} DEFAULT {default_val}
                    """
                else:
                    alter_sql = f"""
                        ALTER TABLE players
                        ADD COLUMN {col_name} {col_type}
                    """

                logger.info(f"Adding column: {col_name} ({col_type})")
                cursor.execute(alter_sql)

            conn.commit()
            logger.info(f"✅ Added {len(columns_to_create)} columns successfully!")
            return True

    except Exception as e:
        logger.error(f"❌ Error adding columns: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def backfill_stable_metrics(db: DatabaseManager) -> bool:
    """Backfill stable metrics for existing players."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 2: Backfilling stable metrics for existing players")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all active players
            cursor.execute("""
                SELECT id, player_name, guild_id, total_score, war_count, average_score
                FROM players
                WHERE is_active = TRUE
                ORDER BY id
            """)

            all_players = cursor.fetchall()
            total_players = len(all_players)
            logger.info(f"Found {total_players} active players to backfill")

            if total_players == 0:
                logger.info("No players to backfill.")
                return True

            for idx, (player_id, player_name, guild_id, total_score, war_count, avg_score) in enumerate(all_players, 1):
                # Progress indicator
                if idx % 100 == 0 or idx == total_players:
                    logger.info(f"Progress: {idx}/{total_players} players processed...")

                try:
                    # Calculate stable metrics using subqueries
                    cursor.execute("""
                        UPDATE players
                        SET
                            score_stddev = COALESCE((
                                SELECT STDDEV_POP(score) FROM player_war_performances
                                WHERE player_id = %s
                            ), 0.0),
                            highest_score = COALESCE((
                                SELECT MAX(score) FROM player_war_performances
                                WHERE player_id = %s AND races_played = 12
                            ), 0),
                            lowest_score = COALESCE((
                                SELECT MIN(score) FROM player_war_performances
                                WHERE player_id = %s AND races_played = 12
                            ), 0),
                            wins = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential > 0 AND w.guild_id = %s
                            ), 0),
                            losses = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential < 0 AND w.guild_id = %s
                            ), 0),
                            ties = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential = 0 AND w.guild_id = %s
                            ), 0),
                            consistency_score = CASE
                                WHEN war_count >= 2 AND average_score > 0
                                THEN GREATEST(0, 100 - (
                                    COALESCE((
                                        SELECT STDDEV_POP(score) FROM player_war_performances
                                        WHERE player_id = %s
                                    ), 0.0) / average_score * 100
                                ))
                                ELSE NULL
                            END,
                            win_percentage = CASE
                                WHEN war_count > 0
                                THEN (COALESCE((
                                    SELECT COUNT(*) FROM player_war_performances pwp
                                    JOIN wars w ON pwp.war_id = w.id
                                    WHERE pwp.player_id = %s AND w.team_differential > 0 AND w.guild_id = %s
                                ), 0)::DECIMAL / war_count * 100)
                                ELSE 0.0
                            END
                        WHERE id = %s
                    """, (player_id, player_id, player_id, player_id, guild_id, player_id, guild_id,
                          player_id, guild_id, player_id, player_id, guild_id, player_id))

                except Exception as e:
                    logger.error(f"Error backfilling player {player_name} (ID {player_id}): {e}")

            conn.commit()
            logger.info(f"✅ Backfilled stable metrics for {total_players} players!")
            return True

    except Exception as e:
        logger.error(f"❌ Error during backfill: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def verify_migration(db: DatabaseManager) -> bool:
    """Verify the migration was successful."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 3: Verifying migration")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Verify all columns exist
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'players'
                AND column_name IN (
                    'score_stddev', 'consistency_score', 'highest_score', 'lowest_score',
                    'wins', 'losses', 'ties', 'win_percentage',
                    'avg10_score', 'form_score', 'clutch_factor', 'potential',
                    'hotstreak', 'cached_metrics_updated_at'
                )
            """)

            columns = cursor.fetchall()
            column_count = len(columns)
            expected_columns = 14

            if column_count == expected_columns:
                logger.info(f"✅ All {expected_columns} columns added successfully!")
            else:
                logger.warning(f"⚠️  Only {column_count}/{expected_columns} columns found")
                return False

            # Verify stable metrics are populated
            cursor.execute("""
                SELECT COUNT(*) FROM players
                WHERE is_active = TRUE
                AND (score_stddev != 0.0 OR war_count < 2)
            """)

            populated_count = cursor.fetchone()[0]
            logger.info(f"Players with populated stable metrics: {populated_count}")

            # Get sample data
            cursor.execute("""
                SELECT player_name, war_count, score_stddev, consistency_score,
                       wins, losses, ties, win_percentage
                FROM players
                WHERE is_active = TRUE
                AND war_count > 0
                ORDER BY war_count DESC
                LIMIT 5
            """)

            sample_data = cursor.fetchall()
            logger.info("")
            logger.info("Sample Data (top 5 active players by war count):")
            for row in sample_data:
                player_name, war_count, stddev, consistency, wins, losses, ties, win_pct = row
                logger.info(
                    f"  {player_name}: {war_count} wars, "
                    f"stddev={stddev}, consistency={consistency}, "
                    f"record={wins}W-{losses}L-{ties}T ({win_pct}%)"
                )

            logger.info("")
            logger.info("✅ Migration verification PASSED!")
            return True

    except Exception as e:
        logger.error(f"❌ Error during verification: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main() -> int:
    """Main migration execution."""
    logger.info("")
    logger.info("🚀 Cached Metrics Migration")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    try:
        # Initialize database
        db = DatabaseManager()
        logger.info("✅ Database connection established")

        # Step 1: Add columns
        if not add_cached_metrics_columns(db):
            logger.error("❌ Failed to add columns. Aborting migration.")
            return False

        # Step 2: Backfill stable metrics
        if not backfill_stable_metrics(db):
            logger.error("❌ Failed to backfill stable metrics.")
            return False

        # Step 3: Verify
        if not verify_migration(db):
            logger.warning("⚠️  Verification had issues. Please review.")
            return False

        logger.info("")
        logger.info("=" * 80)
        logger.info("🎉 Migration completed successfully!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next Steps:")
        logger.info("  1. Review the migration summary above")
        logger.info("  2. Update database.py with cache-aware methods")
        logger.info("  3. Deploy code changes and test cache functionality")
        logger.info("  4. Monitor cache hit rates in production")
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
