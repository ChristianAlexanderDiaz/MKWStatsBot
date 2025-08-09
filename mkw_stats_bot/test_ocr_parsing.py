#!/usr/bin/env python3
"""
Quick test of the improved OCR parsing logic
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mkw_stats.ocr_processor import OCRProcessor
from mkw_stats.database import DatabaseManager
from mkw_stats import config
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

def test_ocr_parsing():
    """Test the new OCR parsing logic with sample data"""
    
    # Create database manager
    db = DatabaseManager()
    
    # Create OCR processor  
    ocr = OCRProcessor(db_manager=db)
    
    # Test cases
    test_cases = [
        {
            "name": "Perfect case",
            "ocr_text": "Cynical 102 Hero 95 Stickman 93",
            "expected_players": ["Cynical", "Hero", "Stickman"]
        },
        {
            "name": "Problem case (score before name)",
            "ocr_text": "103 peet Morgana 84",
            "expected_players": ["peet", "Morgana"] 
        },
        {
            "name": "Duplicate scores",
            "ocr_text": "Cynical 102 102 brad",
            "expected_players": ["Cynical", "brad"]
        },
        {
            "name": "Multi-word names",
            "ocr_text": "No name 64 kyle christian 40",
            "expected_players": ["No name", "kyle christian"]
        }
    ]
    
    # Use guild_id = 0 for testing (adjust if needed)
    test_guild_id = 0
    
    print(f"🧪 Testing improved OCR parsing logic...")
    print(f"📊 Using guild_id: {test_guild_id}")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\\n🔍 Test {i}: {test_case['name']}")
        print(f"📝 Input: \"{test_case['ocr_text']}\"")
        
        # Create fake extracted_texts format
        extracted_texts = [{"text": test_case['ocr_text'], "confidence": 0.9}]
        
        # Run parsing
        try:
            results = ocr._parse_mario_kart_results(extracted_texts, test_guild_id)
            
            print(f"✅ Found {len(results)} players:")
            for result in results:
                print(f"   👤 {result['name']} (raw: '{result['raw_name']}') - {result['score']} points")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\\n" + "=" * 60)
    print("🎉 Testing complete!")

if __name__ == "__main__":
    test_ocr_parsing()