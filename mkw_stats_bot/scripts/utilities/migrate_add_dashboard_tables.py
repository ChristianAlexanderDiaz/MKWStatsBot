#!/usr/bin/env python3
"""
Database migration to add dashboard tables for the MKW Review Web Dashboard.
This migration adds:
- bulk_scan_sessions: Tracks bulk scan review sessions
- bulk_scan_results: Individual OCR results within sessions
- user_sessions: Web authentication sessions for Discord OAuth
"""

import sys
import os
import logging

# Add the parent directory to sys.path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
from mkw_stats.config import DATABASE_URL


def migrate_add_dashboard_tables():
    """Add dashboard tables for the web review interface."""
    print("Starting dashboard tables migration...")

    try:
        # Initialize database connection
        db = DatabaseManager(DATABASE_URL)
        print("Database connection established")

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if bulk_scan_sessions table already exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'bulk_scan_sessions'
                );
            """)

            if cursor.fetchone()[0]:
                print("Dashboard tables already exist, skipping migration")
                return True

            print("Creating bulk_scan_sessions table...")

            # Create bulk_scan_sessions table
            cursor.execute("""
                CREATE TABLE bulk_scan_sessions (
                    id SERIAL PRIMARY KEY,
                    token UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    guild_id BIGINT NOT NULL,
                    created_by_user_id BIGINT NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    total_images INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'),
                    completed_at TIMESTAMP WITH TIME ZONE
                )
            """)

            cursor.execute("""
                CREATE INDEX idx_bulk_sessions_token ON bulk_scan_sessions(token)
            """)
            cursor.execute("""
                CREATE INDEX idx_bulk_sessions_guild ON bulk_scan_sessions(guild_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_bulk_sessions_status ON bulk_scan_sessions(status)
            """)

            print("bulk_scan_sessions table created")

            print("Creating bulk_scan_results table...")

            # Create bulk_scan_results table
            cursor.execute("""
                CREATE TABLE bulk_scan_results (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES bulk_scan_sessions(id) ON DELETE CASCADE,
                    image_filename VARCHAR(255),
                    image_url TEXT,
                    detected_players JSONB NOT NULL,
                    review_status VARCHAR(20) DEFAULT 'pending',
                    corrected_players JSONB,
                    race_count INTEGER DEFAULT 12,
                    message_timestamp TIMESTAMP WITH TIME ZONE,
                    discord_message_id BIGINT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP WITH TIME ZONE
                )
            """)

            cursor.execute("""
                CREATE INDEX idx_bulk_results_session ON bulk_scan_results(session_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_bulk_results_status ON bulk_scan_results(review_status)
            """)

            print("bulk_scan_results table created")

            print("Creating user_sessions table...")

            # Create user_sessions table
            cursor.execute("""
                CREATE TABLE user_sessions (
                    id SERIAL PRIMARY KEY,
                    discord_user_id BIGINT NOT NULL,
                    discord_username VARCHAR(100),
                    discord_avatar VARCHAR(255),
                    session_token UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    access_token_encrypted TEXT,
                    refresh_token_encrypted TEXT,
                    guild_permissions JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '7 days'),
                    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX idx_user_sessions_discord_id ON user_sessions(discord_user_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_user_sessions_token ON user_sessions(session_token)
            """)

            print("user_sessions table created")

            conn.commit()
            print("All dashboard tables created successfully")

            # Verify the migration
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('bulk_scan_sessions', 'bulk_scan_results', 'user_sessions')
                ORDER BY table_name
            """)

            tables = [row[0] for row in cursor.fetchall()]
            print(f"Migration verification:")
            print(f"   Created tables: {', '.join(tables)}")

            return True

    except Exception as e:
        print(f"Migration failed: {e}")
        logging.error(f"Dashboard tables migration error: {e}")
        return False


def main():
    """Run the migration."""
    logging.basicConfig(level=logging.INFO)

    print("MKW Stats Bot - Dashboard Tables Migration")
    print("=" * 50)

    success = migrate_add_dashboard_tables()

    if success:
        print("\nMigration completed successfully!")
        print("Next steps:")
        print("   1. Deploy the mkw-dashboard-api service")
        print("   2. Deploy the mkw-review-web service")
        print("   3. Update bot environment variables")
        print("   4. Test the /bulkscanimage command")
    else:
        print("\nMigration failed!")
        print("Check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
