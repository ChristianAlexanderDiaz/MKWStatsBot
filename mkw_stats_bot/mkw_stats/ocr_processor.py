#!/usr/bin/env python3
"""
OCR Processor for MKW Stats Bot
Based on working Discord bot PaddleOCR implementation
Enhanced with Railway-optimized resource management
"""

import os
import gc
import asyncio
import threading
import tempfile
import logging
import re
from enum import Enum
from typing import List, Dict, Optional
from pathlib import Path
from PIL import Image, ImageDraw
import traceback
import numpy as np

# PaddleOCR imports
from paddleocr import PaddleOCR

# Enhanced resource management imports (optional - falls back gracefully)
try:
    from .ocr_config_manager import get_ocr_config, OCRPriority
    from .ocr_resource_manager import get_ocr_resource_manager
    from .ocr_performance_monitor import get_ocr_performance_monitor
    RESOURCE_MANAGEMENT_AVAILABLE = True
except ImportError:
    RESOURCE_MANAGEMENT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.info("Resource management modules not available - using basic OCR processing")

# Thread lock for OCR operations (preserved for compatibility)
ocr_lock = threading.Lock()

class TableFormat(Enum):
    """Enumeration of supported Mario Kart table formats."""
    LARGE = "large"
    SMALL = "small"

# Table format definitions with crop coordinates and width-based detection
TABLE_FORMATS = {
    TableFormat.LARGE: {
        'name': 'Large Format',
        'expected_width': 1720,  # Used for format detection
        'crop_coords': {
            'start_x': 576,
            'start_y': 100,
            'end_x': 1068,
            # end_y: dynamic (set to img_height in crop_image_to_target_region)
        }
    },
    TableFormat.SMALL: {
        'name': 'Small Format',
        'expected_width': 860,   # Used for format detection
        'crop_coords': {
            'start_x': 284,
            'start_y': 51,
            'end_x': 534,
            # end_y: dynamic (set to img_height in crop_image_to_target_region)
        }
    }
}

