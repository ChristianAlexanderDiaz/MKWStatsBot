#!/usr/bin/env python3
import sys
import os
from src.ocr_processor import OCRProcessor
from src import config

def test_ocr_on_image(image_path):
    """Test OCR processing on a specific image."""
    
    if not os.path.exists(image_path):
        print(f"❌ Error: Image file '{image_path}' not found!")
        return
    
    print(f"🔍 Testing OCR on: {image_path}")
    print("=" * 60)
    
    # Initialize OCR processor
    ocr = OCRProcessor()
    
    try:
        # Extract raw text
        print("📝 Step 1: Extracting raw text from image...")
        raw_text = ocr.extract_text_from_image(image_path)
        
        print("Raw extracted text:")
        print("-" * 40)
        print(raw_text)
        print("-" * 40)
        print()
        
        # Process the image completely
        print("🧠 Step 2: Processing and parsing results...")
        results = ocr.process_image(image_path)
        
        if results['success']:
            print("✅ Processing successful!")
            print(f"📊 Found {results['total_found']} clan member results")
            print()
            
            # Show race info
            if 'race_info' in results:
                race_info = results['race_info']
                print("📅 Race Information:")
                print(f"  Date: {race_info.get('date', 'Not detected')}")
                print(f"  Race Count: {race_info.get('race_count', 'Not detected')}")
                print()
            
            # Show extracted results
            print("🏁 Extracted Results:")
            if results['results']:
                for i, result in enumerate(results['results'], 1):
                    position = f" (Position: {result['position']})" if result.get('position') else ""
                    print(f"  {i}. {result['name']}: {result['score']}{position}")
            else:
                print("  No clan member results found")
            
            print()
            print("🎯 Formatted confirmation text:")
            print("-" * 40)
            confirmation_text = ocr.format_results_for_confirmation(results['results'])
            print(confirmation_text)
            print("-" * 40)
            
        else:
            print("❌ Processing failed!")
            print(f"Error: {results['error']}")
            if 'raw_text' in results:
                print("\nRaw text that was extracted:")
                print(results['raw_text'])
        
    except Exception as e:
        print(f"❌ Error during OCR processing: {e}")

def main():
    print("🏁 Mario Kart OCR Test Tool")
    print("=" * 60)
    print(f"Current clan roster: {', '.join(config.CLAN_ROSTER)}")
    print()
    
    if len(sys.argv) != 2:
        print("Usage: python test_ocr.py <image_path>")
        print("Example: python test_ocr.py mario_kart_results.png")
        return
    
    image_path = sys.argv[1]
    test_ocr_on_image(image_path)

if __name__ == "__main__":
    main() 