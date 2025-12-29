#!/usr/bin/env python3
"""
Database migration to add Discord user ID support and role configuration.

This migration adds:
1. Discord user ID fields to players table (discord_user_id, display_name, discord_username)
2. Role configuration to guild_configs table (role_member_id, role_trial_id, role_ally_id)
3. Indexes for efficient Discord ID lookups
4. Last role sync timestamp tracking
"""

import sys
import os
import logging

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

def migrate_add_discord_user_ids(db):
    """Add Discord user ID support and role configuration."""
    logger.info("=" * 80)
    logger.info("Discord User ID Migration")
    logger.info("=" * 80)

    try:

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if discord_user_id column already exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'players' AND column_name = 'discord_user_id'
            """)

            if cursor.fetchone():
                print("[!] discord_user_id column already exists, skipping players table migration")
            else:
                print("[*] Adding Discord fields to players table...")

                # Add discord_user_id column
                cursor.execute("""
                    ALTER TABLE players
                    ADD COLUMN discord_user_id BIGINT
                """)

                # Add display_name column (auto-synced from Discord)
                cursor.execute("""
                    ALTER TABLE players
                    ADD COLUMN display_name VARCHAR
                """)

                # Add discord_username column (auto-synced from Discord)
                cursor.execute("""
                    ALTER TABLE players
                    ADD COLUMN discord_username VARCHAR
                """)

                # Add last_role_sync timestamp
                cursor.execute("""
                    ALTER TABLE players
                    ADD COLUMN last_role_sync TIMESTAMP
                """)

                # Add country code column for flag display
                cursor.execute("""
                    ALTER TABLE players
                    ADD COLUMN country_code CHAR(2)
                """)

                # Create index for Discord user ID lookups
                cursor.execute("""
                    CREATE INDEX idx_players_discord_user
                    ON players(discord_user_id, guild_id)
                """)

                # Create index for display_name lookups (for OCR matching)
                cursor.execute("""
                    CREATE INDEX idx_players_display_name
                    ON players(display_name, guild_id)
                """)

                print("[+] Discord fields added to players table")

            # Check if role_member_id column already exists in guild_configs
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'guild_configs' AND column_name = 'role_member_id'
            """)

            if cursor.fetchone():
                print("[!] role_member_id column already exists, skipping guild_configs migration")
            else:
                print("[*] Adding role configuration to guild_configs table...")

                # Add role_member_id column
                cursor.execute("""
                    ALTER TABLE guild_configs
                    ADD COLUMN role_member_id BIGINT
                """)

                # Add role_trial_id column
                cursor.execute("""
                    ALTER TABLE guild_configs
                    ADD COLUMN role_trial_id BIGINT
                """)

                # Add role_ally_id column
                cursor.execute("""
                    ALTER TABLE guild_configs
                    ADD COLUMN role_ally_id BIGINT
                """)

                print("[+] Role configuration added to guild_configs table")

            conn.commit()
            print("[+] Migration completed successfully")

            # Verify the migration
            cursor.execute("""
                SELECT COUNT(*) as total_players,
                       COUNT(discord_user_id) as linked_players,
                       COUNT(*) - COUNT(discord_user_id) as unlinked_players
                FROM players
            """)

            result = cursor.fetchone()
            print(f"[*] Migration verification:")
            print(f"   Total players: {result[0]}")
            print(f"   Linked to Discord: {result[1]}")
            print(f"   Unlinked (legacy): {result[2]}")

            # Show guild_configs status
            cursor.execute("""
                SELECT COUNT(*) as total_guilds,
                       COUNT(role_member_id) as guilds_with_roles
                FROM guild_configs
            """)

            result = cursor.fetchone()
            print(f"   Total guilds: {result[0]}")
            print(f"   Guilds with role config: {result[1]}")

            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Main migration execution."""
    try:
        # Initialize database
        db = DatabaseManager()
        logger.info("Database connection established")

        # Run migration
        if not migrate_add_discord_user_ids(db):
            logger.error("Failed to complete migration")
            return False

        logger.info("")
        logger.info("=" * 80)
        logger.info("Migration completed successfully!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next Steps:")
        logger.info("  1. Update /setup command to configure roles")
        logger.info("  2. Update /addplayer to use @mentions")
        logger.info("  3. Use /linkplayer to link existing players")
        logger.info("  4. Use /listunlinked to see players needing links")
        logger.info("")

        return True

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
