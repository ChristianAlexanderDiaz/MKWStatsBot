"""
Script to delete invalid wars from the database.
These wars were created via bulk review before the player stats update fix.
"""
import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('DATABASE_PUBLIC_URL')

if not DATABASE_URL:
    print("Error: DATABASE_URL or DATABASE_PUBLIC_URL not found in environment")
    sys.exit(1)


async def main():
    print("Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        war_count = await conn.fetchval("SELECT COUNT(*) FROM wars WHERE id >= 460")
        print(f"Found {war_count} wars with ID >= 460")

        perf_count = await conn.fetchval(
            "SELECT COUNT(*) FROM player_war_performances WHERE war_id >= 460"
        )
        print(f"Found {perf_count} player_war_performances records with war_id >= 460")

        if war_count == 0 and perf_count == 0:
            print("No records to delete. Exiting.")
            return

        confirm = await asyncio.to_thread(
            input,
            f"\nAre you sure you want to delete {war_count} wars "
            f"and {perf_count} performance records? (yes/no): "
        )
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

        async with conn.transaction():
            status = await conn.execute(
                "DELETE FROM player_war_performances WHERE war_id >= 460"
            )
            print(f"Deleted {status.split()[-1]} player_war_performances records")

            status = await conn.execute("DELETE FROM wars WHERE id >= 460")
            print(f"Deleted {status.split()[-1]} wars")

        print("\nDeletion committed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await conn.close()

    print("Done!")


if __name__ == '__main__':
    asyncio.run(main())
