#!/usr/bin/env python3
"""
OCR Testing Tool

Test OCR processing on sample images and debug extraction issues.
Usage: python testing/test_ocr.py [image_path]
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mkw_stats.ocr_processor_paddle import PaddleXOCRProcessor
from mkw_stats.database import DatabaseManager
from mkw_stats import config
import json
from datetime import datetime

def test_ocr_processing(image_path: str):
    """Test OCR processing on a specific image."""
    
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        return
    
    print(f"🔍 Testing OCR processing on: {image_path}")
    print("=" * 50)
    
    # Initialize OCR processor with database
    db = DatabaseManager()
    ocr = PaddleXOCRProcessor(db_manager=db)
    
    # Process the image
    results = ocr.process_image(image_path)
    
    # Display results
    print(f"✅ Success: {results['success']}")
    
    if not results['success']:
        print(f"❌ Error: {results.get('error', 'Unknown error')}")
        return
    
    print(f"📊 Results found: {len(results['results'])}")
    print()
    
    # Show extracted results
    if results['results']:
        print("🎯 Extracted Players:")
        for i, result in enumerate(results['results'], 1):
            print(f"  {i}. {result['name']}: {result['score']} points")
            if 'raw_name' in result:
                print(f"     (detected as: '{result['raw_name']}')")
        print()
    
    # Show validation
    validation = results.get('validation', {})
    if validation:
        print("✅ Validation Results:")
        print(f"  Valid: {validation.get('is_valid', 'Unknown')}")
        print(f"  Player count: {validation.get('player_count', 0)}")
        print(f"  Ideal count: {validation.get('is_ideal_count', False)}")
        
        if validation.get('warnings'):
            print("  ⚠️  Warnings:")
            for warning in validation['warnings']:
                print(f"    - {warning}")
        
        if validation.get('errors'):
            print("  ❌ Errors:")
            for error in validation['errors']:
                print(f"    - {error}")
        print()
    
    # Show raw OCR text for debugging
    print("🔤 Raw OCR Text (for debugging):")
    texts = ocr.extract_text_from_image(image_path)
    for i, text in enumerate(texts, 1):
        print(f"  Method {i}:")
        print("  " + "-" * 30)
        for line in text.split('\n')[:10]:  # Show first 10 lines
            if line.strip():
                print(f"  {line}")
        print()

def test_nickname_resolution():
    """Test nickname resolution with database."""
    print("🔍 Testing Nickname Resolution")
    print("=" * 30)
    
    db = DatabaseManager()
    
    test_names = [
        "Cynical", "Cyn", "Christian", "Cynicl",
        "rx", "Astral", "Astralixv", 
        "Corbs", "myst",
        "Quick", "Q",
        "DEMISE", "Demise",
        "Jake", "J",
        "Unknown Player"
    ]
    
    for name in test_names:
        resolved = db.resolve_player_name(name)
        if resolved:
            if resolved == name:
                print(f"  ✅ '{name}' → '{resolved}' (exact match)")
            else:
                print(f"  🔄 '{name}' → '{resolved}' (nickname resolved)")
        else:
            print(f"  ❌ '{name}' → NOT FOUND")

def main():
    """Main testing function."""
    
    if len(sys.argv) > 1:
        # Test specific image
        image_path = sys.argv[1]
        test_ocr_processing(image_path)
    else:
        # Test nickname resolution
        test_nickname_resolution()
        print()
        
        # Look for sample images
        sample_dir = "testing/sample_images"
        if os.path.exists(sample_dir):
            print("📁 Sample images found:")
            for filename in os.listdir(sample_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    print(f"  - {filename}")
            print("\nUsage: python testing/test_ocr.py testing/sample_images/[filename]")
        else:
            print("📁 No sample images directory found.")
            print("Create 'testing/sample_images/' and add test images.")
            print("\nUsage: python testing/test_ocr.py [path_to_image]")

if __name__ == "__main__":
    main() 