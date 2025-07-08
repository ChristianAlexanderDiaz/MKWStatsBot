#!/usr/bin/env python3
"""
PostgreSQL table deletion script for mkw_stats_bot.

Usage:
    python delete_table.py --table players
    python delete_table.py --table wars
    python delete_table.py --table roster

Safety features:
- Lists all available tables
- Confirms table exists before deletion
- Requires user confirmation
- Handles database connection errors
"""

import argparse
import sys
import os
from typing import List

# Add the mkw_stats module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mkw_stats'))

from mkw_stats.database import DatabaseManager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def list_tables(db: DatabaseManager) -> List[str]:
    """List all tables in the database."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logging.error(f"Error listing tables: {e}")
        return []

def table_exists(db: DatabaseManager, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = %s
                );
            """, (table_name,))
            return cursor.fetchone()[0]
    except Exception as e:
        logging.error(f"Error checking if table exists: {e}")
        return False

def delete_table(db: DatabaseManager, table_name: str) -> bool:
    """Delete a table from the database."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Use double quotes to handle case-sensitive table names
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error deleting table '{table_name}': {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Delete a PostgreSQL table from mkw_stats_bot database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python delete_table.py --table players
    python delete_table.py --table wars
    python delete_table.py --table roster
        """
    )
    parser.add_argument(
        '--table', 
        required=True, 
        help='Name of the table to delete'
    )
    
    args = parser.parse_args()
    table_name = args.table
    
    print(f"🔍 Connecting to PostgreSQL database...")
    
    # Initialize database connection
    try:
        db = DatabaseManager()
        if not db.health_check():
            print("❌ Database connection failed!")
            sys.exit(1)
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    # List all available tables
    print("\n📋 Available tables:")
    tables = list_tables(db)
    if not tables:
        print("   No tables found in the database")
        db.close()
        sys.exit(1)
    
    for table in tables:
        print(f"   • {table}")
    
    # Check if the specified table exists
    if not table_exists(db, table_name):
        print(f"\n❌ Table '{table_name}' does not exist!")
        print(f"Available tables: {', '.join(tables)}")
        db.close()
        sys.exit(1)
    
    # Confirmation prompt
    print(f"\n⚠️  WARNING: You are about to delete table '{table_name}'")
    print("This action cannot be undone!")
    print("All data in this table will be permanently lost.")
    
    confirm = input(f"\nType 'DELETE {table_name}' to confirm: ")
    
    if confirm != f"DELETE {table_name}":
        print("❌ Deletion cancelled - confirmation text did not match")
        db.close()
        sys.exit(1)
    
    # Delete the table
    print(f"\n🗑️  Deleting table '{table_name}'...")
    
    if delete_table(db, table_name):
        print(f"✅ Table '{table_name}' deleted successfully!")
        
        # Show remaining tables
        remaining_tables = list_tables(db)
        if remaining_tables:
            print(f"\nRemaining tables: {', '.join(remaining_tables)}")
        else:
            print("\nNo tables remain in the database")
    else:
        print(f"❌ Failed to delete table '{table_name}'")
        sys.exit(1)
    
    # Close database connection
    db.close()
    print("\n✅ Database connection closed")

if __name__ == "__main__":
    main()