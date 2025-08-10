#!/usr/bin/env python3
"""
Test script to verify the nickname resolution fix works with Python lists.
"""

import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from mkw_stats.database import DatabaseManager

def setup_debug_logging():
    """Setup comprehensive debug logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def test_nickname_resolution():
    """Test the nickname resolution fix."""
    setup_debug_logging()
    
    print("🧪 TESTING NICKNAME RESOLUTION FIX")
    print("=" * 60)
    
    try:
        # Initialize database
        db = DatabaseManager()
        
        if not db.health_check():
            print("❌ Database connection failed!")
            return
            
        print("✅ Database connection successful")
        
        # From the debug output, we know the actual guild ID is 1380041421259669504
        actual_guild_id = 1380041421259669504
        
        # Test cases that should work now
        test_cases = [
            {'name': 'Beanman', 'expected': 'Cynical'},
            {'name': 'BEANMAN', 'expected': 'Cynical'},  
            {'name': 'beanman', 'expected': 'Cynical'},
            {'name': 'Christian', 'expected': 'Cynical'},
            {'name': 'cynicl', 'expected': 'Cynical'},
            {'name': 'Stikmn', 'expected': 'Stickman'},
            {'name': 'Yosh', 'expected': 'BYosh'},
            {'name': 'yosh', 'expected': 'BYosh'},  # Test case sensitivity
            {'name': 'NonExistent', 'expected': None},
        ]
        
        print(f"\n🔧 Testing with guild_id: {actual_guild_id}")
        
        success_count = 0
        total_count = len(test_cases)
        
        for i, test_case in enumerate(test_cases, 1):
            name = test_case['name']
            expected = test_case.get('expected', None)
            
            print(f"\n{i}. Testing: '{name}' (Expected: {expected})")
            print("-" * 40)
            
            # Test with debug logging to see exactly what happens
            resolved = db.resolve_player_name(name, actual_guild_id, log_level='debug')
            
            if resolved == expected:
                status = "✅ PASS"
                success_count += 1
            else:
                status = "❌ FAIL"
            
            print(f"   Result: {resolved} {status}")
        
        print(f"\n📊 TEST RESULTS: {success_count}/{total_count} passed")
        
        if success_count == total_count:
            print("🎉 ALL TESTS PASSED! Nickname resolution is working correctly.")
        else:
            print("⚠️ Some tests failed. The fix may need additional work.")
            
        db.close()
        
    except Exception as e:
        print(f"❌ Error in test: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_nickname_resolution()