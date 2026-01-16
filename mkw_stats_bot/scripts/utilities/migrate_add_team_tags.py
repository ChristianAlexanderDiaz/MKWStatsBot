#!/usr/bin/env python3
"""
Migration Script: Add Team Tags Column to Guild Configs Table
==============================================================

This migration adds team_tags JSONB column to guild_configs table to support
custom tags for teams (e.g., "Let Him Cook" -> "COOK").

Features:
- Stores team name -> tag mapping: {"Team Name": "TAG", "Let Him Cook": "COOK"}
- Tags are optional (teams without tags display normally)
- Guild-specific (each guild has separate team tags)
- Unicode support for international characters
- Tags are 1-8 chars max (Switch 10 char limit: 8 tag + 1 separator + 1 name min)
- Tags display in player names across all views (roster, leaderboard, stats)

Run this script to:
1. Check if team_tags column already exists (idempotent)
2. Add team_tags JSONB column with default '{}'
3. Verify the migration was successful
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


def add_team_tags_column(db: DatabaseManager) -> bool:
    """Add team_tags JSONB column to the guild_configs table."""
    logger.info("=" * 80)
    logger.info("STEP 1: Adding team_tags column to guild_configs table")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if team_tags column already exists
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'guild_configs' AND column_name = 'team_tags'
            """)

            if cursor.fetchone():
                logger.warning("⚠️  team_tags column already exists. Skipping creation.")
                return True

            # Add team_tags column
            logger.info("Adding column: team_tags (JSONB)")
            cursor.execute("""
                ALTER TABLE guild_configs
                ADD COLUMN team_tags JSONB DEFAULT '{}'::jsonb
            """)

            conn.commit()
            logger.info("✅ Added team_tags column successfully!")
            return True

    except Exception as e:
        logger.error(f"❌ Error adding column: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def verify_migration(db: DatabaseManager) -> bool:
    """Verify the migration was successful."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 2: Verifying migration")
    logger.info("=" * 80)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Verify column exists
            cursor.execute("""
                SELECT column_name, data_type, column_default
                FROM information_schema.columns
                WHERE table_name = 'guild_configs' AND column_name = 'team_tags'
            """)

            result = cursor.fetchone()
            if result:
                col_name, data_type, default = result
                logger.info(f"✅ Column '{col_name}' exists")
                logger.info(f"   Type: {data_type}")
                logger.info(f"   Default: {default}")
            else:
                logger.error("❌ Column 'team_tags' not found")
                return False

            # Count guilds
            cursor.execute("""
                SELECT COUNT(*) FROM guild_configs
            """)
            guild_count = cursor.fetchone()[0]
            logger.info(f"Guilds in database: {guild_count}")

            # Show sample data
            cursor.execute("""
                SELECT guild_id, guild_name, team_names, team_tags
                FROM guild_configs
                WHERE is_active = TRUE
                LIMIT 5
            """)

            sample_data = cursor.fetchall()
            if sample_data:
                logger.info("")
                logger.info("Sample Data (first 5 active guilds):")
                for row in sample_data:
                    guild_id, guild_name, team_names, team_tags = row
                    logger.info(f"  Guild {guild_id} ({guild_name}):")
                    logger.info(f"    Teams: {team_names}")
                    logger.info(f"    Tags: {team_tags}")

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
    logger.info("🚀 Team Tags Migration")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    try:
        # Initialize database
        db = DatabaseManager()
        logger.info("✅ Database connection established")

        # Step 1: Add column
        if not add_team_tags_column(db):
            logger.error("❌ Failed to add column. Aborting migration.")
            return False

        # Step 2: Verify
        if not verify_migration(db):
            logger.warning("⚠️  Verification had issues. Please review.")
            return False

        logger.info("")
        logger.info("=" * 80)
        logger.info("🎉 Migration completed successfully!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next Steps:")
        logger.info("  1. Use /setteamtag to add tags for teams")
        logger.info("  2. Use /showteamtags to view all team tags")
        logger.info("  3. Use /removeteamtag to remove tags from teams")
        logger.info("  4. Tags will automatically display in roster, leaderboard, and stats")
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
