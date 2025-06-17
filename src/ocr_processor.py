import cv2
import pytesseract
import numpy as np
import re
import logging
import json
import os
from PIL import Image
from typing import List, Dict, Tuple, Optional
from src import config

class OCRProcessor:
    def __init__(self):
        # Set tesseract path if specified in config
        if hasattr(config, 'TESSERACT_PATH') and config.TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
        
        # Load preset regions if they exist
        self.presets_file = 'table_presets.json'
        self.load_presets()
    
    def load_presets(self):
        """Load saved table format presets."""
        try:
            if os.path.exists(self.presets_file):
                with open(self.presets_file, 'r') as f:
                    loaded_presets = json.load(f)
                    config.TABLE_PRESETS.update(loaded_presets)
                    logging.info(f"Loaded {len(loaded_presets)} table presets")
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
                x, y, w, h = region['x'], region['y'], region['width'], region['height']
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
        """Validate extracted results for proper 6v6 format."""
        validation = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        player_count = len(results)
        expected_count = config.EXPECTED_PLAYERS_PER_TEAM
        
        # Check player count
        if player_count == 0:
            validation['errors'].append("No players found in image")
            validation['is_valid'] = False
        elif player_count < expected_count:
            validation['warnings'].append(f"Only {player_count} players found, expected {expected_count}")
            validation['is_valid'] = False
        elif player_count > expected_count:
            validation['warnings'].append(f"Found {player_count} players, expected {expected_count}. Extra players will be ignored.")
            # Keep only first expected_count players
            results = results[:expected_count]
        
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
        """Find clan member names and scores in text, simplified approach."""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for each clan member name in the line
            for roster_name in config.CLAN_ROSTER:
                if roster_name.lower() in line.lower():
                    # Try to find a score (number) in the same line
                    score_matches = re.findall(r'\b(\d{1,3})\b', line)
                    if score_matches:
                        # Take the first reasonable score (0-999)
                        for score_str in score_matches:
                            score = int(score_str)
                            if 0 <= score <= 999:
                                results.append({
                                    'name': roster_name,
                                    'score': score,
                                    'raw_line': line,
                                    'full_text': text
                                })
                                break
        
        return results
    
    def parse_mario_kart_results(self, texts: List[str]) -> Dict:
        """Parse extracted text to find Mario Kart race results."""
        try:
            all_results = []
            
            # Get results from all text variations
            for text in texts:
                results = self.find_clan_members_in_text(text)
                all_results.extend(results)
            
            # Remove duplicates - keep the best match for each clan member
            final_results = {}
            for result in all_results:
                name = result['name']
                if name not in final_results:
                    final_results[name] = result
                else:
                    # Keep the result with higher confidence (longer raw line = more context)
                    if len(result['raw_line']) > len(final_results[name]['raw_line']):
                        final_results[name] = result
            
            return {
                'results': list(final_results.values()),
                'total_extracted': len(final_results)
            }
            
        except Exception as e:
            logging.error(f"Parsing error: {e}")
            return {'results': [], 'total_extracted': 0}
    
    def process_image(self, image_path: str) -> Dict:
        """Complete image processing pipeline."""
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
            
            # Validate results
            validation_result = self.validate_results(parsed_data['results'])
            
            return {
                'success': True,
                'results': parsed_data['results'],
                'total_found': parsed_data['total_extracted'],
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