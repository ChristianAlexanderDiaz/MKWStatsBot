#!/usr/bin/env python3
"""
Database migration to add bulk_scan_failures table.
This migration adds:
- bulk_scan_failures: Stores failed bulk scan images with Discord metadata
"""

import sys
import os
import logging

# Add the parent directory to sys.path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
from mkw_stats.config import DATABASE_URL


def migrate_add_bulk_scan_failures():
    """Add bulk_scan_failures table for storing failed image metadata."""
    print("Starting bulk_scan_failures migration...")

    try:
        # Initialize database connection
        db = DatabaseManager(DATABASE_URL)
        print("Database connection established")

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if bulk_scan_failures table already exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'bulk_scan_failures'
                );
            """)

            if cursor.fetchone()[0]:
                print("bulk_scan_failures table already exists, skipping migration")
                return True

            print("Creating bulk_scan_failures table...")

            # Create bulk_scan_failures table
            cursor.execute("""
                CREATE TABLE bulk_scan_failures (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES bulk_scan_sessions(id) ON DELETE CASCADE,
                    image_filename VARCHAR(255),
                    image_url TEXT,
                    error_message TEXT,
                    message_timestamp TIMESTAMP WITH TIME ZONE,
                    discord_message_id BIGINT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX idx_bulk_failures_session ON bulk_scan_failures(session_id)
            """)

            print("bulk_scan_failures table created")

            conn.commit()
            print("Migration completed successfully")

            # Verify the migration
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'bulk_scan_failures'
                ORDER BY ordinal_position
            """)

            columns = cursor.fetchall()
            print(f"Migration verification:")
            print(f"   Columns: {', '.join([col[0] for col in columns])}")

            return True

    except Exception as e:
        print(f"Migration failed: {e}")
        logging.error(f"bulk_scan_failures migration error: {e}")
        return False


def main():
    """Run the migration."""
    logging.basicConfig(level=logging.INFO)

    print("MKW Stats Bot - Bulk Scan Failures Migration")
    print("=" * 50)

    success = migrate_add_bulk_scan_failures()

    if success:
        print("\nMigration completed successfully!")
    else:
        print("\nMigration failed!")
        print("Check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
