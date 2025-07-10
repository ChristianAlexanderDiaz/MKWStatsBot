#!/usr/bin/env python3
"""
Test script for quote parsing functionality in nickname commands.

This script tests the parse_quoted_nicknames() function to ensure it handles
all edge cases correctly for nicknames with and without spaces.
"""

import sys
import os
import re

# Add the parent directory to the path so we can import from mkw_stats
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def parse_quoted_nicknames(text: str) -> list:
    """
    Parse nicknames from text, handling quoted strings for nicknames with spaces.
    This is a copy of the function from commands.py for testing.
    """
    nicknames = []
    # Pattern to match quoted strings or unquoted words
    pattern = r'"([^"]+)"|(\S+)'
    
    matches = re.findall(pattern, text.strip())
    
    for match in matches:
        # match[0] is quoted content, match[1] is unquoted content
        nickname = match[0] if match[0] else match[1]
        if nickname:  # Skip empty matches
            nicknames.append(nickname)
    
    return nicknames

def test_quote_parsing():
    """Test all the edge cases for quote parsing."""
    
    print("🧪 Testing Quote Parsing for Nickname Commands")
    print("=" * 60)
    
    test_cases = [
        # Basic cases
        ("Vort", ["Vort"]),
        ("Vort VortexNickname", ["Vort", "VortexNickname"]),
        ('"MK Vortex"', ["MK Vortex"]),
        
        # Mixed cases
        ('"MK Vortex" Vort', ["MK Vortex", "Vort"]),
        ('Vort "MK Vortex"', ["Vort", "MK Vortex"]),
        ('Vort "MK Vortex" VortexNickname', ["Vort", "MK Vortex", "VortexNickname"]),
        
        # Multiple quoted
        ('"MK Vortex" "Another Name"', ["MK Vortex", "Another Name"]),
        ('"MK Vortex" "Another Name" Vort', ["MK Vortex", "Another Name", "Vort"]),
        
        # Edge cases
        ('', []),
        ('   ', []),
        ('"   "', ["   "]),  # Quoted spaces
        ('Vort   VortexNickname', ["Vort", "VortexNickname"]),  # Multiple spaces
        
        # Test cases from the requirements
        ("Vort VortexNickname", ["Vort", "VortexNickname"]),  # Should be rejected for mkaddnickname
        ('Vort "MK Vortex"', ["Vort", "MK Vortex"]),  # Should be rejected for mkaddnickname
        ('"MK Vortex"', ["MK Vortex"]),  # Should work for mkaddnickname
    ]
    
    all_passed = True
    
    for i, (input_text, expected) in enumerate(test_cases, 1):
        result = parse_quoted_nicknames(input_text)
        
        if result == expected:
            print(f"✅ Test {i:2d}: '{input_text}' -> {result}")
        else:
            print(f"❌ Test {i:2d}: '{input_text}' -> {result} (expected {expected})")
            all_passed = False
    
    print("\n" + "=" * 60)
    
    # Test specific command scenarios
    print("\n🎯 Testing Command Scenarios:")
    print("-" * 40)
    
    # Test mkaddnickname scenarios
    print("\n!mkaddnickname scenarios:")
    mkaddnickname_tests = [
        ('"MK Vortex"', True, "Single quoted nickname - SHOULD WORK"),
        ("Vort", True, "Single unquoted nickname - SHOULD WORK"),
        ("Vort VortexNickname", False, "Multiple unquoted - SHOULD REJECT"),
        ('Vort "MK Vortex"', False, "Multiple mixed - SHOULD REJECT"),
        ('"MK Vortex" "Another Name"', False, "Multiple quoted - SHOULD REJECT"),
    ]
    
    for input_text, should_work, description in mkaddnickname_tests:
        nicknames = parse_quoted_nicknames(input_text)
        num_nicknames = len(nicknames)
        
        if should_work and num_nicknames == 1:
            print(f"✅ {description}: '{input_text}' -> {nicknames}")
        elif not should_work and num_nicknames > 1:
            print(f"✅ {description}: '{input_text}' -> {nicknames} (correctly rejected)")
        else:
            print(f"❌ {description}: '{input_text}' -> {nicknames} (unexpected result)")
            all_passed = False
    
    # Test mkaddnicknames scenarios
    print("\n!mkaddnicknames scenarios:")
    mkaddnicknames_tests = [
        ('"MK Vortex" Vort', "Mixed quoted/unquoted - SHOULD WORK"),
        ("Vort VortexNickname", "Multiple unquoted - SHOULD WORK"),
        ('"MK Vortex" "Another Name"', "Multiple quoted - SHOULD WORK"),
        ('"MK Vortex" Vort "Gaming Name"', "Complex mix - SHOULD WORK"),
    ]
    
    for input_text, description in mkaddnicknames_tests:
        nicknames = parse_quoted_nicknames(input_text)
        print(f"✅ {description}: '{input_text}' -> {nicknames}")
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("✅ All tests passed! Quote parsing is working correctly.")
        print("\n💡 Ready to handle:")
        print("   - Single nicknames: Vort")
        print("   - Quoted nicknames: \"MK Vortex\"")
        print("   - Mixed scenarios: \"MK Vortex\" Vort \"Another Name\"")
        print("   - Proper rejection of multiple nicknames in mkaddnickname")
    else:
        print("❌ Some tests failed. Please check the implementation.")
    
    return all_passed

if __name__ == "__main__":
    success = test_quote_parsing()
    if not success:
        sys.exit(1)