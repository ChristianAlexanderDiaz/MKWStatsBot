#!/usr/bin/env python3
"""
Migration script to consolidate roster and player_stats tables into unified players table.
WARNING: This will drop existing data - for testing purposes only.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mkw_stats.database import DatabaseManager
import logging

def migrate_to_unified_players():
    """Drop old tables and create unified players table."""
    try:
        db = DatabaseManager()
        
        print("🔄 Starting migration to unified players table...")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Drop old tables (no backup - testing only)
            print("🗑️  Dropping old tables...")
            cursor.execute("DROP TABLE IF EXISTS player_stats CASCADE")
            cursor.execute("DROP TABLE IF EXISTS roster CASCADE")
            print("✅ Old tables dropped")
            
            # Create unified players table
            print("🏗️  Creating unified players table...")
            cursor.execute("""
                CREATE TABLE players (
                    id SERIAL PRIMARY KEY,
                    player_name VARCHAR(100) NOT NULL,
                    guild_id BIGINT NOT NULL,
                    team VARCHAR(50) DEFAULT 'Unassigned',
                    nicknames JSONB DEFAULT '[]',
                    added_by VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    -- Statistics fields
                    total_score INTEGER DEFAULT 0,
                    total_races INTEGER DEFAULT 0,
                    war_count INTEGER DEFAULT 0,
                    average_score DECIMAL(5,2) DEFAULT 0.0,
                    last_war_date DATE,
                    -- Metadata
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(player_name, guild_id)
                );
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX idx_players_guild_id ON players(guild_id);
                CREATE INDEX idx_players_active ON players(is_active);
                CREATE INDEX idx_players_team ON players(team);
                CREATE INDEX idx_players_name ON players(player_name);
            """)
            
            # Create trigger to update updated_at timestamp
            cursor.execute("""
                CREATE OR REPLACE FUNCTION update_players_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
                
                CREATE TRIGGER update_players_updated_at 
                    BEFORE UPDATE ON players 
                    FOR EACH ROW 
                    EXECUTE FUNCTION update_players_updated_at();
            """)
            
            conn.commit()
            print("✅ Unified players table created successfully")
            
            # Verify table structure
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'players' AND table_schema = 'public'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            
            print("\n📋 New players table structure:")
            for col_name, data_type, nullable in columns:
                null_info = "NULL" if nullable == "YES" else "NOT NULL"
                print(f"   {col_name:<20} {data_type:<15} {null_info}")
            
            print("\n🎉 Migration completed successfully!")
            print("Next steps:")
            print("- Use /setup command to initialize guilds")
            print("- Use !mkadd command to add players")
            print("- Use /addwar command to track wars")
            
        return True
        
    except Exception as e:
        logging.error(f"❌ Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = migrate_to_unified_players()
    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)