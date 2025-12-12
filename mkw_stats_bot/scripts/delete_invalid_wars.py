"""
Script to delete invalid wars from the database.
These wars were created via bulk review before the player stats update fix.
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('DATABASE_PUBLIC_URL')

if not DATABASE_URL:
    print("Error: DATABASE_URL or DATABASE_PUBLIC_URL not found in environment")
    sys.exit(1)

print(f"Connecting to database...")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # First, check how many records will be deleted
    cursor.execute("SELECT COUNT(*) FROM wars WHERE id >= 460")
    war_count = cursor.fetchone()[0]
    print(f"Found {war_count} wars with ID >= 460")

    cursor.execute("SELECT COUNT(*) FROM player_war_performances WHERE war_id >= 460")
    perf_count = cursor.fetchone()[0]
    print(f"Found {perf_count} player_war_performances records with war_id >= 460")

    if war_count == 0 and perf_count == 0:
        print("No records to delete. Exiting.")
        sys.exit(0)

    # Confirm deletion
    confirm = input(f"\nAre you sure you want to delete {war_count} wars and {perf_count} performance records? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    # First, delete related player_war_performances
    cursor.execute("DELETE FROM player_war_performances WHERE war_id >= 460")
    print(f"Deleted {cursor.rowcount} player_war_performances records")

    # Then delete the wars
    cursor.execute("DELETE FROM wars WHERE id >= 460")
    print(f"Deleted {cursor.rowcount} wars")

    conn.commit()
    print("\nDeletion committed successfully!")

except Exception as e:
    print(f"Error: {e}")
    if 'conn' in locals():
        conn.rollback()
    sys.exit(1)
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()

print("Done!")
