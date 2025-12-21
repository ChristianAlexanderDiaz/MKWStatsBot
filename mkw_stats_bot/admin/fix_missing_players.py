#!/usr/bin/env python3
"""
Data Migration Script: Fix Missing Players from OCR Auto-Add Bug

This script fixes the bug where players added via the "Add Player" button
in OCR confirmation were only added to war results but not to the players table.

It will:
1. Query all wars from the database
2. Extract all unique player names from war JSONB data
3. Check if each player exists in the players table
4. For missing players:
   - Add them to players table with team='Unassigned', member_status='member'
   - Recalculate their statistics from all wars
   - Create missing player_war_performances records
5. Report summary of fixes made

Usage:
    python mkw_stats_bot/admin/fix_missing_players.py [--guild-id GUILD_ID] [--dry-run]
"""

import sys
import os
import logging
from datetime import datetime
import argparse
from typing import Set, Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mkw_stats.database import DatabaseManager
from mkw_stats.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class MissingPlayersFixer:
    """Fix players that exist in war data but not in players table."""

    def __init__(self, db: DatabaseManager, guild_id: int = 0, dry_run: bool = False):
        self.db = db
        self.guild_id = guild_id
        self.dry_run = dry_run
        self.missing_players: Set[str] = set()
        self.players_added: List[str] = []
        self.performances_created: int = 0
        self.stats_updated: int = 0

    def find_missing_players(self) -> Set[str]:
        """Find all players in war data that don't exist in players table."""
        logging.info(f"🔍 Scanning wars for guild_id={self.guild_id}...")

        all_wars = self.db.get_all_wars(limit=None, guild_id=self.guild_id)
        logging.info(f"📊 Found {len(all_wars)} wars to analyze")

        # Extract all unique player names from wars
        players_in_wars: Set[str] = set()
        for war in all_wars:
            results = war.get('results', [])
            for result in results:
                player_name = result.get('name')
                if player_name:
                    players_in_wars.add(player_name)

        logging.info(f"👥 Found {len(players_in_wars)} unique players in war data")

        # Check which players don't exist in players table
        missing_players: Set[str] = set()
        for player_name in players_in_wars:
            player_info = self.db.get_player_info(player_name, self.guild_id)
            if not player_info:
                missing_players.add(player_name)

        self.missing_players = missing_players
        logging.info(f"❌ Found {len(missing_players)} players missing from players table")

        if missing_players:
            logging.info(f"Missing players: {', '.join(sorted(missing_players))}")

        return missing_players

    def add_missing_player_to_roster(self, player_name: str) -> bool:
        """Add a missing player to the players table."""
        if self.dry_run:
            logging.info(f"[DRY RUN] Would add player: {player_name}")
            return True

        added = self.db.add_roster_player(
            player_name,
            added_by='Migration Script (fix_missing_players.py)',
            guild_id=self.guild_id,
            member_status='member'
        )

        if added:
            self.players_added.append(player_name)
            logging.info(f"✅ Added player to roster: {player_name}")
        else:
            logging.warning(f"⚠️ Failed to add player to roster: {player_name}")

        return added

    def recalculate_player_stats(self, player_name: str) -> Tuple[int, int]:
        """
        Recalculate player statistics and create missing performance records.

        Returns:
            Tuple of (performances_created, stats_updates)
        """
        logging.info(f"🔄 Recalculating stats for: {player_name}")

        # Get all wars this player participated in
        all_wars = self.db.get_all_wars(limit=None, guild_id=self.guild_id)

        # Get player ID from database
        player_info = self.db.get_player_info(player_name, self.guild_id)
        if not player_info:
            logging.error(f"❌ Player {player_name} not found after adding to roster")
            return 0, 0

        # Get player ID
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, self.guild_id))
                result = cursor.fetchone()
                if not result:
                    logging.error(f"❌ Could not find player ID for {player_name}")
                    return 0, 0
                player_id = result[0]
        except Exception as e:
            logging.error(f"❌ Error getting player ID for {player_name}: {e}")
            return 0, 0

        performances_created = 0
        total_score = 0
        total_races = 0
        war_count = 0
        total_team_differential = 0

        for war in all_wars:
            war_id = war['id']
            war_date = war['war_date']
            race_count = war['race_count']
            results = war.get('results', [])

            # Find this player's result in the war
            player_result = None
            for result in results:
                if result.get('name') == player_name:
                    player_result = result
                    break

            if not player_result:
                continue  # Player didn't participate in this war

            # Extract player data
            score = player_result.get('score', 0)
            races_played = player_result.get('races', 12)
            war_participation = races_played / race_count if race_count > 0 else 1.0

            # Calculate team differential for this war
            # (This logic mirrors the bot's war saving logic)
            team_differential = 0
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT team_differential FROM wars WHERE id = %s AND guild_id = %s
                    """, (war_id, self.guild_id))
                    diff_result = cursor.fetchone()
                    if diff_result and diff_result[0] is not None:
                        team_differential = diff_result[0]
            except Exception:
                pass

            # Create player_war_performances record if it doesn't exist
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()

                    # Check if performance record exists
                    cursor.execute("""
                        SELECT id FROM player_war_performances
                        WHERE player_id = %s AND war_id = %s
                    """, (player_id, war_id))

                    if not cursor.fetchone():
                        if self.dry_run:
                            logging.info(f"[DRY RUN] Would create performance record for {player_name} in war {war_id}")
                            performances_created += 1
                        else:
                            # Create the performance record
                            cursor.execute("""
                                INSERT INTO player_war_performances
                                (player_id, war_id, score, races_played, war_participation)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (player_id, war_id, score, races_played, war_participation))
                            conn.commit()
                            performances_created += 1
                            logging.info(f"✅ Created performance record for {player_name} in war {war_id}")
            except Exception as e:
                logging.error(f"❌ Error creating performance record for {player_name} in war {war_id}: {e}")

            # Accumulate stats
            total_score += score
            total_races += races_played
            war_count += 1
            total_team_differential += team_differential

        # Update player stats in players table
        if war_count > 0:
            average_score = total_score / war_count if war_count > 0 else 0.0

            if self.dry_run:
                logging.info(f"[DRY RUN] Would update stats for {player_name}:")
                logging.info(f"  Total Score: {total_score}, Total Races: {total_races}")
                logging.info(f"  War Count: {war_count}, Avg Score: {average_score:.2f}")
            else:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE players SET
                                total_score = %s,
                                total_races = %s,
                                war_count = %s,
                                average_score = %s,
                                total_team_differential = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                        """, (total_score, total_races, war_count, average_score,
                              total_team_differential, player_name, self.guild_id))
                        conn.commit()
                        self.stats_updated += 1
                        logging.info(f"✅ Updated stats for {player_name}: {war_count} wars, avg {average_score:.2f}")
                except Exception as e:
                    logging.error(f"❌ Error updating stats for {player_name}: {e}")

        return performances_created, 1 if war_count > 0 else 0

    def fix_all_missing_players(self):
        """Fix all missing players: add to roster and recalculate stats."""
        if not self.missing_players:
            logging.info("✅ No missing players to fix!")
            return

        logging.info(f"🔧 Fixing {len(self.missing_players)} missing players...")

        for player_name in sorted(self.missing_players):
            logging.info(f"\n{'='*60}")
            logging.info(f"Processing: {player_name}")
            logging.info(f"{'='*60}")

            # Add player to roster
            if self.add_missing_player_to_roster(player_name):
                # Recalculate stats
                perfs_created, stats_updated = self.recalculate_player_stats(player_name)
                self.performances_created += perfs_created
                self.stats_updated += stats_updated

        self.print_summary()

    def print_summary(self):
        """Print summary of fixes made."""
        logging.info(f"\n{'='*60}")
        logging.info("MIGRATION SUMMARY")
        logging.info(f"{'='*60}")
        logging.info(f"Guild ID: {self.guild_id}")
        logging.info(f"Dry Run: {self.dry_run}")
        logging.info(f"Missing Players Found: {len(self.missing_players)}")
        logging.info(f"Players Added to Roster: {len(self.players_added)}")
        logging.info(f"Performance Records Created: {self.performances_created}")
        logging.info(f"Player Stats Updated: {self.stats_updated}")

        if self.players_added:
            logging.info(f"\nPlayers Added:")
            for player in sorted(self.players_added):
                logging.info(f"  - {player}")

        if self.dry_run:
            logging.info("\n⚠️ DRY RUN MODE - No changes were made to the database")
        else:
            logging.info("\n✅ Migration completed successfully!")
        logging.info(f"{'='*60}\n")


def main():
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description='Fix players missing from players table due to OCR auto-add bug'
    )
    parser.add_argument(
        '--guild-id',
        type=int,
        default=0,
        help='Guild ID to process (default: 0 for legacy data)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying the database'
    )

    args = parser.parse_args()

    logging.info("="*60)
    logging.info("Missing Players Migration Script")
    logging.info("="*60)
    logging.info(f"Guild ID: {args.guild_id}")
    logging.info(f"Dry Run: {args.dry_run}")
    logging.info("="*60 + "\n")

    # Initialize database
    config = Config()
    db = DatabaseManager(config)

    # Run migration
    fixer = MissingPlayersFixer(db, guild_id=args.guild_id, dry_run=args.dry_run)
    fixer.find_missing_players()

    if fixer.missing_players:
        if args.dry_run:
            logging.info("\n⚠️ DRY RUN MODE - Review the changes above")
            logging.info("Run without --dry-run to apply these changes")
        else:
            response = input("\nProceed with fixing missing players? (yes/no): ")
            if response.lower() in ['yes', 'y']:
                fixer.fix_all_missing_players()
            else:
                logging.info("❌ Migration cancelled by user")
    else:
        logging.info("✅ No missing players found - database is consistent!")

    # Close database connection
    db.close()


if __name__ == '__main__':
    main()
