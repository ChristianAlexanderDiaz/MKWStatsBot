#!/usr/bin/env python3
"""
OCR Processor for MKW Stats Bot
Based on working Discord bot PaddleOCR implementation
"""

import os
import gc
import threading
import tempfile
import logging
import re
from typing import List, Dict, Optional
from pathlib import Path
from PIL import Image, ImageDraw
import traceback
import numpy as np

# PaddleOCR imports
from paddleocr import PaddleOCR

# Thread lock for OCR operations
ocr_lock = threading.Lock()

class OCRProcessor:
    """PaddleOCR processor for Mario Kart race result images."""
    
    # Fixed coordinates for Mario Kart table region (from working Discord bot)
    CROP_COORDS = {
        'start_x': 576,
        'start_y': 100,
        'end_x': 1068,
        # end_y will be set to full image height dynamically
    }
    
    def __init__(self, db_manager=None):
        """Initialize PaddleOCR processor with memory optimization."""
        self.db_manager = db_manager
        self.ocr = None
        self._initialize_ocr()
    
    def _initialize_ocr(self):
        """Initialize PaddleOCR with optimized settings."""
        try:
            logging.info("🚀 Initializing PaddleOCR with memory-optimized settings...")
            
            # Memory-optimized PaddleOCR settings (from working Discord bot)
            self.ocr = PaddleOCR(
                use_angle_cls=False,  # Disable angle classification to save memory
                lang='en',  # Use English model (smaller than multilingual)
                use_gpu=False,  # CPU only for Railway deployment
                det_model_dir=None,  # Use default lightweight models
                rec_model_dir=None,
                cls_model_dir=None,
                show_log=False,
                use_space_char=True
            )
            
            logging.info("✅ PaddleOCR initialized successfully!")
            
        except Exception as e:
            logging.error(f"❌ Failed to initialize PaddleOCR: {e}")
            raise
    
    def cleanup_memory(self):
        """Force garbage collection to free memory."""
        gc.collect()
    
    def crop_image_to_target_region(self, image_path: str) -> tuple[str, str, tuple]:
        """Crop image to target region and create visualization - returns (cropped_path, visual_path, crop_coords)"""
        try:
            # Load image
            image = Image.open(image_path)
            img_width, img_height = image.size
            
            # Fixed coordinates from working Discord bot
            start_x = self.CROP_COORDS['start_x']
            start_y = self.CROP_COORDS['start_y']
            end_x = self.CROP_COORDS['end_x']
            end_y = img_height  # Extend to full height of current image
            
            # Ensure coordinates are within bounds
            start_x = max(0, min(start_x, img_width))
            start_y = max(0, min(start_y, img_height))
            end_x = max(0, min(end_x, img_width))
            end_y = max(0, min(end_y, img_height))
            
            crop_coords = (start_x, start_y, end_x, end_y)
            
            # Crop the image
            cropped_image = image.crop(crop_coords)
            
            # Create visualization showing the crop region on original image
            visual_image = image.copy()
            draw = ImageDraw.Draw(visual_image)
            
            # Draw rectangle showing crop region
            draw.rectangle(crop_coords, outline="red", width=8)
            
            # Add text labels
            draw.text((start_x + 10, start_y + 10), "OCR REGION", fill="red")
            draw.text((start_x + 10, start_y + 40), f"{end_x - start_x}x{end_y - start_y}px", fill="red")
            
            # Save both images
            cropped_path = image_path.replace('.png', '_cropped.png').replace('.jpg', '_cropped.jpg').replace('.jpeg', '_cropped.jpg')
            visual_path = image_path.replace('.png', '_visual.png').replace('.jpg', '_visual.jpg').replace('.jpeg', '_visual.jpg')
            
            cropped_image.save(cropped_path)
            visual_image.save(visual_path)
            
            logging.info(f"✂️ Cropped image {img_width}x{img_height} to region ({start_x},{start_y}) to ({end_x},{end_y})")
            
            return cropped_path, visual_path, crop_coords
            
        except Exception as e:
            logging.error(f"❌ Error cropping image: {e}")
            return image_path, image_path, (0, 0, 0, 0)  # Return original if cropping fails
    
    def perform_ocr_on_file(self, image_path: str) -> dict:
        """Perform OCR on image file and return results with visualization paths"""
        try:
            # First crop the image to target region and create visualization
            cropped_path, visual_path, crop_coords = self.crop_image_to_target_region(image_path)
            
            with ocr_lock:
                # Perform OCR on cropped image
                result = self.ocr.ocr(cropped_path, cls=False)
                
                # Format results
                text_results = []
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:  # Ensure valid structure
                            text_results.append({
                                "text": line[1][0],
                                "confidence": float(line[1][1]),
                                "bbox": line[0]
                            })
                
                response = {
                    "success": True,
                    "results": text_results,
                    "text": " ".join([r["text"] for r in text_results]),
                    "cropped_path": cropped_path,
                    "visual_path": visual_path,
                    "crop_coords": crop_coords
                }
                
                # Clean up
                del result
                self.cleanup_memory()
                
                return response
                
        except Exception as e:
            self.cleanup_memory()
            logging.error(f"❌ Error in OCR: {str(e)}")
            logging.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    def process_image(self, image_path: str, message_timestamp=None, guild_id: int = 0) -> Dict:
        """Process image using PaddleOCR and return parsed Mario Kart results."""
        try:
            logging.info(f"🔍 Processing image with PaddleOCR: {image_path}")
            
            if not os.path.exists(image_path):
                logging.error(f"❌ File not found: {image_path}")
                return {
                    'success': False,
                    'error': f'Image file not found: {image_path}',
                    'results': []
                }
            
            # Perform OCR using the working Discord bot method
            ocr_result = self.perform_ocr_on_file(image_path)
            
            if not ocr_result["success"]:
                return {
                    'success': False,
                    'error': ocr_result.get('error', 'OCR processing failed'),
                    'results': []
                }
            
            # Extract text results for parsing
            extracted_texts = []
            if ocr_result.get("results"):
                for item in ocr_result["results"]:
                    text = item.get("text", "").strip()
                    confidence = item.get("confidence", 0.0)
                    
                    # Filter out junk - keep only characters, numbers, spaces, punctuation, parentheses
                    if text and re.match(r'^[a-zA-Z0-9\s.,\-+%$()]+$', text):
                        extracted_texts.append({
                            'text': text,
                            'confidence': confidence
                        })
            
            if not extracted_texts:
                return {
                    'success': False,
                    'error': 'No valid text found in image after filtering',
                    'results': []
                }
            
            # Parse Mario Kart results
            parsed_results = self._parse_mario_kart_results(extracted_texts, guild_id)
            
            if not parsed_results:
                return {
                    'success': False,
                    'error': 'No valid player results found',
                    'results': []
                }
            
            # Add metadata to results
            war_metadata = self._create_default_war_metadata(message_timestamp)
            for result_item in parsed_results:
                result_item.update(war_metadata)
            
            # Validate results
            validation_result = self._validate_results(parsed_results, guild_id)
            
            logging.info("🎉 SUCCESS! PaddleOCR processing completed!")
            
            return {
                'success': True,
                'results': parsed_results,
                'total_found': len(parsed_results),
                'war_metadata': war_metadata,
                'validation': validation_result,
                'processing_engine': 'paddleocr'
            }
            
        except Exception as e:
            logging.error(f"❌ OCR processing error: {e}")
            return {
                'success': False,
                'error': f'OCR processing failed: {str(e)}',
                'results': []
            }
    
    def _parse_mario_kart_results(self, extracted_texts: List[Dict], guild_id: int = 0) -> List[Dict]:
        """Parse extracted text to find Mario Kart player results using database validation."""
        try:
            if not self.db_manager:
                logging.error("❌ No database manager available for player validation")
                return []
            
            # Combine all OCR text into single string and tokenize
            combined_text = ' '.join([item['text'] for item in extracted_texts])
            tokens = combined_text.split()
            
            logging.info(f"🔍 OCR tokens: {tokens}")
            
            # Find all valid scores (1-180)
            score_positions = []
            for i, token in enumerate(tokens):
                if token.isdigit() and 1 <= int(token) <= 180:
                    score_positions.append(i)
                    logging.info(f"📊 Found score: {token} at position {i}")
            
            # Find all valid player names using sliding window
            valid_names = self._find_valid_names_with_window(tokens, guild_id)
            
            # Pair names with scores using proximity
            results = self._pair_names_with_scores(valid_names, score_positions, tokens)
            
            # Count total detected vs guild players
            all_detected_scores = len(score_positions)
            guild_players_found = len(results)
            opponent_players = all_detected_scores - guild_players_found
            
            logging.info(f"🎯 OCR Results: {guild_players_found} guild players found, {opponent_players} opponent players detected")
            
            # Log guild team summary
            if results:
                team_summary = ", ".join([f"{result['name']} {result['score']}" for result in results])
                logging.info(f"Your team: {team_summary}")
            
            return results
            
        except Exception as e:
            logging.error(f"❌ Error parsing Mario Kart results: {e}")
            return []
    
    def _validate_results(self, results: List[Dict], guild_id: int = 0) -> Dict:
        """Basic validation of parsed results."""
        try:
            validation = {
                'is_valid': True,
                'errors': [],
                'warnings': []
            }
            
            if not results:
                validation['is_valid'] = False
                validation['errors'].append("No results found")
                return validation
            
            # Check for duplicate players
            names = [result['name'] for result in results]
            duplicates = set([name for name in names if names.count(name) > 1])
            if duplicates:
                validation['warnings'].append(f"Duplicate players found: {', '.join(duplicates)}")
            
            # Check score ranges
            for result in results:
                score = result.get('score', 0)
                if not (1 <= score <= 180):
                    validation['warnings'].append(f"{result['name']}: Score {score} is outside normal range (1-180)")
            
            # Check minimum players
            if len(results) < 3:
                validation['warnings'].append(f"Only {len(results)} players found, expected more for a war")
            
            logging.info(f"🔍 Validation complete: {len(validation['errors'])} errors, {len(validation['warnings'])} warnings")
            
            return validation
            
        except Exception as e:
            logging.error(f"❌ Error during validation: {e}")
            return {
                'is_valid': False,
                'errors': [f"Validation failed: {str(e)}"],
                'warnings': []
            }
    
    def _create_default_war_metadata(self, message_timestamp=None) -> Dict:
        """Create default war metadata."""
        try:
            from . import config
            default_race_count = getattr(config, 'DEFAULT_RACE_COUNT', 12)
        except:
            default_race_count = 12
        
        metadata = {
            'date': None,
            'time': None, 
            'race_count': default_race_count,
            'war_type': '6v6',
            'notes': 'Auto-processed with PaddleOCR'
        }
        
        # Use message timestamp as primary source for date/time
        if message_timestamp:
            metadata['date'] = message_timestamp.strftime('%Y-%m-%d')
            metadata['time'] = message_timestamp.strftime('%H:%M:%S')
        
        return metadata
    
    def create_debug_overlay(self, image_path: str) -> str:
        """Create debug overlay showing OCR detection results."""
        try:
            logging.info("🎨 Creating debug visualization...")
            
            # Load original image
            image = Image.open(image_path).convert('RGB')
            img_width, img_height = image.size
            draw = ImageDraw.Draw(image)
            
            # Draw crop region
            start_x = self.CROP_COORDS['start_x']
            start_y = self.CROP_COORDS['start_y']
            end_x = self.CROP_COORDS['end_x']
            end_y = img_height
            
            # Draw ROI boundaries
            draw.rectangle([start_x, start_y, end_x, end_y], outline="red", width=3)
            draw.text((start_x, start_y-20), "OCR REGION", fill="red")
            
            # Process and get OCR results for visualization
            ocr_result = self.perform_ocr_on_file(image_path)
            
            if ocr_result.get("success") and ocr_result.get("results"):
                for i, result in enumerate(ocr_result["results"]):
                    text = result.get("text", "")
                    bbox = result.get("bbox", [])
                    
                    if bbox and len(bbox) >= 4:
                        # Draw bounding box (adjust coordinates)
                        if isinstance(bbox[0], list):
                            # Polygon format
                            x_coords = [point[0] for point in bbox]
                            y_coords = [point[1] for point in bbox]
                            box_x1, box_y1 = int(min(x_coords)) + start_x, int(min(y_coords)) + start_y
                            box_x2, box_y2 = int(max(x_coords)) + start_x, int(max(y_coords)) + start_y
                        else:
                            # Rectangle format
                            box_x1, box_y1, box_x2, box_y2 = bbox[:4]
                            box_x1 += start_x
                            box_y1 += start_y
                            box_x2 += start_x
                            box_y2 += start_y
                        
                        # Color based on content type
                        if re.match(r'^[\d\s.,\-+%$]+$', text.strip()):
                            color = "blue"  # Numbers in blue
                        else:
                            color = "green"  # Names in green
                        
                        draw.rectangle([box_x1, box_y1, box_x2, box_y2], outline=color, width=2)
                        draw.text((box_x1, max(0, box_y1-20)), text[:10], fill=color)
            
            # Save visualization
            output_path = image_path.replace('.png', '_debug.png').replace('.jpg', '_debug.jpg')
            image.save(output_path)
            logging.info(f"📊 Debug overlay saved: {output_path}")
            return output_path
            
        except Exception as e:
            logging.error(f"❌ Error creating debug overlay: {e}")
            return None
    
    def _find_valid_names_with_window(self, tokens: List[str], guild_id: int) -> List[tuple]:
        """Find valid player names using sliding window approach for 1-word and 2-word combinations."""
        valid_names = []
        i = 0
        
        while i < len(tokens):
            # Skip tokens that are clearly scores
            if tokens[i].isdigit() and 1 <= int(tokens[i]) <= 180:
                i += 1
                continue
            
            # Try 2-word combination first (for "No name", "kyle christian")
            if i < len(tokens) - 1:
                two_word = f"{tokens[i]} {tokens[i+1]}"
                resolved = self.db_manager.resolve_player_name(two_word, guild_id, log_level='debug')
                if resolved:
                    valid_names.append((i, resolved, two_word))
                    logging.info(f"✅ Found 2-word name: '{two_word}' → '{resolved}' at position {i}")
                    i += 2  # Skip next token
                    continue
                else:
                    logging.debug(f"Player '{two_word}' not found in guild roster (likely opponent)")
            
            # Try single word
            resolved = self.db_manager.resolve_player_name(tokens[i], guild_id, log_level='debug')
            if resolved:
                valid_names.append((i, resolved, tokens[i]))
                logging.info(f"✅ Found 1-word name: '{tokens[i]}' → '{resolved}' at position {i}")
            else:
                logging.debug(f"Player '{tokens[i]}' not found in guild roster (likely opponent)")
            
            i += 1
        
        return valid_names
    
    def _pair_names_with_scores(self, valid_names: List[tuple], score_positions: List[int], tokens: List[str]) -> List[Dict]:
        """Pair validated player names with scores using sequential flow matching."""
        results = []
        used_scores = set()
        
        # Sort names by position to process in reading order
        valid_names_sorted = sorted(valid_names, key=lambda x: x[0])
        
        for name_pos, official_name, raw_name in valid_names_sorted:
            # Find the next available score after this name position
            best_score_pos = None
            min_distance = float('inf')
            
            # First, try to find a score that comes AFTER the name (preferred pattern: "Name Score")
            for score_pos in score_positions:
                if score_pos not in used_scores and score_pos > name_pos:
                    distance = score_pos - name_pos
                    if distance < min_distance:
                        min_distance = distance
                        best_score_pos = score_pos
            
            # If no score found after the name, try scores BEFORE the name (pattern: "Score Name")
            if best_score_pos is None:
                for score_pos in score_positions:
                    if score_pos not in used_scores and score_pos < name_pos:
                        distance = name_pos - score_pos
                        # Only consider scores that are very close (within 2 positions) to avoid wrong pairings
                        if distance <= 2 and distance < min_distance:
                            min_distance = distance
                            best_score_pos = score_pos
            
            # If still no score found, fall back to absolute nearest unused score
            if best_score_pos is None:
                for score_pos in score_positions:
                    if score_pos not in used_scores:
                        distance = abs(name_pos - score_pos)
                        if distance < min_distance:
                            min_distance = distance
                            best_score_pos = score_pos
            
            if best_score_pos is not None:
                score = int(tokens[best_score_pos])
                results.append({
                    'name': official_name,
                    'raw_name': raw_name,
                    'score': score,
                    'raw_line': f"{raw_name} {score}",
                    'preset_used': 'database_validated',
                    'confidence': 1.0,  # Database validated = highest confidence
                    'is_roster_member': True  # All results are validated against roster
                })
                used_scores.add(best_score_pos)
                logging.info(f"🎯 Paired '{official_name}' (raw: '{raw_name}') at pos {name_pos} with score {score} at pos {best_score_pos}")
            else:
                logging.warning(f"⚠️ No available score found for '{official_name}'")
        
        return results