class OCRProcessor:
    """PaddleOCR processor for Mario Kart race result images."""
    
    def __init__(self, db_manager=None):
        """Initialize PaddleOCR processor with memory optimization and optional resource management."""
        self.db_manager = db_manager
        self.ocr = None
        
        # Initialize resource management if available
        self.resource_management_enabled = RESOURCE_MANAGEMENT_AVAILABLE
        if self.resource_management_enabled:
            try:
                self.config_manager = get_ocr_config()
                self.resource_manager = get_ocr_resource_manager()
                self.performance_monitor = get_ocr_performance_monitor()
                logging.info("✅ OCR Processor initialized with resource management")
            except Exception as e:
                logging.warning(f"Failed to initialize resource management: {e}")
                self.resource_management_enabled = False
        
        if not self.resource_management_enabled:
            logging.info("📝 OCR Processor initialized in basic mode (no resource management)")
        
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
    
    def detect_table_format(self, img_width: int, img_height: int) -> TableFormat:
        """Detect table format based on image width. Height varies with player count."""
        # Find the closest matching format by width
        best_match = None
        smallest_diff = float('inf')
        
        for format_type, format_data in TABLE_FORMATS.items():
            expected_width = format_data['expected_width']
            width_diff = abs(img_width - expected_width)
            
            if width_diff < smallest_diff:
                smallest_diff = width_diff
                best_match = format_type
        
        if best_match:
            format_name = TABLE_FORMATS[best_match]['name']
            logging.info(f"🎯 Detected table format: {format_name} (image: {img_width}x{img_height})")
            return best_match
        else:
            # Fallback to large format if no good match
            logging.warning(f"⚠️ Unknown image size {img_width}x{img_height}, defaulting to Large Format")
            return TableFormat.LARGE
    
    def crop_image_to_target_region(self, image_path: str) -> tuple[str, str, tuple]:
        """Crop image to target region and create visualization - returns (cropped_path, visual_path, crop_coords)"""
        try:
            # Load image
            image = Image.open(image_path)
            img_width, img_height = image.size
            
            # Detect table format based on image size
            table_format = self.detect_table_format(img_width, img_height)
            crop_coords = TABLE_FORMATS[table_format]['crop_coords']
            
            # Get coordinates for detected format
            start_x = crop_coords['start_x']
            start_y = crop_coords['start_y']
            end_x = crop_coords['end_x']
            end_y = img_height  # Extend to full height of current image (preserves dynamic behavior)
            
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
            
            format_name = TABLE_FORMATS[table_format]['name']
            logging.info(f"✂️ Cropped image {img_width}x{img_height} to region ({start_x},{start_y}) to ({end_x},{end_y}) using {format_name}")
            
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
    
    async def process_image_async(self, image_path: str, guild_id: int, user_id: int,
                                 message_timestamp=None) -> Dict:
        """
        Async process image with resource management and priority allocation.
        Falls back to sync processing if resource management is unavailable.
        """
        if not self.resource_management_enabled:
            # Fallback to synchronous processing
            return self.process_image(image_path, message_timestamp, guild_id)
        
        try:
            # Create resource request
            request = self.resource_manager.create_request(
                image_count=1,
                guild_id=guild_id,
                user_id=user_id
            )
            
            # Track operation performance
            async with self.performance_monitor.track_operation(
                request.request_id, request.priority, 1, guild_id, user_id
            ) as operation_profile:
                
                # Acquire resources with priority allocation
                async with self.resource_manager.acquire_resources(request) as context:
                    self.performance_monitor.mark_operation_started(request.request_id)
                    
                    # Perform OCR processing in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, 
                        self.process_image, 
                        image_path, 
                        message_timestamp, 
                        guild_id
                    )
                    
                    # Update performance metrics
                    if result.get('success'):
                        players_detected = len(result.get('results', []))
                        # Calculate average confidence from results
                        all_confidences = [r.get('confidence', 0.0) for r in result.get('results', []) 
                                         if 'confidence' in r]
                        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
                        
                        self.performance_monitor.update_operation_results(
                            request.request_id, players_detected, avg_confidence
                        )
                    
                    # Add resource management metadata
                    if result.get('success'):
                        result['resource_priority'] = request.priority.value
                        result['processing_engine'] = 'paddleocr_with_resource_management'
                        result['wait_time_seconds'] = context.wait_time
                    
                    return result
                    
        except Exception as e:
            logging.error(f"Error in async OCR processing: {e}")
            # Fallback to synchronous processing on error
            return self.process_image(image_path, message_timestamp, guild_id)
    
    async def process_bulk_images_async(self, image_data_list: List[Dict], guild_id: int, 
                                       user_id: int) -> List[Dict]:
        """
        Process multiple images with intelligent batching and resource management.
        Falls back to individual sync processing if resource management is unavailable.
        """
        if not self.resource_management_enabled:
            # Fallback to individual synchronous processing
            results = []
            for image_data in image_data_list:
                result = self.process_image(
                    image_data['path'], 
                    image_data.get('timestamp'), 
                    guild_id
                )
                results.append(result)
            return results
        
        try:
            image_count = len(image_data_list)
            
            # Create resource request for bulk processing
            request = self.resource_manager.create_request(
                image_count=image_count,
                guild_id=guild_id,
                user_id=user_id
            )
            
            # Track bulk operation performance
            async with self.performance_monitor.track_operation(
                request.request_id, request.priority, image_count, guild_id, user_id
            ) as operation_profile:
                
                # Acquire resources with priority allocation
                async with self.resource_manager.acquire_resources(request) as context:
                    self.performance_monitor.mark_operation_started(request.request_id)
                    
                    # Process images based on batch size configuration
                    batch_size = getattr(self.config_manager.config, 'batch_size', 3)
                    results = []
                    
                    for i in range(0, image_count, batch_size):
                        batch = image_data_list[i:i + batch_size]
                        
                        # Process batch in executor
                        loop = asyncio.get_event_loop()
                        batch_tasks = []
                        
                        for image_data in batch:
                            task = loop.run_in_executor(
                                None,
                                self.process_image,
                                image_data['path'],
                                image_data.get('timestamp'),
                                guild_id
                            )
                            batch_tasks.append(task)
                        
                        # Wait for batch completion
                        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                        
                        # Handle any exceptions in batch results
                        for j, result in enumerate(batch_results):
                            if isinstance(result, Exception):
                                logging.error(f"Error processing image in batch: {result}")
                                results.append({
                                    'success': False,
                                    'error': str(result),
                                    'results': []
                                })
                            else:
                                # Add resource management metadata
                                if result.get('success'):
                                    result['resource_priority'] = request.priority.value
                                    result['processing_engine'] = 'paddleocr_bulk_with_resource_management'
                                    result['batch_number'] = i // batch_size + 1
                                results.append(result)
                        
                        # Memory cleanup between batches
                        if i + batch_size < image_count:
                            self.cleanup_memory()
                            await asyncio.sleep(0.1)  # Brief pause for cleanup
                    
                    # Update performance metrics
                    successful_results = [r for r in results if r.get('success')]
                    total_players = sum(len(r.get('results', [])) for r in successful_results)
                    
                    # Calculate bulk average confidence
                    all_confidences = []
                    for result in successful_results:
                        for player_result in result.get('results', []):
                            if 'confidence' in player_result:
                                all_confidences.append(player_result['confidence'])
                    
                    avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
                    
                    self.performance_monitor.update_operation_results(
                        request.request_id, total_players, avg_confidence
                    )
                    
                    return results
                    
        except Exception as e:
            logging.error(f"Error in bulk async OCR processing: {e}")
            # Fallback to individual synchronous processing
            results = []
            for image_data in image_data_list:
                try:
                    result = self.process_image(
                        image_data['path'], 
                        image_data.get('timestamp'), 
                        guild_id
                    )
                    results.append(result)
                except Exception as individual_error:
                    results.append({
                        'success': False,
                        'error': str(individual_error),
                        'results': []
                    })
            return results
    
    def get_performance_stats(self) -> Dict:
        """Get current performance statistics from the processor."""
        if not self.resource_management_enabled:
            return {
                'resource_management': False,
                'status': 'basic_mode'
            }
        
        try:
            return {
                'resource_management': True,
                'configuration': self.config_manager.export_configuration(),
                'resource_stats': self.resource_manager.get_current_stats(),
                'performance_stats': self.performance_monitor.get_current_stats()
            }
        except Exception as e:
            logging.error(f"Error getting performance stats: {e}")
            return {
                'resource_management': True,
                'status': 'error',
                'error': str(e)
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
                # Skip race count tokens like (5), (3), etc.
                race_count_patterns = [
                    r'^\((\d+)\)$',  # (5)
                    r'^\((\d+)$',    # (5
                    r'^(\d+)\)$'     # 5)
                ]
                
                is_race_count_token = False
                for pattern in race_count_patterns:
                    match = re.match(pattern, token.strip())
                    if match:
                        race_num = int(match.group(1))
                        if 1 <= race_num <= 11:  # Valid race count range
                            is_race_count_token = True
                            logging.info(f"🏁 Skipping race count token '{token}' in score detection")
                            break
                
                if is_race_count_token:
                    continue
                    
                if token.isdigit() and 1 <= int(token) <= 180:
                    score_positions.append(i)
                    logging.info(f"📊 Found score: {token} at position {i}")
                else:
                    # Check for embedded scores in corrupted tokens (like "RIC69")
                    # But only if this token is NOT followed by another valid score
                    has_following_score = False
                    if i < len(tokens) - 1:
                        next_token = tokens[i + 1]
                        if next_token.isdigit() and 1 <= int(next_token) <= 180:
                            has_following_score = True
                    
                    # Only treat as embedded score if NO following score exists
                    if not has_following_score:
                        embedded_score = self._extract_score_from_corrupted_token(token)
                        if embedded_score:
                            score_positions.append(i)
                            logging.info(f"📊 Found embedded score: {embedded_score} in token '{token}' at position {i}")
                    else:
                        logging.info(f"🔍 Skipping potential embedded score in '{token}' because followed by valid score '{next_token}'")
            
            # Find all valid player names using sliding window
            valid_names = self._find_valid_names_with_window(tokens, guild_id)
            
            # Pair names with scores using proximity
            results = self._pair_names_with_scores(valid_names, score_positions, tokens)
            
            # Count total detected vs guild players
            all_detected_scores = len(score_positions)
            guild_players_found = len(results)
            opponent_players = all_detected_scores - guild_players_found
            
            # Check for 6v6 team splitting scenario
            if all_detected_scores == 12:
                logging.info(f"🔀 6v6 Split Detection: {guild_players_found} guild players in 12-player match")
                results = self._apply_6v6_team_splitting(results, tokens, guild_id)
                guild_players_found = len(results)  # Update count after splitting
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
    
    def _apply_6v6_team_splitting(self, guild_results: List[Dict], tokens: List[str], guild_id: int) -> List[Dict]:
        """Apply 6v6 team splitting using majority rule based on player positions in raw OCR."""
        try:
            logging.info("🔀 Starting 6v6 team splitting analysis")
            
            # Extract all player-score pairs from tokens in order to determine positioning
            all_players = self._extract_all_players_from_tokens(tokens, guild_id)
            logging.info(f"📊 Extracted {len(all_players)} total players from OCR tokens")
            
            if len(all_players) != 12:
                logging.warning(f"⚠️ Expected 12 players for 6v6 split, found {len(all_players)}. Skipping split.")
                return guild_results
            
            # Create position mapping for guild members by matching their raw names and scores
            guild_member_positions = {}
            
            for result in guild_results:
                result_name = result['name']
                result_score = result['score']
                result_raw = result.get('raw_name', result_name)
                
                # Find this guild member's position in the all_players list
                for pos, (player_name, score) in enumerate(all_players):
                    # Match by score and name (handle different raw name formats)
                    score_match = (score == result_score)
                    name_match1 = (player_name.lower() == result_raw.lower())
                    name_match2 = (player_name.lower() == result_name.lower())
                    name_match3 = (result_name.lower() in player_name.lower())
                    
                    if (score_match and (name_match1 or name_match2 or name_match3)):
                        guild_member_positions[result_name] = pos
                        logging.info(f"🎯 {result_name} found at position {pos}")
                        break
            
            # Split guild members into two teams based on their positions
            team1_guild_members = []  # Positions 0-5
            team2_guild_members = []  # Positions 6-11
            
            for result in guild_results:
                member_name = result['name']
                if member_name in guild_member_positions:
                    pos = guild_member_positions[member_name]
                    if pos < 6:
                        team1_guild_members.append(result)
                    else:
                        team2_guild_members.append(result)
                else:
                    logging.warning(f"⚠️ Could not find position for guild member {member_name}")
                    # Default to team1 if position unknown
                    team1_guild_members.append(result)
            
            team1_guild_count = len(team1_guild_members)
            team2_guild_count = len(team2_guild_members)
            
            # Log team composition summary
            team1_names = [m['name'] for m in team1_guild_members]
            team2_names = [m['name'] for m in team2_guild_members]
            logging.info(f"🏁 Team split - First 6: {team1_guild_count} guild members ({', '.join(team1_names)})")
            logging.info(f"🏁 Team split - Last 6: {team2_guild_count} guild members ({', '.join(team2_names)})")
            
            # Apply majority rule
            if team1_guild_count > team2_guild_count:
                winning_team = team1_guild_members
                excluded_team = team2_guild_members
                winning_team_num = 1
            elif team2_guild_count > team1_guild_count:
                winning_team = team2_guild_members
                excluded_team = team1_guild_members
                winning_team_num = 2
            else:
                # Tie scenario - return all players and let user manually decide
                logging.info(f"🤝 Team split tie: {team1_guild_count} vs {team2_guild_count} guild members - recording all players")
                return guild_results
            
            # Log final decision
            winning_names = [r['name'] for r in winning_team]
            excluded_names = [r['name'] for r in excluded_team]
            
            logging.info(f"🏆 6v6 Result - Team {winning_team_num} selected: {', '.join(winning_names)}")
            if excluded_team:
                logging.info(f"❌ Excluded opposing team: {', '.join(excluded_names)}")
            
            return winning_team  # Return only the winning team results
            
        except Exception as e:
            logging.error(f"❌ Error applying 6v6 team splitting: {e}")
            return guild_results  # Return original results if splitting fails
    
    def _extract_score_from_corrupted_token(self, token: str) -> int:
        """Extract score (1-180) from a corrupted token containing mixed text and numbers."""
        import re
        # Find all numbers in the token
        numbers = re.findall(r'\d+', token)
        
        for num_str in numbers:
            try:
                num = int(num_str)
                if 1 <= num <= 180:  # Valid Mario Kart score range
                    return num
            except ValueError:
                continue
        
        return None

    def _extract_all_players_from_tokens(self, tokens: List[str], guild_id: int = 0) -> List[tuple]:
        """Extract all player-score pairs using database-first approach for proper 6v6 splitting."""
        if not self.db_manager:
            logging.error("❌ No database manager available for guild member lookup")
            return []
            
        # Get all guild members upfront (one database call)
        guild_players = self.db_manager.get_all_players_stats(guild_id)
        if not guild_players:
            logging.warning("⚠️ No guild players found in database")
            return []
            
        # Create lookup sets for faster searching
        guild_names = set()
        guild_nicknames = {}
        for player in guild_players:
            player_name = player.get('player_name', '').lower()
            guild_names.add(player_name)
            nicknames = player.get('nicknames', [])
            if nicknames:
                for nickname in nicknames:
                    guild_nicknames[nickname.lower()] = player_name
        
        logging.info(f"🔍 Database lookup ready: {len(guild_names)} guild members, {len(guild_nicknames)} nicknames")
        
        players = []
        i = 0
        
        def find_guild_member_in_token(token: str) -> str:
            """Check if token contains a guild member name or nickname."""
            token_lower = token.lower()
            
            # Check exact match first
            if token_lower in guild_names:
                return token_lower
                
            # Check nickname match
            if token_lower in guild_nicknames:
                return guild_nicknames[token_lower]
                
            # Check substring matches (for corrupted OCR like 'IDiceyBIG')
            for name in guild_names:
                if len(name) >= 2 and name in token_lower:
                    return name
                    
            # Check nickname substrings
            for nickname, real_name in guild_nicknames.items():
                if len(nickname) >= 2 and nickname in token_lower:
                    return real_name
                    
            return None
        
        while i < len(tokens):
            current_token = tokens[i]
            
            # Case 1: Current token is a standalone score - look ahead for name
            if current_token.isdigit() and 1 <= int(current_token) <= 180:
                score = int(current_token)
                
                # Look ahead for name in next token
                if i < len(tokens) - 1:
                    next_token = tokens[i + 1]
                    guild_member = find_guild_member_in_token(next_token)
                    
                    if guild_member:
                        # Found guild member after score - reversed pattern like "93 vee"
                        players.append((next_token, score))
                        logging.info(f"🔍 Found reversed pattern (guild): '{current_token} {next_token}' -> {next_token}: {score}")
                        i += 2
                        continue
                    else:
                        # Not a guild member, but still extract as opponent
                        players.append((next_token, score))
                        logging.info(f"🔍 Found reversed pattern (opponent): '{current_token} {next_token}' -> {next_token}: {score}")
                        i += 2
                        continue
                else:
                    # No next token, skip standalone score
                    logging.warning(f"⚠️ Standalone score '{current_token}' at end of tokens")
                    i += 1
                    continue
            
            # Case 2: Current token contains letters - check for guild member
            if not current_token.isdigit():
                guild_member = find_guild_member_in_token(current_token)
                
                if guild_member:
                    # Found guild member - look for score
                    score = None
                    consumed_tokens = 1
                    
                    # First check if current token has embedded score
                    embedded_score = self._extract_score_from_corrupted_token(current_token)
                    if embedded_score:
                        score = embedded_score
                        logging.info(f"🔍 Found guild member with embedded score: '{current_token}' -> {guild_member}: {score}")
                    else:
                        # Look ahead for score in next tokens
                        for lookahead in range(1, min(3, len(tokens) - i)):
                            next_token = tokens[i + lookahead]
                            
                            # Check if next token is a pure score
                            if next_token.isdigit() and 1 <= int(next_token) <= 180:
                                score = int(next_token)
                                consumed_tokens += lookahead
                                logging.info(f"🔍 Found guild member with following score: '{current_token}' -> {guild_member}: {score}")
                                break
                            
                            # Check if next token has embedded score
                            embedded_score = self._extract_score_from_corrupted_token(next_token)
                            if embedded_score:
                                score = embedded_score
                                consumed_tokens += lookahead
                                logging.info(f"🔍 Found guild member with embedded score in next token: '{current_token} {next_token}' -> {guild_member}: {score}")
                                break
                    
                    if score:
                        players.append((current_token, score))
                        i += consumed_tokens
                        continue
                    else:
                        logging.warning(f"⚠️ Guild member '{current_token}' found but no score located")
                        i += 1
                        continue
                
                # Case 3: Not a guild member - check for opponent player patterns
                
                # Try standard name-score pattern
                if (i < len(tokens) - 1 and 
                    tokens[i + 1].isdigit() and 
                    1 <= int(tokens[i + 1]) <= 180):
                    score = int(tokens[i + 1])
                    players.append((current_token, score))
                    logging.info(f"🔍 Found opponent player: '{current_token}' -> {current_token}: {score}")
                    i += 2
                    continue
                
                # Try 2-word opponent pattern
                if (i < len(tokens) - 2 and 
                    not tokens[i + 1].isdigit() and
                    tokens[i + 2].isdigit() and 
                    1 <= int(tokens[i + 2]) <= 180):
                    opponent_name = f"{current_token} {tokens[i + 1]}"
                    score = int(tokens[i + 2])
                    players.append((opponent_name, score))
                    logging.info(f"🔍 Found 2-word opponent: '{opponent_name}' -> {opponent_name}: {score}")
                    i += 3
                    continue
                
                # Check for embedded score in current token
                embedded_score = self._extract_score_from_corrupted_token(current_token)
                if embedded_score:
                    players.append((current_token, embedded_score))
                    logging.info(f"🔍 Found opponent with embedded score: '{current_token}' -> {current_token}: {embedded_score}")
                    i += 1
                    continue
            
            # Case 4: No pattern found - skip token
            logging.debug(f"🔍 No pattern found for token '{current_token}', skipping")
            i += 1
        
        logging.info(f"🔍 Extracted {len(players)} player-score pairs: {[f'{name}:{score}' for name, score in players]}")
        return players
    
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
            
            # Draw crop region using format detection
            table_format = self.detect_table_format(img_width, img_height)
            crop_coords = TABLE_FORMATS[table_format]['crop_coords']
            
            start_x = crop_coords['start_x']
            start_y = crop_coords['start_y']
            end_x = crop_coords['end_x']
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
    
    def _find_guild_name_in_substring(self, corrupted_token: str, guild_id: int) -> tuple:
        """Find guild member names as substrings within corrupted OCR tokens."""
        try:
            if not self.db_manager:
                return None, None
            
            # Get all guild player names
            guild_players = self.db_manager.get_all_players_stats(guild_id)
            if not guild_players:
                return None, None
            
            # Check each guild member name as substring (case-insensitive)
            best_match = None
            best_match_name = None
            longest_length = 0
            
            for player in guild_players:
                player_name = player.get('player_name', '')
                # Also check nicknames
                nicknames = player.get('nicknames', [])
                all_names = [player_name] + (nicknames if nicknames else [])
                
                for name in all_names:
                    if len(name) >= 3 and name.lower() in corrupted_token.lower():
                        # Prefer longer matches to avoid false positives
                        if len(name) > longest_length:
                            best_match = player_name  # Always return official name
                            best_match_name = name    # But track which variant matched
                            longest_length = len(name)
            
            if best_match:
                logging.info(f"🔍 Substring match: Found '{best_match}' (via '{best_match_name}') in corrupted token '{corrupted_token}'")
                return best_match, best_match_name
            
            return None, None
            
        except Exception as e:
            logging.error(f"❌ Error in substring matching: {e}")
            return None, None

    def _find_valid_names_with_window(self, tokens: List[str], guild_id: int) -> List[tuple]:
        """Find valid player names using sliding window approach with substring fallback for corrupted OCR."""
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
                race_count_2word = 12  # Default
                two_word_to_check = two_word
                raw_name_2word = two_word
                tokens_consumed_2word = 2
                
                # Check if the 2-word combination has race count patterns
                race_patterns = [
                    r'^(.+?)\s*\((\d+)\)$',  # Name (5)
                    r'^(.+?)\s*\((\d+)$',    # Name (5
                    r'^(.+?)\s*(\d+)\)$'     # Name 5)
                ]
                
                for pattern in race_patterns:
                    match = re.match(pattern, two_word.strip())
                    if match:
                        clean_2word_name = match.group(1).strip()
                        extracted_races = int(match.group(2))
                        if 1 <= extracted_races <= 11:
                            two_word_to_check = clean_2word_name
                            race_count_2word = extracted_races
                            logging.info(f"🏁 Extracted race count from 2-word token '{two_word}': {clean_2word_name} → {race_count_2word} races")
                        break
                
                # If no race count in 2-word combo, check if next token (i+2) has race count
                if race_count_2word == 12 and i < len(tokens) - 2:
                    next_token = tokens[i + 2]
                    pair_patterns = [
                        r'^\((\d+)\)$',  # (5)
                        r'^\((\d+)$',    # (5
                        r'^(\d+)\)$'     # 5)
                    ]
                    
                    for pattern in pair_patterns:
                        match = re.match(pattern, next_token.strip())
                        if match:
                            extracted_races = int(match.group(1))
                            if 1 <= extracted_races <= 11:
                                race_count_2word = extracted_races
                                raw_name_2word = f"{two_word} {next_token}"
                                tokens_consumed_2word = 3
                                logging.info(f"🏁 Extracted race count from 2-word + token '{two_word}' + '{next_token}': {two_word_to_check} → {race_count_2word} races")
                            break
                
                resolved = self.db_manager.resolve_player_name(two_word_to_check, guild_id, log_level='debug')
                if resolved:
                    valid_names.append((i, resolved, raw_name_2word, None, race_count_2word))
                    logging.info(f"✅ Found 2-word name: '{raw_name_2word}' → '{resolved}' at position {i} ({race_count_2word} races)")
                    i += tokens_consumed_2word  # Skip consumed tokens
                    continue
                else:
                    logging.debug(f"Player '{two_word}' not found in guild roster (likely opponent)")
            
            # Try single word exact match (check for race count patterns first)
            token_to_check = tokens[i]
            race_count = 12  # Default race coun
            raw_name = tokens[i]
            tokens_consumed = 1
            
            # Check current token for race count patterns like "Cynical (5)" or "Cynical (5"
            race_patterns = [
                r'^(.+?)\s*\((\d+)\)$',  # Name (5)
                r'^(.+?)\s*\((\d+)$',    # Name (5
                r'^(.+?)\s*(\d+)\)$'     # Name 5)
            ]
            
            for pattern in race_patterns:
                match = re.match(pattern, token_to_check.strip())
                if match:
                    clean_name = match.group(1).strip()
                    extracted_races = int(match.group(2))
                    if 1 <= extracted_races <= 11:
                        token_to_check = clean_name
                        race_count = extracted_races
                        logging.info(f"🏁 Extracted race count from token '{raw_name}': {clean_name} → {race_count} races")
                    break
            
            # If no race count in current token, check if next token has race count pattern
            if race_count == 12 and i < len(tokens) - 1:
                next_token = tokens[i + 1]
                pair_patterns = [
                    r'^\((\d+)\)$',  # (5)
                    r'^\((\d+)$',    # (5
                    r'^(\d+)\)$'     # 5)
                ]
                
                for pattern in pair_patterns:
                    match = re.match(pattern, next_token.strip())
                    if match:
                        extracted_races = int(match.group(1))
                        if 1 <= extracted_races <= 11:
                            race_count = extracted_races
                            raw_name = f"{tokens[i]} {next_token}"
                            tokens_consumed = 2
                            logging.info(f"🏁 Extracted race count from token pair '{tokens[i]}' + '{next_token}': {token_to_check} → {race_count} races")
                        break
            
            # Now try to resolve the clean name
            resolved = self.db_manager.resolve_player_name(token_to_check, guild_id, log_level='debug')
            if resolved:
                valid_names.append((i, resolved, raw_name, None, race_count))
                logging.info(f"✅ Found 1-word name: '{raw_name}' → '{resolved}' at position {i} ({race_count} races)")
                if tokens_consumed == 2:
                    i += 1  # Skip the next token if we consumed it
            else:
                # Fallback: Try substring matching for corrupted OCR tokens
                # Only try this for longer tokens that might contain corrupted names
                if len(tokens[i]) >= 5:  # Avoid false positives on short tokens
                    substring_match, _ = self._find_guild_name_in_substring(tokens[i], guild_id)
                    if substring_match:
                        # Check if this is part of a multi-token corrupted sequence
                        # Look ahead for tokens that might contain embedded scores
                        consumed_tokens = 1  # Start with current token
                        embedded_score = None
                        raw_name_parts = [tokens[i]]
                        
                        # Look ahead up to 2 positions for embedded scores
                        for lookahead in range(1, min(3, len(tokens) - i)):
                            next_token = tokens[i + lookahead]
                            # Skip very short tokens or obvious separators
                            if len(next_token) < 3 or next_token.lower() in ['go', 'and', 'vs']:
                                continue
                                
                            # Apply same context-based logic: only treat as embedded score 
                            # if this token is NOT followed by another valid score
                            token_has_following_score = False
                            if i + lookahead < len(tokens) - 1:
                                following_token = tokens[i + lookahead + 1]
                                if following_token.isdigit() and 1 <= int(following_token) <= 180:
                                    token_has_following_score = True
                            
                            if not token_has_following_score:
                                potential_score = self._extract_score_from_corrupted_token(next_token)
                                if potential_score:
                                    logging.info(f"🔍 Multi-token corrupted sequence detected: '{tokens[i]}' + '{next_token}' contains score {potential_score}")
                                    embedded_score = potential_score
                                    raw_name_parts.append(next_token)
                                    consumed_tokens += lookahead
                                    break
                            else:
                                logging.info(f"🔍 Skipping multi-token sequence for '{next_token}' because followed by valid score '{following_token}'")
                        
                        # Store the match with embedded score info if found
                        raw_name = " ".join(raw_name_parts)
                        if embedded_score:
                            # Embedded score found - use it directly
                            match_info = (i, substring_match, raw_name, embedded_score, 12)
                            logging.info(f"✅ Found multi-token corrupted match: '{raw_name}' → '{substring_match}' with embedded score {embedded_score} (12 races)")
                        else:
                            # No embedded score - will need score pairing
                            match_info = (i, substring_match, raw_name, None, 12)
                            logging.info(f"✅ Found substring match: '{tokens[i]}' contains '{substring_match}' at position {i} (12 races)")
                        
                        valid_names.append(match_info)
                        i += consumed_tokens  # Skip the consumed tokens
                        continue
                    else:
                        logging.debug(f"Player '{tokens[i]}' not found in guild roster (likely opponent)")
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
        
        for name_match in valid_names_sorted:
            # All matches are now 5-element tuples: (pos, name, raw_name, embedded_score, race_count)
            name_pos, official_name, raw_name, embedded_score, race_count = name_match
            
            if embedded_score is not None:
                # Use the embedded score directly for multi-token corrupted sequences
                score = embedded_score
                results.append({
                    'name': official_name,
                    'raw_name': raw_name,
                    'score': score,
                    'races': race_count,
                    'raw_line': f"{raw_name} {score}",
                    'preset_used': 'database_validated',
                    'confidence': 1.0,  # Database validated = highest confidence
                    'is_roster_member': True  # All results are validated against roster
                })
                logging.info(f"🎯 Used embedded score: '{official_name}' (raw: '{raw_name}') with embedded score {score} ({race_count} races)")
                continue
            
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
                    'races': race_count,
                    'raw_line': f"{raw_name} {score}",
                    'preset_used': 'database_validated',
                    'confidence': 1.0,  # Database validated = highest confidence
                    'is_roster_member': True  # All results are validated against roster
                })
                used_scores.add(best_score_pos)
                logging.info(f"🎯 Paired '{official_name}' (raw: '{raw_name}') at pos {name_pos} with score {score} at pos {best_score_pos} ({race_count} races)")
            else:
                logging.warning(f"⚠️ No available score found for '{official_name}'")
        
        return results