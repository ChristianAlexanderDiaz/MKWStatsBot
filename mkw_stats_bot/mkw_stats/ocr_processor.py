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
            
            # Check for 6v6 team splitting scenario
            logging.info(f"🚨 DEBUG: 6v6 Check - all_detected_scores={all_detected_scores}, guild_players_found={guild_players_found}")
            logging.info(f"🚨 DEBUG: 6v6 Condition: all_detected_scores == 12? {all_detected_scores == 12}")
            logging.info(f"🚨 DEBUG: 6v6 Condition: guild_players_found > 6? {guild_players_found > 6}")
            
            if all_detected_scores == 12 and guild_players_found > 6:
                logging.info(f"🔀 6v6 Split Detection: {guild_players_found} guild players in 12-player match")
                logging.info(f"🚨 DEBUG: CALLING _apply_6v6_team_splitting() with {len(results)} guild results")
                
                results_before = len(results)
                results = self._apply_6v6_team_splitting(results, tokens, guild_id)
                results_after = len(results)
                
                logging.info(f"🚨 DEBUG: 6v6 splitting returned {results_after} results (was {results_before})")
                
                guild_players_found = len(results)  # Update count after splitting
                opponent_players = all_detected_scores - guild_players_found
            else:
                logging.info(f"🚨 DEBUG: 6v6 splitting SKIPPED - conditions not met")
            
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
            logging.info("🚨 DEBUG: === STARTING 6v6 TEAM SPLITTING DEBUG ===")
            logging.info(f"🚨 DEBUG: Input guild_results count: {len(guild_results)}")
            for i, result in enumerate(guild_results):
                logging.info(f"🚨 DEBUG: Input[{i}]: {result['name']} (score: {result['score']}, raw: {result.get('raw_name', 'N/A')})")
            
            # Extract all player-score pairs from tokens in order to determine positioning
            all_players = self._extract_all_players_from_tokens(tokens)
            logging.info(f"🚨 DEBUG: all_players extracted: {len(all_players)} players")
            for i, (name, score) in enumerate(all_players):
                logging.info(f"🚨 DEBUG: all_players[{i}]: '{name}' -> {score}")
            
            if len(all_players) != 12:
                logging.warning(f"⚠️ Expected 12 players for 6v6 split, found {len(all_players)}. Skipping split.")
                logging.info(f"🚨 DEBUG: RETURNING ORIGINAL guild_results (count: {len(guild_results)})")
                return guild_results
            
            # Create position mapping for guild members by matching their raw names and scores
            guild_member_positions = {}
            logging.info("🚨 DEBUG: === POSITION MAPPING PHASE ===")
            
            for result in guild_results:
                result_name = result['name']
                result_score = result['score']
                result_raw = result.get('raw_name', result_name)
                logging.info(f"🚨 DEBUG: Looking for guild member '{result_name}' (score: {result_score}, raw: '{result_raw}')")
                
                found = False
                # Find this guild member's position in the all_players list
                for pos, (player_name, score) in enumerate(all_players):
                    # Match by score and name (handle different raw name formats)
                    score_match = (score == result_score)
                    name_match1 = (player_name.lower() == result_raw.lower())
                    name_match2 = (player_name.lower() == result_name.lower())
                    name_match3 = (result_name.lower() in player_name.lower())
                    
                    logging.info(f"🚨 DEBUG:   Checking pos[{pos}]: '{player_name}' score={score}")
                    logging.info(f"🚨 DEBUG:     score_match: {score_match}")
                    logging.info(f"🚨 DEBUG:     name_match1 (raw): '{player_name}'.lower() == '{result_raw}'.lower() -> {name_match1}")
                    logging.info(f"🚨 DEBUG:     name_match2 (official): '{player_name}'.lower() == '{result_name}'.lower() -> {name_match2}")
                    logging.info(f"🚨 DEBUG:     name_match3 (substring): '{result_name}'.lower() in '{player_name}'.lower() -> {name_match3}")
                    
                    if (score_match and (name_match1 or name_match2 or name_match3)):
                        guild_member_positions[result_name] = pos
                        logging.info(f"🚨 DEBUG: ✅ MATCHED! {result_name} found at position {pos}")
                        found = True
                        break
                
                if not found:
                    logging.info(f"🚨 DEBUG: ❌ NO MATCH found for {result_name}")
            
            logging.info(f"🚨 DEBUG: Final position mapping: {guild_member_positions}")
            
            # Split guild members into two teams based on their positions
            team1_guild_members = []  # Positions 0-5
            team2_guild_members = []  # Positions 6-11
            
            logging.info("🚨 DEBUG: === TEAM ASSIGNMENT PHASE ===")
            
            for result in guild_results:
                member_name = result['name']
                if member_name in guild_member_positions:
                    pos = guild_member_positions[member_name]
                    if pos < 6:
                        team1_guild_members.append(result)
                        logging.info(f"🚨 DEBUG: {member_name} (pos {pos}) -> TEAM 1")
                    else:
                        team2_guild_members.append(result)
                        logging.info(f"🚨 DEBUG: {member_name} (pos {pos}) -> TEAM 2")
                else:
                    logging.warning(f"⚠️ Could not find position for guild member {member_name}")
                    logging.info(f"🚨 DEBUG: {member_name} (no pos) -> TEAM 1 (default)")
                    # Default to team1 if position unknown
                    team1_guild_members.append(result)
            
            team1_guild_count = len(team1_guild_members)
            team2_guild_count = len(team2_guild_members)
            
            logging.info("🚨 DEBUG: === TEAM COMPOSITION ===")
            logging.info(f"🚨 DEBUG: Team 1 ({team1_guild_count} members):")
            for member in team1_guild_members:
                logging.info(f"🚨 DEBUG:   - {member['name']} ({member['score']})")
            
            logging.info(f"🚨 DEBUG: Team 2 ({team2_guild_count} members):")
            for member in team2_guild_members:
                logging.info(f"🚨 DEBUG:   - {member['name']} ({member['score']})")
            
            # Apply majority rule
            logging.info("🚨 DEBUG: === MAJORITY RULE DECISION ===")
            if team1_guild_count > team2_guild_count:
                winning_team = team1_guild_members
                excluded_team = team2_guild_members
                winning_team_num = 1
                logging.info(f"🚨 DEBUG: Team 1 WINS ({team1_guild_count} > {team2_guild_count})")
            elif team2_guild_count > team1_guild_count:
                winning_team = team2_guild_members
                excluded_team = team1_guild_members
                winning_team_num = 2
                logging.info(f"🚨 DEBUG: Team 2 WINS ({team2_guild_count} > {team1_guild_count})")
            else:
                # Tie scenario - return all players and let user manually decide
                logging.info(f"🤝 Team split tie: {team1_guild_count} vs {team2_guild_count} guild members.")
                logging.info(f"🚨 DEBUG: TIE SCENARIO - returning all guild_results (count: {len(guild_results)})")
                logging.info(f"TODO: Implement user choice for tie scenarios. Recording all players for now.")
                return guild_results
            
            # Enhanced logging for team split decision
            logging.info(f"🏆 Team {winning_team_num} wins: {len(winning_team)} guild members vs {len(excluded_team)}")
            
            if winning_team:
                winning_summary = ", ".join([f"{result['name']} {result['score']}" for result in winning_team])
                logging.info(f"✅ Recording team {winning_team_num}: {winning_summary}")
                logging.info(f"🚨 DEBUG: RETURNING winning team (count: {len(winning_team)})")
                for i, member in enumerate(winning_team):
                    logging.info(f"🚨 DEBUG: Returning[{i}]: {member['name']} ({member['score']})")
            
            if excluded_team:
                excluded_summary = ", ".join([f"{result['name']} {result['score']}" for result in excluded_team])
                logging.info(f"❌ Excluded team: {excluded_summary} (opposing team)")
                logging.info(f"🚨 DEBUG: EXCLUDED team (count: {len(excluded_team)})")
                for i, member in enumerate(excluded_team):
                    logging.info(f"🚨 DEBUG: Excluded[{i}]: {member['name']} ({member['score']})")
            
            logging.info("🚨 DEBUG: === END 6v6 TEAM SPLITTING DEBUG ===")
            return winning_team  # Return only the winning team results
            
        except Exception as e:
            logging.error(f"❌ Error applying 6v6 team splitting: {e}")
            logging.error(f"🚨 DEBUG: EXCEPTION - returning original guild_results (count: {len(guild_results)})")
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

    def _extract_all_players_from_tokens(self, tokens: List[str]) -> List[tuple]:
        """Extract all player-score pairs from raw OCR tokens, handling corrupted OCR."""
        players = []
        i = 0
        
        while i < len(tokens):
            # Skip tokens that are clearly standalone scores
            if tokens[i].isdigit() and 1 <= int(tokens[i]) <= 180:
                i += 1
                continue
            
            # Check for corrupted token containing both name and score (like "GO IDiceyBIG RIC69")
            if len(tokens[i]) > 8:  # Long tokens are more likely to be corrupted
                embedded_score = self._extract_score_from_corrupted_token(tokens[i])
                if embedded_score:
                    # Found embedded score, treat whole token as name-score pair
                    players.append((tokens[i], embedded_score))
                    logging.info(f"🔍 Found corrupted token with embedded score: '{tokens[i]}' contains score {embedded_score}")
                    i += 1
                    continue
            
            # Check for 2-word name pattern: "Nick F." 90
            if (i < len(tokens) - 2 and 
                not tokens[i].isdigit() and 
                not tokens[i + 1].isdigit() and 
                tokens[i + 2].isdigit() and 
                1 <= int(tokens[i + 2]) <= 180):
                # Found 2-word name followed by valid score
                player_name = f"{tokens[i]} {tokens[i + 1]}"
                score = int(tokens[i + 2])
                players.append((player_name, score))
                logging.info(f"🔍 Found 2-word name: '{player_name}' with score {score}")
                i += 3  # Skip both name parts and score
                continue
            
            # Check for single-word name pattern: "Hero" 134
            if (i < len(tokens) - 1 and
                tokens[i + 1].isdigit() and 
                1 <= int(tokens[i + 1]) <= 180 and 
                not tokens[i].isdigit()):
                # Found single word name followed by valid score
                player_name = tokens[i]
                score = int(tokens[i + 1])
                players.append((player_name, score))
                logging.info(f"🔍 Found 1-word name: '{player_name}' with score {score}")
                i += 2  # Skip name and score
                continue
            
            # No valid pattern found, move to next token
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
                resolved = self.db_manager.resolve_player_name(two_word, guild_id, log_level='debug')
                if resolved:
                    valid_names.append((i, resolved, two_word))
                    logging.info(f"✅ Found 2-word name: '{two_word}' → '{resolved}' at position {i}")
                    i += 2  # Skip next token
                    continue
                else:
                    logging.debug(f"Player '{two_word}' not found in guild roster (likely opponent)")
            
            # Try single word exact match
            resolved = self.db_manager.resolve_player_name(tokens[i], guild_id, log_level='debug')
            if resolved:
                valid_names.append((i, resolved, tokens[i]))
                logging.info(f"✅ Found 1-word name: '{tokens[i]}' → '{resolved}' at position {i}")
            else:
                # Fallback: Try substring matching for corrupted OCR tokens
                # Only try this for longer tokens that might contain corrupted names
                if len(tokens[i]) >= 5:  # Avoid false positives on short tokens
                    substring_match, _ = self._find_guild_name_in_substring(tokens[i], guild_id)
                    if substring_match:
                        valid_names.append((i, substring_match, tokens[i]))
                        logging.info(f"✅ Found substring match: '{tokens[i]}' contains '{substring_match}' at position {i}")
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