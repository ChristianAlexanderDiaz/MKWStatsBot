#!/usr/bin/env python3
"""
Migration script to increase war_count column precision to support 100+ wars.
Changes war_count from DECIMAL(5,3) to DECIMAL(8,3) to support up to 99,999.999 wars.

ISSUE: Players with 100+ wars trigger overflow error with DECIMAL(5,3) which maxes at 99.999
SOLUTION: Increase precision to DECIMAL(8,3) which supports up to 99,999.999 wars
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
import logging

def migrate_increase_war_count_precision():
    """Update war_count column from DECIMAL(5,3) to DECIMAL(8,3) to support higher war counts."""
    try:
        db = DatabaseManager()

        print("🔄 Starting migration to increase war_count precision...")
        print("📊 This will update war_count from DECIMAL(5,3) to DECIMAL(8,3)")
        print("✅ Max value will increase from 99.999 to 99,999.999")

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check current column type and precision
            cursor.execute("""
                SELECT data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_name = 'players'
                AND column_name = 'war_count'
                AND table_schema = 'public';
            """)

            current_info = cursor.fetchone()
            if current_info:
                print(f"📋 Current war_count type: {current_info[0]} (precision: {current_info[1]}, scale: {current_info[2]})")
            else:
                print("❌ Could not find war_count column in players table")
                return False

            # Check if any players currently have war_count >= 100
            cursor.execute("""
                SELECT player_name, war_count, guild_id
                FROM players
                WHERE war_count >= 100
                ORDER BY war_count DESC
                LIMIT 10;
            """)

            high_war_players = cursor.fetchall()
            if high_war_players:
                print(f"\n⚠️  Found {len(high_war_players)} player(s) with 100+ wars:")
                for player_name, war_count, guild_id in high_war_players:
                    print(f"   - {player_name}: {war_count} wars (guild {guild_id})")
                print("   These players are currently blocked from adding new wars!")
            else:
                print("\n✅ No players currently at 100+ wars (migration is preventative)")

            # Update column type to DECIMAL(8,3)
            print("\n🔧 Updating war_count column to DECIMAL(8,3)...")
            cursor.execute("""
                ALTER TABLE players
                ALTER COLUMN war_count TYPE DECIMAL(8,3);
            """)

            # Verify the change
            cursor.execute("""
                SELECT data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_name = 'players'
                AND column_name = 'war_count'
                AND table_schema = 'public';
            """)

            new_info = cursor.fetchone()
            if new_info:
                print(f"✅ Updated war_count type: {new_info[0]} (precision: {new_info[1]}, scale: {new_info[2]})")

            # Show stats on current war counts
            cursor.execute("""
                SELECT
                    MAX(war_count) as max_wars,
                    MIN(war_count) as min_wars,
                    AVG(war_count) as avg_wars,
                    COUNT(*) as total_players
                FROM players
                WHERE is_active = TRUE;
            """)

            stats = cursor.fetchone()
            if stats:
                max_wars, min_wars, avg_wars, total_players = stats
                print(f"\n📊 Current War Statistics:")
                print(f"   - Total active players: {total_players}")
                print(f"   - Maximum wars: {max_wars}")
                print(f"   - Minimum wars: {min_wars}")
                print(f"   - Average wars: {avg_wars:.2f}" if avg_wars else "   - Average wars: 0.00")

            conn.commit()
            print("\n✅ Migration completed successfully!")

            print("\n📋 What this fixes:")
            print("✅ Players can now have up to 99,999.999 wars (previously limited to 99.999)")
            print("✅ Fractional war support preserved (e.g., 0.583 for 7/12 races)")
            print("✅ Fully backwards compatible with existing data")
            print("✅ No downtime required (instant schema change)")

            print("\n🔄 Rollback Instructions (if needed):")
            print("   ALTER TABLE players ALTER COLUMN war_count TYPE DECIMAL(5,3);")
            print("   ⚠️  WARNING: Rollback will FAIL if any player has war_count >= 100")

        return True

    except Exception as e:
        logging.error(f"❌ Migration failed: {e}")
        print(f"\n❌ Migration failed: {e}")
        print("\n🔄 Database has been rolled back (no changes applied)")
        return False

if __name__ == "__main__":
    success = migrate_increase_war_count_precision()
    if success:
        print("\n✅ Migration completed successfully!")
        print("🎮 Players with 100+ wars can now add new wars without errors!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
