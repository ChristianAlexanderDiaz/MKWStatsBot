import cv2
import pytesseract
import numpy as np
import re
import logging
import json
import os
from PIL import Image
from typing import List, Dict, Tuple, Optional
from . import config

class OCRProcessor:
    def __init__(self, table_preset=None, db_manager=None):
        """Initialize OCR processor with table preset configuration."""
        # Set tesseract path from config or auto-detect
        import os
        import shutil
        
        if hasattr(config, 'TESSERACT_PATH') and config.TESSERACT_PATH:
            # Use configured path first
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
            logging.info(f"🔧 Tesseract path set to: {config.TESSERACT_PATH}")
            
            if os.path.exists(config.TESSERACT_PATH):
                logging.info(f"✅ Tesseract executable found at {config.TESSERACT_PATH}")
            else:
                logging.error(f"❌ Tesseract NOT found at {config.TESSERACT_PATH}")
                config.TESSERACT_PATH = None  # Fall back to auto-detection
        
        # Auto-detect tesseract if no valid path configured
        if not hasattr(config, 'TESSERACT_PATH') or not config.TESSERACT_PATH:
            logging.info("🔍 Auto-detecting Tesseract installation...")
            common_paths = ['/usr/bin/tesseract', '/usr/local/bin/tesseract', '/opt/homebrew/bin/tesseract', '/nix/store/*/bin/tesseract']
            found_path = shutil.which('tesseract')
            
            if found_path:
                logging.info(f"✅ Tesseract found via PATH at: {found_path}")
                pytesseract.pytesseract.tesseract_cmd = found_path
            else:
                # Try common paths manually
                for path in common_paths:
                    if '*' in path:
                        # Handle nix store paths with glob
                        import glob
                        nix_paths = glob.glob(path)
                        for nix_path in nix_paths:
                            if os.path.exists(nix_path):
                                logging.info(f"✅ Tesseract found at: {nix_path}")
                                pytesseract.pytesseract.tesseract_cmd = nix_path
                                found_path = nix_path
                                break
                        if found_path:
                            break
                    else:
                        if os.path.exists(path):
                            logging.info(f"✅ Tesseract found at: {path}")
                            pytesseract.pytesseract.tesseract_cmd = path
                            found_path = path
                            break
                
                if not found_path:
                    logging.error("❌ Tesseract not found anywhere in PATH or common locations")
                    logging.error("Please ensure tesseract-ocr is installed in your deployment environment")
                    # Try a final system check
                    try:
                        import subprocess
                        result = subprocess.run(['which', 'tesseract'], capture_output=True, text=True)
                        if result.returncode == 0 and result.stdout.strip():
                            found_path = result.stdout.strip()
                            logging.info(f"✅ Tesseract found via system which: {found_path}")
                            pytesseract.pytesseract.tesseract_cmd = found_path
                    except Exception as e:
                        logging.error(f"System check failed: {e}")
        
        # Store database manager for name resolution
        self.db_manager = db_manager
        
        # Custom region processing mode - no longer using legacy presets
        self.presets_file = 'table_presets.json'  # Keep for legacy compatibility
        
        # Use simple config for custom region processing
        self.preset_config = {
            'score_pattern': r'\b\d{1,3}\b',
            'player_name_pattern': r'[A-Za-z0-9ΣΩ]+',
            'ocr_confidence_threshold': 0.6
        }
    
    def load_custom_regions(self):
        """Load custom region selection from selected_regions.json."""
        try:
            regions_file = 'data/formats/selected_regions.json'
            if not os.path.exists(regions_file):
                raise FileNotFoundError(f"Custom regions file not found: {regions_file}")
            
            with open(regions_file, 'r') as f:
                regions_data = json.load(f)
            
            regions = regions_data.get('regions', [])
            if not regions:
                raise ValueError("No regions found in selected_regions.json")
            
            # Use the first (main) region
            main_region = regions[0]
            
            # Extract coordinates
            start_x, start_y = main_region['start']
            end_x, end_y = main_region['end']
            separator_x = main_region.get('separator_x')
            
            logging.info(f"✅ Loaded custom region: ({start_x}, {start_y}) to ({end_x}, {end_y})")
            logging.info(f"📏 Region size: {main_region['width']} x {main_region['height']}")
            if separator_x:
                logging.info(f"📏 Separator at X={separator_x}")
            
            return {
                'start': [start_x, start_y],
                'end': [end_x, end_y],
                'original_end': [end_x, end_y],  # Store original for overlay
                'width': main_region['width'],
                'height': main_region['height'],
                'separator_x': separator_x,
                'source': 'selected_regions.json'
            }
            
        except Exception as e:
            logging.error(f"❌ Error loading custom regions: {e}")
            raise
    
    def extend_region_to_bottom(self, region_data: dict, image_height: int) -> dict:
        """Extend the custom region to the bottom of the image."""
        try:
            # Create extended region
            extended_region = region_data.copy()
            start_x, start_y = region_data['start']
            end_x, _ = region_data['end']
            
            # Extend to image bottom
            extended_region['end'] = [end_x, image_height]
            extended_region['height'] = image_height - start_y
            
            logging.info(f"🔽 Extended region to bottom: ({start_x}, {start_y}) to ({end_x}, {image_height})")
            logging.info(f"📐 Extended height: {extended_region['height']} pixels")
            
            return extended_region
            
        except Exception as e:
            logging.error(f"❌ Error extending region: {e}")
            return region_data
    
    def save_preset(self, preset_name: str, regions: List[Dict], description: str = ""):
        """Save a new table format preset."""
        try:
            preset_data = {
                preset_name: {
                    "name": description or f"Table Format {preset_name}",
                    "regions": regions,
                    "description": description,
                    "expected_players": config.EXPECTED_PLAYERS_PER_TEAM
                }
            }
            
            # Update in-memory config
            config.TABLE_PRESETS.update(preset_data)
            
            # Save to file
            with open(self.presets_file, 'w') as f:
                json.dump(config.TABLE_PRESETS, f, indent=2)
            
            logging.info(f"Saved preset '{preset_name}' with {len(regions)} regions")
            return True
        except Exception as e:
            logging.error(f"Error saving preset: {e}")
            return False
    
    def process_image_with_preset(self, image_path: str, preset_name: str, guild_id: int = 0) -> Dict:
        """Process image using a saved preset for region targeting."""
        try:
            if preset_name not in config.TABLE_PRESETS:
                return {
                    'success': False,
                    'error': f'Preset "{preset_name}" not found',
                    'results': []
                }
            
            preset = config.TABLE_PRESETS[preset_name]
            regions = preset.get('regions', [])
            
            if not regions:
                # Fall back to full image processing if no regions saved
                return self.process_image(image_path, guild_id=guild_id)
            
            # Process each region separately
            all_results = []
            img = cv2.imread(image_path)
            
            for region in regions:
                # Handle different region coordinate formats
                if 'x' in region and 'y' in region:
                    # Old format: x, y, width, height
                    x, y, w, h = region['x'], region['y'], region['width'], region['height']
                elif 'start' in region and 'end' in region:
                    # New format: start [x, y], end [x, y]
                    start_x, start_y = region['start']
                    end_x, end_y = region['end']
                    x, y = start_x, start_y
                    w, h = end_x - start_x, end_y - start_y
                else:
                    logging.error(f"Invalid region format: {region}")
                    continue
                    
                roi = img[y:y+h, x:x+w]
                
                # Save ROI temporarily and process
                roi_path = f"temp_roi_{region.get('name', 'unknown')}.png"
                cv2.imwrite(roi_path, roi)
                
                try:
                    roi_results = self.process_image(roi_path, guild_id=guild_id)
                    if roi_results['success']:
                        all_results.extend(roi_results['results'])
                finally:
                    # Clean up temp file
                    if os.path.exists(roi_path):
                        os.unlink(roi_path)
            
            # Validate results
            validation_result = self.validate_results(all_results, guild_id)
            
            return {
                'success': len(all_results) > 0,
                'results': all_results,
                'total_found': len(all_results),
                'validation': validation_result,
                'preset_used': preset_name
            }
            
        except Exception as e:
            logging.error(f"Error processing with preset: {e}")
            return {
                'success': False,
                'error': f'Preset processing failed: {str(e)}',
                'results': []
            }
    
    def validate_results(self, results: List[Dict], guild_id: int = 0) -> Dict:
        """Validate extracted results with flexible player count."""
        validation = {
            'is_valid': True,
            'warnings': [],
            'errors': [],
            'player_count': len(results),
            'is_ideal_count': False,
            'needs_confirmation': False
        }
        
        player_count = len(results)
        ideal_count = config.TOTAL_IDEAL_PLAYERS  # Use total ideal players (12 for 6v6)
        
        # Check player count
        if player_count == 0:
            validation['errors'].append("No players found in image")
            validation['is_valid'] = False
        elif player_count < config.MIN_TOTAL_PLAYERS:
            validation['errors'].append(f"Too few players: {player_count} (minimum {config.MIN_TOTAL_PLAYERS})")
            validation['is_valid'] = False
        elif player_count == ideal_count:
            validation['is_ideal_count'] = True
            # Perfect count, no warnings needed
        elif player_count < ideal_count:
            validation['warnings'].append(f"Found {player_count} players (ideal: {ideal_count})")
            validation['needs_confirmation'] = True
            # Still valid but needs user confirmation
        elif player_count > config.MAX_TOTAL_PLAYERS:
            validation['errors'].append(f"Too many players: {player_count} (maximum {config.MAX_TOTAL_PLAYERS})")
            validation['is_valid'] = False
        else:
            validation['warnings'].append(f"Found {player_count} players (ideal: {ideal_count})")
            validation['needs_confirmation'] = True
        
        # Check for duplicate players
        player_names = [r['name'] for r in results]
        duplicates = set([name for name in player_names if player_names.count(name) > 1])
        if duplicates:
            validation['errors'].append(f"Duplicate players found: {', '.join(duplicates)}")
            validation['is_valid'] = False
        
        # Check score ranges (Mario Kart: 12-180 for 12 races)
        for result in results:
            score = result.get('score', 0)
            if not (12 <= score <= 180):
                validation['warnings'].append(f"{result['name']}: Invalid score {score} (valid range: 12-180)")
        
        # Check for roster vs non-roster players (informational only)
        roster_members = []
        non_roster = []
        
        for result in results:
            if result.get('is_roster_member', False):
                roster_members.append(result['name'])
            else:
                non_roster.append(result.get('raw_name', result['name']))
        
        if non_roster:
            validation['warnings'].append(f"Non-roster players detected: {', '.join(non_roster)}")
        
        if roster_members:
            validation['warnings'].append(f"Roster members found: {', '.join(roster_members)}")
        
        return validation
    
    def preprocess_image(self, image_path: str) -> List[np.ndarray]:
        """Preprocess image with multiple processing methods for better OCR."""
        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError("Could not load image")
            
            processed_images = []
            
            # Original image
            processed_images.append(img)
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            processed_images.append(gray)
            
            # Increase contrast
            contrast = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
            processed_images.append(contrast)
            
            # Threshold versions
            _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(thresh1)
            
            # Adaptive threshold
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            processed_images.append(adaptive)
            
            # Add more processing methods as needed
            return processed_images
            
        except Exception as e:
            logging.error(f"Image preprocessing error: {e}")
            return [cv2.imread(image_path)]
    
    def extract_text_from_image(self, image_path: str) -> List[str]:
        """Extract text using multiple preprocessing methods."""
        processed_images = self.preprocess_image(image_path)
        texts = []
        
        # OCR config for game font - include parentheses for race counts like "Cynical(5)"
        configs = [
            r'--oem 3 --psm 6 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789() "',
            r'--oem 3 --psm 7 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789() "',
            r'--oem 3 --psm 8 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789() "'
        ]
        
        for img in processed_images:
            for config in configs:
                try:
                    text = pytesseract.image_to_string(img, config=config)
                    texts.append(text)
                except Exception as e:
                    logging.error(f"OCR extraction error: {e}")
        
        return texts
    
    def find_clan_members_in_text(self, text: str, guild_id: int = 0) -> List[Dict]:
        """Find ALL player names and scores in text (no database filtering)."""
        results = []
        lines = text.split('\n')
        
        # Get patterns from preset config
        score_pattern = self.preset_config['score_pattern']
        
        # Get current roster from database for nickname resolution (but don't filter)
        roster_players = self.db_manager.get_roster_players(guild_id) if self.db_manager else []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Extract potential player names and scores from each line
            words = line.split()
            for i, word in enumerate(words):
                # Check if this could be a player name
                # Allow letters, numbers, and parentheses for race counts like "Cynical(5)"
                is_valid_name = (
                    re.match(r'^[A-Za-z0-9()]+$', word) and 
                    len(word) >= 2  # Excludes single characters like "C", "I", "1"
                )
                
                if is_valid_name:
                    # Look for valid scores in the line
                    all_scores_in_line = []
                    for j, check_word in enumerate(words):
                        if re.match(score_pattern, check_word):
                            score = int(check_word)
                            if 12 <= score <= 180:
                                all_scores_in_line.append(score)
                    
                    # If we found scores, use the last one (most likely the player's total)
                    if all_scores_in_line:
                        score = all_scores_in_line[-1]  # Take the last score in the line
                        
                        # Score validation 
                        if 12 <= score <= 180:
                            # Try to resolve nickname to roster name using database
                            resolved_name = word  # Default to detected name
                            is_roster_member = False
                            
                            if self.db_manager:
                                try:
                                    db_resolved = self.db_manager.resolve_player_name(word, guild_id)
                                    if db_resolved and db_resolved in roster_players:
                                        resolved_name = db_resolved
                                        is_roster_member = True
                                except Exception as e:
                                    # If resolution fails, just use the original name
                                    logging.debug(f"Name resolution failed for '{word}': {e}")
                                    pass
                            
                            # Add ALL detected players (no filtering)
                            results.append({
                                'name': resolved_name,
                                'raw_name': word,  # Original detected name
                                'score': score,
                                'raw_line': line,
                                'preset_used': 'custom_region',
                                'confidence': 0.9 if is_roster_member else 0.7,
                                'is_roster_member': is_roster_member
                            })
                            break  # Only take first valid name per line
        
        return results
    
    def create_default_war_metadata(self, message_timestamp=None, **overrides) -> Dict:
        """Create default war metadata - OCR only extracts names/scores."""
        metadata = {
            'date': None,
            'time': None, 
            'race_count': config.DEFAULT_RACE_COUNT,
            'war_type': '6v6',
            'notes': 'Auto-processed'
        }
        
        # Use message timestamp as primary source for date/time
        if message_timestamp:
            metadata['date'] = message_timestamp.strftime('%Y-%m-%d')
            metadata['time'] = message_timestamp.strftime('%H:%M:%S')
        
        # Apply any user overrides
        metadata.update(overrides)
        
        return metadata
    
    def parse_mario_kart_results(self, texts: List[str], guild_id: int = 0) -> Dict:
        """Parse extracted text to find Mario Kart race results."""
        try:
            all_results = []
            
            # Get results from all text variations
            for text in texts:
                results = self.find_clan_members_in_text(text, guild_id)
                all_results.extend(results)
            
            # Prioritize clan roster members
            final_results = {}
            for result in all_results:
                name = result['name']
                if name not in final_results:
                    final_results[name] = result
                else:
                    # Prioritize clan roster members over non-roster names
                    existing_is_clan = final_results[name]['name'] in config.CLAN_ROSTER
                    current_is_clan = result['name'] in config.CLAN_ROSTER
                    
                    if current_is_clan and not existing_is_clan:
                        # Replace non-clan member with clan member
                        final_results[name] = result
                    elif existing_is_clan and not current_is_clan:
                        # Keep existing clan member over non-clan member
                        pass
                    else:
                        # Both are clan members or both are non-clan, use confidence/length
                        if len(result['raw_line']) > len(final_results[name]['raw_line']):
                            final_results[name] = result
            
            return {
                'results': list(final_results.values()),
                'total_extracted': len(final_results)
            }
            
        except Exception as e:
            logging.error(f"Parsing error: {e}")
            return {'results': [], 'total_extracted': 0}
    
    def process_image(self, image_path: str, message_timestamp=None, guild_id: int = 0) -> Dict:
        """Complete image processing pipeline with war metadata extraction."""
        try:
            logging.info(f"Processing image: {image_path}")
            
            # Extract text using multiple preprocessing methods
            texts = self.extract_text_from_image(image_path)
            
            if not any(text.strip() for text in texts):
                return {
                    'success': False,
                    'error': 'No text could be extracted from the image',
                    'results': []
                }
            
            # Parse the extracted text
            parsed_data = self.parse_mario_kart_results(texts, guild_id)
            
            if parsed_data['total_extracted'] == 0:
                return {
                    'success': False,
                    'error': 'No clan member results found in the image',
                    'raw_text': '\n'.join(texts)[:500],  # First 500 chars for debugging
                    'results': []
                }
            
            # Create default war metadata (user provides date/time/race count)
            war_metadata = self.create_default_war_metadata(message_timestamp)
            
            # Add metadata to each result
            for result in parsed_data['results']:
                result.update(war_metadata)
            
            # Validate results
            validation_result = self.validate_results(parsed_data['results'], guild_id)
            
            return {
                'success': True,
                'results': parsed_data['results'],
                'total_found': parsed_data['total_extracted'],
                'war_metadata': war_metadata,
                'validation': validation_result,
                'raw_text': '\n'.join(texts)[:500]  # For debugging
            }
            
        except Exception as e:
            logging.error(f"Image processing error: {e}")
            return {
                'success': False,
                'error': f'Processing failed: {str(e)}',
                'results': []
            }
    
    def detect_all_text_with_boxes(self, image_path: str) -> Dict:
        """Detect all text in image with bounding boxes and classifications."""
        try:
            # Load image
            img = cv2.imread(image_path)
            if img is None:
                logging.error(f"Could not load image for text detection: {image_path}")
                return {'success': False, 'error': 'Could not load image'}
            
            # Use pytesseract to get detailed text data
            logging.info("🔍 Detecting all text with bounding boxes...")
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=r'--oem 3 --psm 6')
            
            # Process detected text elements
            text_elements = []
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                conf = int(data['conf'][i]) if data['conf'][i] != '-1' else 0
                
                # Filter out empty text and low confidence
                if text and conf > 20:  # Confidence threshold
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    
                    # Classify text type
                    text_type = self.classify_text_type(text)
                    
                    text_elements.append({
                        'text': text,
                        'confidence': conf,
                        'bbox': (x, y, w, h),
                        'type': text_type,
                        'level': data['level'][i]
                    })
            
            logging.info(f"📊 Detected {len(text_elements)} text elements")
            return {
                'success': True,
                'text_elements': text_elements,
                'raw_data': data
            }
            
        except Exception as e:
            logging.error(f"Error detecting text with boxes: {e}")
            return {'success': False, 'error': str(e)}
    
    def classify_text_type(self, text: str) -> str:
        """Classify text as letters or numbers only."""
        if not text:
            return 'letter'  # Default fallback
            
        # Count character types
        letters = sum(1 for c in text if c.isalpha())
        numbers = sum(1 for c in text if c.isdigit())
        
        # Simple classification: numbers or letters only
        if numbers > 0 and letters == 0:
            return 'number'  # Pure numbers (scores)
        else:
            return 'letter'  # Everything else treated as letters (names)
    
    def create_debug_overlay(self, image_path: str) -> str:
        """Create color-coded overlay showing all detected text with bounding boxes."""
        try:
            # Detect all text elements
            detection_result = self.detect_all_text_with_boxes(image_path)
            if not detection_result['success']:
                return None
            
            # Load original image
            img = cv2.imread(image_path)
            if img is None:
                return None
                
            text_elements = detection_result['text_elements']
            logging.info(f"🎨 Creating debug overlay with {len(text_elements)} text elements")
            
            # Color scheme: Red=letters, Green=numbers only
            colors = {
                'letter': (0, 0, 255),      # Red (BGR format)
                'number': (0, 255, 0)       # Green
            }
            
            # Draw bounding boxes and labels
            for element in text_elements:
                text = element['text']
                conf = element['confidence']
                x, y, w, h = element['bbox']
                text_type = element['type']
                
                # Get color for this text type
                color = colors.get(text_type, colors['letter'])  # Default to letter (red) if unknown
                
                # Draw rectangle
                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                
                # Add text label with confidence
                label = f"{text} ({conf}%)"
                label_pos = (x, y - 5 if y > 20 else y + h + 15)
                cv2.putText(img, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 
                           0.4, color, 1, cv2.LINE_AA)
            
            # Add legend
            legend_y = 30
            for text_type, color in colors.items():
                legend_text = f"{text_type.title()}"
                cv2.putText(img, legend_text, (10, legend_y), cv2.FONT_HERSHEY_SIMPLEX,
                           0.6, color, 2, cv2.LINE_AA)
                legend_y += 25
            
            # Save overlay image
            import time
            timestamp = int(time.time())
            overlay_path = f"temp_debug_overlay_{timestamp}.png"
            
            success = cv2.imwrite(overlay_path, img)
            if success:
                logging.info(f"Created debug overlay: {overlay_path}")
                return overlay_path
            else:
                logging.error("Failed to save debug overlay image")
                return None
                
        except Exception as e:
            logging.error(f"Error creating debug overlay: {e}")
            return None
    
    def create_visual_overlay(self, image_path: str) -> str:
        """Create a visual overlay showing the processed region with red box."""
        try:
            # Use the ice_mario preset region coordinates
            region_coords = {
                "start": [576, 101],
                "end": [1064, 1015]
            }
            
            # Load the original image
            img = cv2.imread(image_path)
            if img is None:
                logging.error(f"Could not load image for overlay: {image_path}")
                return None
            
            # Extract coordinates
            start_x, start_y = region_coords["start"]
            end_x, end_y = region_coords["end"]
            
            # Draw red rectangle around the processed region
            cv2.rectangle(img, (start_x, start_y), (end_x, end_y), (0, 0, 255), 4)
            
            # Add label
            label_pos = (start_x, start_y - 10 if start_y > 20 else end_y + 25)
            cv2.putText(img, "OCR Region", label_pos, cv2.FONT_HERSHEY_SIMPLEX, 
                       0.8, (0, 0, 255), 2, cv2.LINE_AA)
            
            # Save overlay image with timestamp to avoid conflicts
            import time
            timestamp = int(time.time())
            overlay_path = f"temp_overlay_{timestamp}.png"
            
            success = cv2.imwrite(overlay_path, img)
            if success:
                logging.info(f"Created visual overlay: {overlay_path}")
                return overlay_path
            else:
                logging.error("Failed to save overlay image")
                return None
                
        except Exception as e:
            logging.error(f"Error creating visual overlay: {e}")
            return None
    
    def create_custom_region_debug_overlay(self, image_path: str, region_data: dict, roi_path: str) -> str:
        """Create debug overlay showing custom region boundaries and detected text."""
        try:
            # Load original image
            img = cv2.imread(image_path)
            if img is None:
                return None
            
            # Get region coordinates
            start_x, start_y = region_data['start']
            end_x, end_y = region_data['end']
            original_end_x, original_end_y = region_data['original_end']
            
            # Draw original selected region in yellow
            cv2.rectangle(img, (start_x, start_y), (original_end_x, original_end_y), (0, 255, 255), 3)
            cv2.putText(img, "Selected Region", (start_x, start_y - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Draw extended region in orange (if different)
            if end_y != original_end_y:
                cv2.rectangle(img, (start_x, original_end_y), (end_x, end_y), (0, 165, 255), 2)
                cv2.putText(img, "Extended to Bottom", (start_x, original_end_y + 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            
            # Get text detection results from the ROI
            detection_result = self.detect_all_text_with_boxes(roi_path)
            if detection_result['success']:
                text_elements = detection_result['text_elements']
                
                # Color scheme for text types - letters and numbers only
                colors = {
                    'letter': (0, 0, 255),      # Red
                    'number': (0, 255, 0)       # Green
                }
                
                # Draw detected text boxes (offset to original image coordinates)
                for element in text_elements:
                    # Adjust coordinates back to original image
                    roi_x, roi_y, roi_w, roi_h = element['bbox']
                    orig_x = start_x + roi_x
                    orig_y = start_y + roi_y
                    
                    text_type = element['type']
                    color = colors.get(text_type, colors['letter'])  # Default to red if unknown
                    
                    # Draw rectangle on original image
                    cv2.rectangle(img, (orig_x, orig_y), (orig_x + roi_w, orig_y + roi_h), color, 2)
                    
                    # Add text label
                    label = f"{element['text']} ({element['confidence']}%)"
                    label_pos = (orig_x, orig_y - 5 if orig_y > 20 else orig_y + roi_h + 15)
                    cv2.putText(img, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 
                               0.4, color, 1, cv2.LINE_AA)
            
            # Add legend
            legend_y = 30
            legend_items = [
                ("Selected Region", (0, 255, 255)),
                ("Extended Region", (0, 165, 255)),
                ("Letters", (0, 0, 255)),
                ("Numbers", (0, 255, 0))
            ]
            
            for i, (text, color) in enumerate(legend_items):
                cv2.putText(img, text, (10, legend_y + i * 25), cv2.FONT_HERSHEY_SIMPLEX,
                           0.6, color, 2, cv2.LINE_AA)
            
            # Save overlay image
            import time
            timestamp = int(time.time())
            overlay_path = f"temp_custom_debug_overlay_{timestamp}.png"
            
            success = cv2.imwrite(overlay_path, img)
            if success:
                logging.info(f"Created custom region debug overlay: {overlay_path}")
                return overlay_path
            else:
                logging.error("Failed to save custom region debug overlay")
                return None
                
        except Exception as e:
            logging.error(f"Error creating custom region debug overlay: {e}")
            return None
    
    def process_custom_region_debug(self, image_path: str, guild_id: int = 0) -> Dict:
        """Process custom region for debugging with color-coded text detection overlay."""
        try:
            logging.info(f"🔍 Processing custom region for debugging: {image_path}")
            
            # Load custom region coordinates
            region_data = self.load_custom_regions()
            
            # Load image to get dimensions
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not load image: {image_path}")
            
            image_height = img.shape[0]
            
            # Extend region to bottom of image
            extended_region = self.extend_region_to_bottom(region_data, image_height)
            
            # Extract region from image
            start_x, start_y = extended_region['start']
            end_x, end_y = extended_region['end']
            
            # Crop the region
            roi = img[start_y:end_y, start_x:end_x]
            
            # Save ROI temporarily for processing
            import time
            timestamp = int(time.time())
            roi_path = f"temp_custom_roi_{timestamp}.png"
            cv2.imwrite(roi_path, roi)
            
            try:
                # Extract text from region only
                texts = self.extract_text_from_image(roi_path)
                
                # Get detailed text detection with bounding boxes from region
                detection_result = self.detect_all_text_with_boxes(roi_path)
                
                if not texts or not any(text.strip() for text in texts):
                    return {
                        'success': False,
                        'error': 'No text could be extracted from the custom region',
                        'results': [],
                        'debug_info': {
                            'raw_text': '',
                            'detected_elements': [],
                            'region_used': extended_region
                        }
                    }
                
                # Parse results from extracted text
                parsed_data = self.parse_mario_kart_results(texts, guild_id)
                
                # Create debug overlay showing region boundaries and detected text
                debug_overlay_path = self.create_custom_region_debug_overlay(image_path, extended_region, roi_path)
                
                # Prepare debug information
                debug_info = {
                    'raw_text': '\n'.join(texts)[:2000],  # Limit to 2000 chars
                    'detected_elements': detection_result.get('text_elements', [])[:50],  # Limit to 50 elements
                    'total_elements': len(detection_result.get('text_elements', [])) if detection_result['success'] else 0,
                    'processing_mode': 'custom_region_debug',
                    'region_used': extended_region,
                    'region_source': region_data['source']
                }
                
                # Validate results
                validation_result = self.validate_results(parsed_data['results'], guild_id)
                
                result = {
                    'success': parsed_data['total_extracted'] > 0,
                    'results': parsed_data['results'],
                    'total_found': parsed_data['total_extracted'],
                    'validation': validation_result,
                    'debug_info': debug_info
                }
                
                if debug_overlay_path:
                    result['debug_overlay'] = debug_overlay_path
                
                if parsed_data['total_extracted'] == 0:
                    result['error'] = 'No valid player results found in the custom region'
                
                return result
                
            finally:
                # Clean up ROI temp file
                if os.path.exists(roi_path):
                    os.unlink(roi_path)
            
        except Exception as e:
            logging.error(f"Error processing custom region for debug: {e}")
            return {
                'success': False,
                'error': f'Custom region debug processing failed: {str(e)}',
                'results': [],
                'debug_info': {'raw_text': '', 'detected_elements': [], 'total_elements': 0}
            }
    
    def process_split_regions_debug(self, image_path: str, guild_id: int = 0) -> Dict:
        """Process custom region split into name and score regions with different OCR configs."""
        try:
            logging.info(f"🔍 Processing split regions for debugging: {image_path}")
            
            # Load custom region coordinates with separator
            region_data = self.load_custom_regions()
            separator_x = region_data.get('separator_x')
            
            if not separator_x:
                # Fall back to original method if no separator
                logging.warning("⚠️ No separator found, falling back to single region processing")
                return self.process_custom_region_debug(image_path, guild_id)
            
            # Load image to get dimensions
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not load image: {image_path}")
            
            image_height = img.shape[0]
            
            # Extend region to bottom of image
            extended_region = self.extend_region_to_bottom(region_data, image_height)
            
            # Split into name and score regions
            start_x, start_y = extended_region['start']
            end_x, end_y = extended_region['end']
            
            # Name region (left): start_x to separator_x
            name_region = img[start_y:end_y, start_x:separator_x]
            # Score region (right): separator_x to end_x  
            score_region = img[start_y:end_y, separator_x:end_x]
            
            # Save regions temporarily for processing
            import time
            timestamp = int(time.time())
            name_roi_path = f"temp_name_roi_{timestamp}.png"
            score_roi_path = f"temp_score_roi_{timestamp}.png"
            cv2.imwrite(name_roi_path, name_region)
            cv2.imwrite(score_roi_path, score_region)
            
            try:
                # Process name region with mixed character set
                name_texts = self.extract_text_from_region_with_config(name_roi_path, "names")
                # Process score region with numbers only
                score_texts = self.extract_text_from_region_with_config(score_roi_path, "scores")
                
                # Get detailed text detection from both regions
                name_detection = self.detect_all_text_with_boxes(name_roi_path)
                score_detection = self.detect_all_text_with_boxes(score_roi_path)
                
                # Match names with scores spatially and parse results
                results = self.match_names_with_scores(name_texts, score_texts, name_detection, score_detection, guild_id)
                
                # Create debug overlay showing both regions and separator
                debug_overlay_path = self.create_split_region_debug_overlay(
                    image_path, extended_region, separator_x, name_roi_path, score_roi_path
                )
                
                # Prepare debug information
                debug_info = {
                    'raw_name_text': '\n'.join(name_texts)[:1000],
                    'raw_score_text': '\n'.join(score_texts)[:1000],
                    'name_elements': name_detection.get('text_elements', [])[:25],
                    'score_elements': score_detection.get('text_elements', [])[:25],
                    'processing_mode': 'split_region_debug',
                    'region_used': extended_region,
                    'separator_x': separator_x
                }
                
                # Validate results
                validation_result = self.validate_results(results, guild_id)
                
                result = {
                    'success': len(results) > 0,
                    'results': results,
                    'total_found': len(results),
                    'validation': validation_result,
                    'debug_info': debug_info
                }
                
                if debug_overlay_path:
                    result['debug_overlay'] = debug_overlay_path
                
                if len(results) == 0:
                    result['error'] = 'No valid player results found in the split regions'
                
                return result
                
            finally:
                # Clean up temp files
                for temp_file in [name_roi_path, score_roi_path]:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
            
        except Exception as e:
            logging.error(f"Error processing split regions for debug: {e}")
            return {
                'success': False,
                'error': f'Split region debug processing failed: {str(e)}',
                'results': [],
                'debug_info': {'raw_name_text': '', 'raw_score_text': '', 'name_elements': [], 'score_elements': []}
            }
    
    def extract_text_from_region_with_config(self, image_path: str, region_type: str) -> List[str]:
        """Extract text using specialized OCR config for names or scores."""
        # Use only single preprocessing to eliminate duplication
        img = cv2.imread(image_path)
        if img is None:
            return []
        
        # Convert to grayscale for better OCR performance
        processed_images = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)]
        texts = []
        
        # Single config per region type to eliminate duplication
        if region_type == "names":
            # Mixed character set for names like "Cynical(5)" - single PSM 6 config
            configs = [
                r'--oem 3 --psm 6 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789() "'
            ]
        else:  # scores
            # Numbers only for pure score detection - single PSM 6 config
            configs = [
                r'--oem 3 --psm 6 -c tessedit_char_whitelist="0123456789"'
            ]
        
        for img in processed_images:
            for config in configs:
                try:
                    text = pytesseract.image_to_string(img, config=config)
                    texts.append(text)
                except Exception as e:
                    logging.error(f"OCR extraction error for {region_type}: {e}")
        
        return texts
    
    def match_names_with_scores(self, name_texts: List[str], score_texts: List[str], 
                               name_detection: Dict, score_detection: Dict, guild_id: int = 0) -> List[Dict]:
        """Match detected names with scores using spatial positioning."""
        try:
            # Extract name candidates from name region
            name_candidates = []
            for text in name_texts:
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    words = line.split()
                    for word in words:
                        # Apply name validation (2+ chars, alphanumeric + parentheses)
                        if (re.match(r'^[A-Za-z0-9()]+$', word) and len(word) >= 2):
                            name_candidates.append(word)
            
            # Extract score candidates from score region
            score_candidates = []
            for text in score_texts:
                lines = text.split('\n')
                for line in lines:
                    words = line.split()
                    for word in words:
                        if re.match(r'^\d+$', word):  # Pure numbers only
                            score = int(word)
                            if 12 <= score <= 180:  # Valid score range
                                score_candidates.append(score)
            
            # For now, simple pairing: match by index (assuming they're in same order)
            # TODO: Could enhance with spatial Y-coordinate matching later
            results = []
            max_pairs = min(len(name_candidates), len(score_candidates))
            
            for i in range(max_pairs):
                name = name_candidates[i]
                score = score_candidates[i]
                
                # Try to resolve nickname to roster name using database
                resolved_name = name
                is_roster_member = False
                
                if self.db_manager:
                    try:
                        db_resolved = self.db_manager.resolve_player_name(name, guild_id)
                        roster_players = self.db_manager.get_roster_players(guild_id)
                        if db_resolved and db_resolved in roster_players:
                            resolved_name = db_resolved
                            is_roster_member = True
                    except Exception as e:
                        logging.debug(f"Name resolution failed for '{name}': {e}")
                
                results.append({
                    'name': resolved_name,
                    'raw_name': name,
                    'score': score,
                    'raw_line': f"{name} {score}",  # Reconstructed line
                    'preset_used': 'split_region',
                    'confidence': 0.9 if is_roster_member else 0.7,
                    'is_roster_member': is_roster_member
                })
            
            return results
            
        except Exception as e:
            logging.error(f"Error matching names with scores: {e}")
            return []
    
    def create_split_region_debug_overlay(self, image_path: str, extended_region: dict, 
                                        separator_x: int, name_roi_path: str, score_roi_path: str) -> str:
        """Create debug overlay showing split regions and detected text."""
        try:
            # Load original image
            img = cv2.imread(image_path)
            if img is None:
                return None
            
            # Get region coordinates
            start_x, start_y = extended_region['start']
            end_x, end_y = extended_region['end']
            original_end_x, original_end_y = extended_region['original_end']
            
            # Draw original selected region in yellow
            cv2.rectangle(img, (start_x, start_y), (original_end_x, original_end_y), (0, 255, 255), 3)
            cv2.putText(img, "Selected Region", (start_x, start_y - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Draw extended region in orange (if different)
            if end_y != original_end_y:
                cv2.rectangle(img, (start_x, original_end_y), (end_x, end_y), (0, 165, 255), 2)
                cv2.putText(img, "Extended to Bottom", (start_x, original_end_y + 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            
            # Draw separator line in red
            cv2.line(img, (separator_x, start_y), (separator_x, end_y), (0, 0, 255), 3)
            cv2.putText(img, "Names | Scores", (start_x, end_y + 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Draw name region outline in blue
            cv2.rectangle(img, (start_x, start_y), (separator_x, end_y), (255, 0, 0), 2)
            cv2.putText(img, "Names", (start_x + 10, start_y + 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            
            # Draw score region outline in green
            cv2.rectangle(img, (separator_x, start_y), (end_x, end_y), (0, 255, 0), 2)
            cv2.putText(img, "Scores", (separator_x + 10, start_y + 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Get text detection results from both regions and draw individual elements
            name_detection = self.detect_all_text_with_boxes(name_roi_path)
            score_detection = self.detect_all_text_with_boxes(score_roi_path)
            
            # Draw individual text elements from name region
            if name_detection['success']:
                for element in name_detection['text_elements']:
                    # Adjust coordinates back to original image (name region)
                    roi_x, roi_y, roi_w, roi_h = element['bbox']
                    orig_x = start_x + roi_x
                    orig_y = start_y + roi_y
                    
                    # Draw red box around names
                    cv2.rectangle(img, (orig_x, orig_y), (orig_x + roi_w, orig_y + roi_h), (0, 0, 255), 1)
                    
                    # Add text label with confidence
                    label = f"{element['text']} ({element['confidence']}%)"
                    label_pos = (orig_x, orig_y - 3 if orig_y > 15 else orig_y + roi_h + 12)
                    cv2.putText(img, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 
                               0.3, (0, 0, 255), 1, cv2.LINE_AA)
            
            # Draw individual text elements from score region  
            if score_detection['success']:
                for element in score_detection['text_elements']:
                    # Adjust coordinates back to original image (score region)
                    roi_x, roi_y, roi_w, roi_h = element['bbox']
                    orig_x = separator_x + roi_x
                    orig_y = start_y + roi_y
                    
                    # Draw green box around scores
                    cv2.rectangle(img, (orig_x, orig_y), (orig_x + roi_w, orig_y + roi_h), (0, 255, 0), 1)
                    
                    # Add text label with confidence
                    label = f"{element['text']} ({element['confidence']}%)"
                    label_pos = (orig_x, orig_y - 3 if orig_y > 15 else orig_y + roi_h + 12)
                    cv2.putText(img, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 
                               0.3, (0, 255, 0), 1, cv2.LINE_AA)
            
            # Add legend
            legend_y = 30
            legend_items = [
                ("Selected Region", (0, 255, 255)),
                ("Extended Region", (0, 165, 255)),
                ("Names Region", (255, 0, 0)),
                ("Scores Region", (0, 255, 0)),
                ("Name Text", (0, 0, 255)),
                ("Score Text", (0, 255, 0))
            ]
            
            for i, (text, color) in enumerate(legend_items):
                cv2.putText(img, text, (10, legend_y + i * 20), cv2.FONT_HERSHEY_SIMPLEX,
                           0.5, color, 2, cv2.LINE_AA)
            
            # Save overlay image
            import time
            timestamp = int(time.time())
            overlay_path = f"temp_split_debug_overlay_{timestamp}.png"
            
            success = cv2.imwrite(overlay_path, img)
            if success:
                logging.info(f"Created split region debug overlay: {overlay_path}")
                return overlay_path
            else:
                logging.error("Failed to save split region debug overlay")
                return None
                
        except Exception as e:
            logging.error(f"Error creating split region debug overlay: {e}")
            return None
    
    def process_image_with_overlay(self, image_path: str, guild_id: int = 0) -> Dict:
        """Process image using the ice_mario preset and create visual overlay."""
        try:
            # Process using the ice_mario preset
            result = self.process_image_with_preset(image_path, "ice_mario", guild_id)
            
            # Create visual overlay showing processed region
            overlay_path = self.create_visual_overlay(image_path)
            if overlay_path:
                result['overlay_image'] = overlay_path
            
            return result
            
        except Exception as e:
            logging.error(f"Error processing with overlay: {e}")
            return {
                'success': False,
                'error': f'Processing failed: {str(e)}',
                'results': []
            }

    def format_results_for_confirmation(self, results: List[Dict]) -> str:
        """Format extracted results for user confirmation."""
        if not results:
            return "No results found."
        
        formatted = "📊 **Extracted Race Results:**\n\n"
        
        # Results table
        formatted += "**Player Scores:**\n"
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result['name']}**: {result['score']}\n"
            if 'raw_line' in result:
                formatted += f"   (Raw: {result['raw_line']})\n"
        
        formatted += f"\n**Total Players Found:** {len(results)}"
        return formatted 