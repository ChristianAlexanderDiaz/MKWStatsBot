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
            common_paths = ['/usr/bin/tesseract', '/usr/local/bin/tesseract', '/opt/homebrew/bin/tesseract']
            found_path = shutil.which('tesseract')
            
            if found_path:
                logging.info(f"✅ Tesseract found via PATH at: {found_path}")
                pytesseract.pytesseract.tesseract_cmd = found_path
            else:
                # Try common paths manually
                for path in common_paths:
                    if os.path.exists(path):
                        logging.info(f"✅ Tesseract found at: {path}")
                        pytesseract.pytesseract.tesseract_cmd = path
                        found_path = path
                        break
                
                if not found_path:
                    logging.error("❌ Tesseract not found anywhere in PATH or common locations")
                    logging.error("Please ensure tesseract-ocr is installed in your deployment environment")
        
        # Store database manager for name resolution
        self.db_manager = db_manager
        
        # Load preset regions first (this populates TABLE_PRESETS)
        self.presets_file = 'table_presets.json'
        self.load_presets()
        
        # Set table preset configuration
        self.table_preset = table_preset or config.DEFAULT_TABLE_PRESET
        if self.table_preset and self.table_preset in config.TABLE_PRESETS:
            self.preset_config = config.TABLE_PRESETS[self.table_preset]
        else:
            # Use default config if preset not found
            self.preset_config = {
                'score_pattern': r'\b\d{1,3}\b',
                'player_name_pattern': r'[A-Za-z0-9ΣΩ]+',
                'ocr_confidence_threshold': 0.6
            }
    
    def load_presets(self):
        """Load saved table format presets from formats/ folder."""
        try:
            # Load custom formats from data/formats/ folder
            formats_dir = 'data/formats'
            if os.path.exists(formats_dir):
                for filename in os.listdir(formats_dir):
                    if filename.endswith('.json') and filename != 'README.md':
                        filepath = os.path.join(formats_dir, filename)
                        try:
                            with open(filepath, 'r') as f:
                                format_data = json.load(f)
                                format_name = format_data.get('format_name', filename.replace('.json', ''))
                                
                                # Convert to TABLE_PRESETS format
                                preset = {
                                    'name': format_data.get('description', format_name),
                                    'description': format_data.get('description', f'Custom format: {format_name}'),
                                    'regions': format_data.get('regions', []),
                                    'created_date': format_data.get('created_date'),
                                    'image_path': format_data.get('image_path'),
                                    'team_columns': 2,
                                    'player_name_pattern': r'[A-Za-z0-9ΣΩ]+',
                                    'score_pattern': r'\b\d{1,3}\b',
                                    'table_structure': 'custom',
                                    'expected_players': 12,
                                    'ocr_confidence_threshold': 0.6,
                                }
                                
                                config.TABLE_PRESETS[format_name] = preset
                                
                                # Set first custom format as default
                                if not config.DEFAULT_TABLE_PRESET:
                                    config.DEFAULT_TABLE_PRESET = format_name
                                    
                        except Exception as e:
                            logging.error(f"Error loading format {filename}: {e}")
                            
                logging.info(f"Loaded {len(config.TABLE_PRESETS)} custom table presets from formats/")
                
            # Fallback to old presets file if no custom formats found
            if not config.TABLE_PRESETS and os.path.exists(self.presets_file):
                with open(self.presets_file, 'r') as f:
                    loaded_presets = json.load(f)
                    config.TABLE_PRESETS.update(loaded_presets)
                    logging.info(f"Loaded {len(loaded_presets)} table presets from {self.presets_file}")
                    
        except Exception as e:
            logging.error(f"Error loading presets: {e}")
    
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
    
    def process_image_with_preset(self, image_path: str, preset_name: str) -> Dict:
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
                return self.process_image(image_path)
            
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
                    roi_results = self.process_image(roi_path)
                    if roi_results['success']:
                        all_results.extend(roi_results['results'])
                finally:
                    # Clean up temp file
                    if os.path.exists(roi_path):
                        os.unlink(roi_path)
            
            # Validate results
            validation_result = self.validate_results(all_results)
            
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
    
    def validate_results(self, results: List[Dict]) -> Dict:
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
        
        # Check score ranges
        for result in results:
            score = result.get('score', 0)
            if score < 0 or score > 999:
                validation['warnings'].append(f"{result['name']}: Unusual score {score}")
        
        # Check for trial/guest players (not in roster)
        trials = []
        for result in results:
            # Use database name resolution if available, otherwise check directly
            if self.db_manager:
                resolved_name = self.db_manager.resolve_player_name(result['name'])
                if not resolved_name or resolved_name not in config.CLAN_ROSTER:
                    trials.append(result['name'])
            else:
                # Fallback: check if name is directly in roster
                if result['name'] not in config.CLAN_ROSTER:
                    trials.append(result['name'])
        
        if trials:
            validation['warnings'].append(f"Trial/Guest players detected: {', '.join(trials)}")
            validation['needs_confirmation'] = True
        
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
        
        # OCR config for game font
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ΣΩ"'
        
        for img in processed_images:
            try:
                text = pytesseract.image_to_string(img, config=custom_config)
                texts.append(text)
            except Exception as e:
                logging.error(f"OCR extraction error: {e}")
        
        return texts
    
    def find_clan_members_in_text(self, text: str) -> List[Dict]:
        """Find clan member names and scores using preset configuration."""
        results = []
        lines = text.split('\n')
        
        # Get patterns from preset config
        score_pattern = self.preset_config['score_pattern']
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for clan members and nicknames in the line
            found_in_line = False
            for roster_name in config.CLAN_ROSTER:
                if roster_name.lower() in line.lower():
                    # Use preset score pattern to find scores
                    score_matches = re.findall(score_pattern, line)
                    if score_matches:
                        # Take the first reasonable score (0-999)
                        for score_str in score_matches:
                            score = int(score_str)
                            if 0 <= score <= 999:
                                results.append({
                                    'name': roster_name,
                                    'score': score,
                                    'raw_line': line,
                                    'preset_used': self.table_preset,
                                    'confidence': 0.9  # High confidence for exact roster match
                                })
                                found_in_line = True
                                break
                if found_in_line:
                    break
            
            # If no roster name found, check for nicknames and unknown players
            if not found_in_line:
                # Extract potential player names (words before scores)
                words = line.split()
                for i, word in enumerate(words):
                    # Check if this could be a player name
                    # Filter out obvious artifacts but allow single meaningful letters (H, J, etc.)
                    is_valid_name = (
                        re.match(r'^[A-Za-z0-9ΣΩ]+$', word) and 
                        len(word) >= 1 and
                        not word.lower() in ['a', 'i', 'o', 'e', 'u', 'oo', 'aa', 'ii']  # Filter common OCR artifacts
                    )
                    
                    if is_valid_name:
                        # Look for the LAST valid score in the line (most likely to be the player's score)
                        all_scores_in_line = []
                        for j, check_word in enumerate(words):
                            if re.match(score_pattern, check_word):
                                score = int(check_word)
                                if 0 <= score <= 999:
                                    all_scores_in_line.append(score)
                        
                        # If we found scores, use the last one (most likely the player's total)
                        if all_scores_in_line:
                            score = all_scores_in_line[-1]  # Take the last score in the line
                            
                            # Resolve nickname to roster name using database
                            if self.db_manager:
                                resolved_name = self.db_manager.resolve_player_name(word)
                            else:
                                resolved_name = word  # Fallback to original name
                            
                            # Only add if it's a clan member or a recognized nickname
                            if resolved_name and resolved_name in config.CLAN_ROSTER:
                                confidence = 0.9
                                results.append({
                                    'name': resolved_name,
                                    'raw_name': word,  # Original detected name
                                    'score': score,
                                    'raw_line': line,
                                    'preset_used': self.table_preset,
                                    'confidence': confidence,
                                    'is_trial': False
                                })
                                found_in_line = True
                                break
                            # Skip non-roster players that aren't recognized nicknames
                    if found_in_line:
                        break
        
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
    
    def parse_mario_kart_results(self, texts: List[str]) -> Dict:
        """Parse extracted text to find Mario Kart race results."""
        try:
            all_results = []
            
            # Get results from all text variations
            for text in texts:
                results = self.find_clan_members_in_text(text)
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
    
    def process_image(self, image_path: str, message_timestamp=None) -> Dict:
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
            parsed_data = self.parse_mario_kart_results(texts)
            
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
            validation_result = self.validate_results(parsed_data['results'])
            
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