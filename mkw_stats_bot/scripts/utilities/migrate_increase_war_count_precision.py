#!/usr/bin/env python3
"""
Migration: Increase war_count precision from DECIMAL(5,3) to DECIMAL(7,3)

This migration increases the maximum war_count from 99.999 to 9999.999
to support active players who exceed 100 wars.

Fixes issue where players with 100+ wars encounter numeric field overflow errors.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mkw_stats.database import DatabaseManager
from mkw_stats.config import Config
import psycopg2


def migrate_war_count_precision():
    """Increase war_count column precision from DECIMAL(5,3) to DECIMAL(7,3)"""

    config = Config()
    db = DatabaseManager(config.database_url)

    print("🔄 Starting war_count precision migration...")
    print("   Current: DECIMAL(5,3) - max value 99.999")
    print("   Target:  DECIMAL(7,3) - max value 9999.999")
    print()

    try:
        # Get a connection from the pool
        conn = db.connection_pool.getconn()
        cursor = conn.cursor()

        # Check current precision
        cursor.execute("""
            SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_name = 'players' AND column_name = 'war_count';
        """)
        current_info = cursor.fetchone()

        if current_info:
            col_name, data_type, precision, scale = current_info
            print(f"✓ Found column: {col_name}")
            print(f"  Current type: {data_type}({precision},{scale})")
            print()
        else:
            print("❌ Error: war_count column not found in players table")
            return False

        # Check if any players are close to the limit
        cursor.execute("""
            SELECT player_name, war_count
            FROM players
            WHERE war_count >= 90.0
            ORDER BY war_count DESC;
        """)
        at_risk_players = cursor.fetchall()

        if at_risk_players:
            print(f"⚠️  Found {len(at_risk_players)} player(s) at risk of overflow:")
            for name, count in at_risk_players:
                print(f"   - {name}: {count} wars")
            print()

        # Perform the migration
        print("🔧 Altering column precision...")
        cursor.execute("""
            ALTER TABLE players
            ALTER COLUMN war_count TYPE DECIMAL(7,3);
        """)

        conn.commit()
        print("✅ Migration successful!")
        print()

        # Verify the change
        cursor.execute("""
            SELECT numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_name = 'players' AND column_name = 'war_count';
        """)
        new_precision, new_scale = cursor.fetchone()
        print(f"✓ Verified new type: DECIMAL({new_precision},{new_scale})")
        print(f"  New maximum value: 9999.999 wars")
        print()

        cursor.close()
        db.connection_pool.putconn(conn)

        return True

    except psycopg2.Error as e:
        print(f"❌ Database error during migration: {e}")
        if 'conn' in locals():
            conn.rollback()
            db.connection_pool.putconn(conn)
        return False
    except Exception as e:
        print(f"❌ Unexpected error during migration: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
            db.connection_pool.putconn(conn)
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("War Count Precision Migration")
    print("=" * 60)
    print()

    success = migrate_war_count_precision()

    if success:
        print("✅ Migration completed successfully!")
        print()
        print("Players can now participate in up to 9999 wars.")
        sys.exit(0)
    else:
        print("❌ Migration failed!")
        print()
        print("Please check the error messages above and try again.")
        sys.exit(1)
