#!/usr/bin/env python3
"""
Complete local test of /debugocr command flow
Processes a single image with full debug logging, exactly like the Discord command

Usage:
    python testing/test_full_debugocr.py <image_path>

Example:
    python testing/test_full_debugocr.py testing/ocr_edge_cases/image.png

Environment:
    DATABASE_URL - Required for database connection
    TEST_GUILD_ID - Optional, defaults to your actual guild ID
    USE_GPU_OCR - Optional, set to "true" to enable GPU (default: false, like Railway)
"""

import sys
import os
import logging
import traceback
from pathlib import Path
from PIL import Image

# Add mkw_stats_bot directory to Python path
project_root = Path(__file__).parent.parent
mkw_stats_bot_dir = project_root / "mkw_stats_bot"
sys.path.insert(0, str(mkw_stats_bot_dir))

from mkw_stats.database import DatabaseManager

# Configure detailed logging (matches bot format)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def main():
    """Run complete /debugocr flow locally"""

    # Parse arguments
    if len(sys.argv) < 2:
        print("❌ Usage: python testing/test_full_debugocr.py <image_path>")
        print("\nExample:")
        print("  python testing/test_full_debugocr.py testing/ocr_edge_cases/image.png")
        print("\nEnvironment Variables:")
        print("  DATABASE_URL    - PostgreSQL connection (required)")
        print("  TEST_GUILD_ID   - Guild ID to test (optional)")
        print("  USE_GPU_OCR     - Set to 'true' to enable GPU (default: false)")
        sys.exit(1)

    image_path = sys.argv[1]

    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)

    # Configuration
    guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
    use_gpu = os.getenv('USE_GPU_OCR', 'false').lower() == 'true'

    print("=" * 80)
    print("🔍 LOCAL DEBUG OCR TEST - Full /debugocr Flow")
    print("=" * 80)
    print(f"Image:    {image_path}")
    print(f"Guild ID: {guild_id}")
    print(f"Use GPU:  {use_gpu}")
    print(f"Database: {os.getenv('DATABASE_URL', 'NOT SET')[:50]}...")
    print("=" * 80)
    print()

    # Initialize database
    try:
        logging.info("📊 Initializing database connection...")
        db_manager = DatabaseManager()

        if guild_id == 0:
            logging.warning("⚠️  TEST_GUILD_ID not set, using guild_id=0")
            logging.warning("   This may result in no player data. Set with:")
            logging.warning("   export TEST_GUILD_ID=123456789")
            print()
    except Exception as e:
        logging.error(f"❌ Database connection failed: {e}")
        logging.error("   Make sure DATABASE_URL is set correctly")
        sys.exit(1)

    # Initialize OCR with optional GPU override
    logging.info(f"🚀 Initializing PaddleOCR (GPU: {use_gpu})...")

    # Import here so we can potentially modify settings
    from mkw_stats.ocr_processor import OCRProcessor, PaddleOCR
    import mkw_stats.ocr_processor as ocr_module

    # Temporarily override GPU setting if requested
    original_init = OCRProcessor._initialize_ocr

    if use_gpu:
        def _initialize_ocr_with_gpu(self):
            """Modified OCR initialization with GPU enabled"""
            try:
                logging.info("🚀 Initializing PaddleOCR with GPU-enabled settings...")

                self.ocr = PaddleOCR(
                    use_angle_cls=False,
                    lang='en',
                    use_gpu=True,  # <<<< GPU ENABLED FOR LOCAL TESTING
                    det_model_dir=None,
                    rec_model_dir=None,
                    cls_model_dir=None,
                    show_log=False,
                    use_space_char=True
                )

                logging.info("✅ PaddleOCR initialized with GPU!")

            except Exception as e:
                logging.error(f"❌ Failed to initialize PaddleOCR: {e}")
                raise

        OCRProcessor._initialize_ocr = _initialize_ocr_with_gpu

    # Create OCR processor
    try:
        ocr = OCRProcessor(db_manager=db_manager)
    except Exception as e:
        logging.error(f"❌ OCR initialization failed: {e}")
        sys.exit(1)
    finally:
        # Restore original method
        if use_gpu:
            OCRProcessor._initialize_ocr = original_init

    # ========================================================================
    # START: Exact /debugocr flow
    # ========================================================================

    logging.info(f"[DEBUG-OCR] {'=' * 80}")
    logging.info(f"[DEBUG-OCR] Processing Image: {Path(image_path).name}")
    logging.info(f"[DEBUG-OCR] {'=' * 80}")

    # Initialize temp file paths (for cleanup tracking)
    temp_path = image_path
    cropped_path = None
    visual_path = None

    try:
        # STEP 1: Get image dimensions
        with Image.open(temp_path) as img:
            img_width, img_height = img.size

        logging.info(f"[DEBUG-OCR] 📐 Image Dimensions: {img_width}x{img_height} pixels")

        # STEP 2: Crop and detect format
        cropped_path, visual_path, crop_coords = ocr.crop_image_to_target_region(temp_path)
        table_format = ocr.detect_table_format(img_width, img_height)
        logging.info(f"[DEBUG-OCR] 🎯 Detected Table Format: {table_format.value}")
        logging.info(f"[DEBUG-OCR] ✂️ Crop Coordinates: {crop_coords}")

        # STEP 3: Perform OCR
        ocr_result = ocr.perform_ocr_on_file(temp_path)

        if not ocr_result["success"]:
            logging.error(f"[DEBUG-OCR] ❌ OCR Failed: {ocr_result.get('error', 'Unknown error')}")
            raise Exception(f"OCR failed: {ocr_result.get('error')}")

        # STEP 4: Log raw OCR text
        raw_text = ocr_result.get("text", "")
        logging.info(f"[DEBUG-OCR] 📝 Raw OCR Text:\n{raw_text}")

        # STEP 5: Log OCR tokens
        tokens = raw_text.split()
        logging.info(f"[DEBUG-OCR] 🔢 Tokens ({len(tokens)} total): {tokens}")

        # STEP 6: Parse Mario Kart results with detailed logging
        # This is where all the pairing, team splitting, etc. happens
        extracted_texts = [{'text': raw_text, 'confidence': 0.9}]
        processed_results = ocr._parse_mario_kart_results(extracted_texts, guild_id)

        # STEP 7: Log player extraction results
        if processed_results:
            logging.info(f"[DEBUG-OCR] ✅ Players Extracted: {len(processed_results)}")
            for result in processed_results:
                raw_name_display = result.get('raw_name', result['name'])
                logging.info(
                    f"[DEBUG-OCR]   • {result['name']} "
                    f"(raw: '{raw_name_display}') - "
                    f"{result['score']} points - "
                    f"{result.get('races', 12)} races"
                )
        else:
            logging.warning("[DEBUG-OCR] ⚠️ No players extracted")

        # STEP 8: Log validation
        validation = ocr._validate_results(processed_results, guild_id) if processed_results else None
        if validation:
            logging.info("[DEBUG-OCR] 🔍 Validation Results:")
            logging.info(f"[DEBUG-OCR]   Valid: {validation.get('is_valid', False)}")
            if validation.get('errors'):
                for error in validation['errors']:
                    logging.info(f"[DEBUG-OCR]   Error: {error}")
            if validation.get('warnings'):
                for warning in validation['warnings']:
                    logging.info(f"[DEBUG-OCR]   Warning: {warning}")

    except Exception as e:
        logging.error(f"[DEBUG-OCR] ❌ Error processing image: {e}")
        logging.error(f"[DEBUG-OCR] {traceback.format_exc()}")
        processed_results = None

    finally:
        # Cleanup temp files (skip original image)
        try:
            if cropped_path and cropped_path != temp_path and os.path.exists(cropped_path):
                os.unlink(cropped_path)
                logging.debug(f"[DEBUG-OCR] Cleaned up: {cropped_path}")
            if visual_path and visual_path != temp_path and os.path.exists(visual_path):
                os.unlink(visual_path)
                logging.debug(f"[DEBUG-OCR] Cleaned up: {visual_path}")
        except OSError as e:
            logging.debug(f"[DEBUG-OCR] Failed to delete temporary file: {e}")

    # ========================================================================
    # END: /debugocr flow
    # ========================================================================

    logging.info(f"[DEBUG-OCR] {'=' * 80}")
    logging.info("[DEBUG-OCR] Debug OCR Processing Complete")
    logging.info(f"[DEBUG-OCR] {'=' * 80}")

    # Print summary
    print()
    print("=" * 80)
    print("📊 FINAL RESULTS")
    print("=" * 80)

    if processed_results:
        print(f"✅ SUCCESS - Found {len(processed_results)} guild players:\n")
        for i, result in enumerate(processed_results, 1):
            raw_name = result.get('raw_name', result['name'])
            name_display = f"{result['name']}" + (f" (OCR: '{raw_name}')" if raw_name != result['name'] else "")
            print(f"  {i}. {name_display}")
            print(f"     Score: {result['score']} | Races: {result.get('races', 12)}")
    else:
        print("❌ FAILED - No players detected")
        print("\nCheck the debug logs above for details on what went wrong.")

    print("=" * 80)

if __name__ == "__main__":
    main()
