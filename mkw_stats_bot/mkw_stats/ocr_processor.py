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
                use_space_char=True,
                drop_score=0.5  # Filter low confidence results
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
        """Parse extracted text to find Mario Kart player results."""
        try:
            results = []
            
            # Get current roster from database for nickname resolution
            roster_players = self.db_manager.get_roster_players(guild_id) if self.db_manager else []
            
            # Create single text string for processing
            combined_text = '\n'.join([item['text'] for item in extracted_texts])
            lines = combined_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Look for complete player names that may include spaces and parentheses
                name_pattern = r'([A-Za-z0-9][A-Za-z0-9\s()]*[A-Za-z0-9()]|[A-Za-z0-9]{2,})'
                potential_names = re.findall(name_pattern, line)
                
                # Find all valid scores in the line
                all_scores_in_line = []
                words = line.split()
                for word in words:
                    if re.match(r'\b\d{1,3}\b', word):
                        score = int(word)
                        if 1 <= score <= 180:
                            all_scores_in_line.append(score)
                
                # If we found scores, try to match with names
                if all_scores_in_line and potential_names:
                    # Use the last score as the player's total score
                    score = all_scores_in_line[-1]
                    
                    # Find the best matching name
                    best_name = None
                    for potential_name in potential_names:
                        potential_name = potential_name.strip()
                        # Validate name: at least 2 chars, contains letters, not pure numbers
                        if (len(potential_name) >= 2 and 
                            re.search(r'[A-Za-z]', potential_name) and 
                            not re.match(r'^\d+$', potential_name)):
                            if best_name is None or len(potential_name) > len(best_name):
                                best_name = potential_name
                    
                    if best_name:
                        # Score validation 
                        if 1 <= score <= 180:
                            # Try to resolve nickname to roster name using database
                            resolved_name = best_name  # Default to detected name
                            is_roster_member = False
                            
                            if self.db_manager:
                                try:
                                    db_resolved = self.db_manager.resolve_player_name(best_name, guild_id)
                                    if db_resolved and db_resolved in roster_players:
                                        resolved_name = db_resolved
                                        is_roster_member = True
                                except Exception as e:
                                    logging.debug(f"Name resolution failed for '{best_name}': {e}")
                                    pass
                            
                            # Add detected player
                            results.append({
                                'name': resolved_name,
                                'raw_name': best_name,
                                'score': score,
                                'raw_line': line,
                                'preset_used': 'paddle_ocr_crop',
                                'confidence': 0.9 if is_roster_member else 0.7,
                                'is_roster_member': is_roster_member
                            })
                            break  # Only take first valid name per line
            
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