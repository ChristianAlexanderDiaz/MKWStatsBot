#!/usr/bin/env python3
"""
Database inspection script to debug nickname resolution issues.
This script examines JSONB nickname data and tests various matching strategies.
"""

import sys
import os
import logging
from typing import List, Dict, Optional

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from mkw_stats.database import DatabaseManager
from mkw_stats.logging_config import setup_logging

def setup_debug_logging():
    """Setup comprehensive debug logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def inspect_nickname_data(db: DatabaseManager, guild_id: int = 0):
    """Inspect all nickname data in the database."""
    print(f"\n🔍 INSPECTING NICKNAME DATA FOR GUILD {guild_id}")
    print("=" * 60)
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all players with nicknames
            cursor.execute("""
                SELECT player_name, nicknames, guild_id, is_active
                FROM players 
                WHERE nicknames IS NOT NULL 
                ORDER BY guild_id, player_name
            """)
            
            results = cursor.fetchall()
            print(f"Found {len(results)} players with nickname data:")
            
            for i, (player_name, nicknames, player_guild, is_active) in enumerate(results, 1):
                print(f"\n{i}. Player: {player_name} (Guild: {player_guild}, Active: {is_active})")
                print(f"   Nicknames: {nicknames} (Type: {type(nicknames)})")
                
                # Test JSONB array extraction
                try:
                    cursor.execute("SELECT jsonb_array_elements_text(%s)", (nicknames,))
                    nickname_elements = [row[0] for row in cursor.fetchall()]
                    print(f"   Extracted: {nickname_elements}")
                    
                    # Test each nickname for case sensitivity
                    for nick in nickname_elements:
                        print(f"   - '{nick}' (length: {len(nick)})")
                        print(f"     lowercase: '{nick.lower()}'")
                        print(f"     uppercase: '{nick.upper()}'")
                        
                except Exception as e:
                    print(f"   ❌ Error extracting nicknames: {e}")
                    
    except Exception as e:
        print(f"❌ Error inspecting nickname data: {e}")

def test_nickname_resolution(db: DatabaseManager, test_cases: List[Dict], guild_id: int = 0):
    """Test nickname resolution with various cases."""
    print(f"\n🧪 TESTING NICKNAME RESOLUTION FOR GUILD {guild_id}")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        name = test_case['name']
        expected = test_case.get('expected', None)
        
        print(f"\n{i}. Testing: '{name}' (Expected: {expected})")
        print("-" * 40)
        
        # Test with debug logging
        resolved = db.resolve_player_name(name, guild_id, log_level='debug')
        
        if resolved:
            status = "✅ PASS" if resolved == expected else "⚠️ UNEXPECTED"
            print(f"   Result: '{resolved}' {status}")
        else:
            status = "❌ FAIL" if expected else "✅ EXPECTED"
            print(f"   Result: None {status}")

def test_direct_sql_queries(db: DatabaseManager, guild_id: int = 0):
    """Test SQL queries directly to isolate issues."""
    print(f"\n🔧 TESTING DIRECT SQL QUERIES FOR GUILD {guild_id}")
    print("=" * 60)
    
    test_name = "Beanman"
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Test 1: Basic JSONB containment
            print(f"\n1. Testing JSONB ? operator for '{test_name}':")
            cursor.execute("""
                SELECT player_name, nicknames
                FROM players 
                WHERE guild_id = %s AND is_active = TRUE AND nicknames ? %s
            """, (guild_id, test_name))
            
            results = cursor.fetchall()
            print(f"   Results: {results}")
            
            # Test 2: Case-insensitive JSONB search
            print(f"\n2. Testing case-insensitive JSONB search for '{test_name}':")
            cursor.execute("""
                SELECT player_name, nicknames
                FROM players 
                WHERE guild_id = %s 
                AND is_active = TRUE
                AND nicknames IS NOT NULL
                AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(nicknames) AS nickname
                    WHERE LOWER(nickname) = LOWER(%s)
                )
            """, (guild_id, test_name))
            
            results = cursor.fetchall()
            print(f"   Results: {results}")
            
            # Test 3: Manual nickname extraction and comparison
            print(f"\n3. Manual nickname extraction for guild {guild_id}:")
            cursor.execute("""
                SELECT player_name, nickname
                FROM players p,
                     jsonb_array_elements_text(p.nicknames) AS nickname
                WHERE p.guild_id = %s AND p.is_active = TRUE
                ORDER BY player_name, nickname
            """, (guild_id,))
            
            results = cursor.fetchall()
            print(f"   All nicknames in guild:")
            for player, nick in results:
                match_status = "✅ MATCH" if nick.lower() == test_name.lower() else ""
                print(f"   - {player}: '{nick}' {match_status}")
            
            # Test 4: Alternative JSONB text search
            print(f"\n4. Testing alternative JSONB text search for '{test_name}':")
            cursor.execute("""
                SELECT player_name, nicknames
                FROM players 
                WHERE guild_id = %s 
                AND is_active = TRUE
                AND nicknames IS NOT NULL
                AND LOWER(nicknames::text) LIKE LOWER(%s)
            """, (guild_id, f'%"{test_name}"%'))
            
            results = cursor.fetchall()
            print(f"   Results: {results}")
            
    except Exception as e:
        print(f"❌ Error in direct SQL testing: {e}")
        import traceback
        print(f"   Full traceback: {traceback.format_exc()}")

def check_postgresql_version(db: DatabaseManager):
    """Check PostgreSQL version for compatibility."""
    print(f"\n📋 POSTGRESQL VERSION CHECK")
    print("=" * 60)
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"PostgreSQL Version: {version}")
            
            # Check for jsonpath support (PostgreSQL 12+)
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_proc 
                    WHERE proname = 'jsonb_path_exists'
                )
            """)
            
            has_jsonpath = cursor.fetchone()[0]
            print(f"JSONPath Support: {'✅ Yes' if has_jsonpath else '❌ No'}")
            
            if has_jsonpath:
                print("✅ Can use modern jsonpath-based case-insensitive matching")
            else:
                print("⚠️ Limited to traditional JSONB functions")
                
    except Exception as e:
        print(f"❌ Error checking PostgreSQL version: {e}")

def main():
    """Main inspection function."""
    setup_debug_logging()
    
    print("🔍 NICKNAME RESOLUTION DEBUG TOOL")
    print("=" * 60)
    
    try:
        # Initialize database
        db = DatabaseManager()
        
        if not db.health_check():
            print("❌ Database connection failed!")
            return
            
        print("✅ Database connection successful")
        
        # Check PostgreSQL version and capabilities
        check_postgresql_version(db)
        
        # Inspect all nickname data
        inspect_nickname_data(db)
        
        # Define test cases based on the issue
        test_cases = [
            {'name': 'Beanman', 'expected': 'Cynical'},  # This should resolve to Cynical
            {'name': 'BEANMAN', 'expected': 'Cynical'},  # This should also resolve to Cynical
            {'name': 'beanman', 'expected': 'Cynical'},  # This should also resolve to Cynical
            {'name': 'Cynical', 'expected': 'Cynical'},  # Direct name match
            {'name': 'NonExistent', 'expected': None},   # Should not match anything
        ]
        
        # Test nickname resolution
        test_nickname_resolution(db, test_cases)
        
        # Test direct SQL queries
        test_direct_sql_queries(db)
        
        print(f"\n✅ NICKNAME RESOLUTION DEBUG COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error in main execution: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()