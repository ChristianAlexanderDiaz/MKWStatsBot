#!/usr/bin/env python3
"""
Mario Kart Bot - Table Preset Setup Tool

This tool helps you create table format presets for consistent OCR processing.
Run this with a sample image to define regions for 6v6 table format.
"""

import sys
import os
from utils.region_selector import RegionSelector
from src.ocr_processor import OCRProcessor
from src import config
import json

def setup_table_preset():
    """Interactive setup for table format presets."""
    print("🏁 Mario Kart Table Preset Setup Tool")
    print("=" * 50)
    print("This tool helps you create table format presets for consistent OCR.")
    print("You'll select regions on a sample image that will be saved for future use.")
    print()
    
    if len(sys.argv) != 2:
        print("Usage: python setup_preset.py <sample_image_path>")
        print("Example: python setup_preset.py sample_6v6_results.png")
        print()
        print("Use a clear, representative image of your 6v6 Mario Kart results table.")
        return
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"❌ Error: Image file '{image_path}' not found!")
        return
    
    print(f"📷 Using sample image: {image_path}")
    print()
    print("🔧 Instructions:")
    print("1. The region selector will open")
    print("2. Draw rectangles around each team's player list area")
    print("3. Typically you'll want 2 regions: one for each team")
    print("4. Press 's' to save regions, 'q' to quit")
    print("5. The preset will be saved for future automatic use")
    print()
    
    input("Press Enter to start region selection...")
    
    # Use region selector to define areas
    selector = RegionSelector(image_path)
    regions = selector.run_interactive_selection()
    
    if not regions:
        print("❌ No regions selected. Setup cancelled.")
        return
    
    print(f"\n✅ Selected {len(regions)} regions")
    
    # Get preset details
    preset_name = input("\nEnter preset name (e.g., 'format_1'): ").strip()
    if not preset_name:
        preset_name = "format_1"
    
    description = input("Enter description (optional): ").strip()
    if not description:
        description = f"6v6 table format with {len(regions)} regions"
    
    # Save the preset
    ocr = OCRProcessor()
    success = ocr.save_preset(preset_name, regions, description)
    
    if success:
        print(f"\n✅ Preset '{preset_name}' saved successfully!")
        print(f"📋 Description: {description}")
        print(f"🔖 Regions: {len(regions)}")
        print("\nThis preset is now available for the Discord bot to use automatically.")
        print("The bot will use this preset to process images with the same table format.")
        
        # Test the preset
        test_choice = input("\nWould you like to test this preset now? (y/n): ").strip().lower()
        if test_choice == 'y':
            print("\n🧪 Testing preset...")
            results = ocr.process_image_with_preset(image_path, preset_name)
            
            if results['success']:
                print(f"✅ Test successful! Found {results['total_found']} players:")
                for i, result in enumerate(results['results'], 1):
                    print(f"  {i}. {result['name']}: {result['score']}")
                
                validation = results.get('validation', {})
                if validation.get('warnings'):
                    print("\n⚠️ Warnings:")
                    for warning in validation['warnings']:
                        print(f"  • {warning}")
            else:
                print(f"❌ Test failed: {results.get('error', 'Unknown error')}")
        
    else:
        print(f"❌ Failed to save preset '{preset_name}'")

def list_existing_presets():
    """List all existing presets."""
    print("📋 Existing Table Presets:")
    print("-" * 30)
    
    ocr = OCRProcessor()
    
    if config.TABLE_PRESETS:
        for name, preset in config.TABLE_PRESETS.items():
            regions_count = len(preset.get('regions', []))
            print(f"🔖 {name}")
            print(f"   Description: {preset.get('description', 'No description')}")
            print(f"   Regions: {regions_count}")
            print(f"   Expected players: {preset.get('expected_players', 6)}")
            print()
    else:
        print("No presets found.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_existing_presets()
    else:
        setup_table_preset() 