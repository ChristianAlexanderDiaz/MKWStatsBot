"""
Mario Kart Race Results OCR Processor using PaddleOCR
====================================================

Clean, well-documented OCR processor specifically designed for extracting 
player names and scores from Mario Kart race results tables using PaddleOCR.

Author: Claude & Christian
Created: 2025-01-24
"""

import cv2
import numpy as np
import re
import logging
import json
import os
import time
from typing import List, Dict, Tuple, Optional
from paddleocr import PaddleOCR
from . import config


class PaddleOCRProcessor:
    """
    Mario Kart racing results OCR processor using PaddleOCR engine.
    
    Handles text detection, recognition, and validation for Mario Kart race results
    tables with complex gaming backgrounds. Optimized for extracting player names
    (including those with parentheses indicating race counts) and scores from 
    structured table layouts.
    
    Attributes:
        ocr (PaddleOCR): The PaddleOCR instance configured for English text
        db_manager: Database manager for player name resolution
        score_range (Tuple[int, int]): Valid score range (1, 180) for Mario Kart
    """
    
    def __init__(self, db_manager=None):
        """
        Initialize PaddleOCR processor with English model optimized for table text.
        
        Configures PaddleOCR with settings optimized for Mario Kart results tables:
        - English language model for gaming text
        - Angle classification enabled for rotated text
        - Optimized confidence thresholds
        
        Args:
            db_manager (DatabaseManager, optional): Database manager for player name 
                resolution and roster lookups. Defaults to None.
                
        Raises:
            ImportError: If PaddleOCR is not installed
            RuntimeError: If PaddleOCR initialization fails
        """
        try:
            # Initialize PaddleOCR with English model (v3.1.0 compatible)
            self.ocr = PaddleOCR(
                use_angle_cls=True,    # Enable angle classification for rotated text
                lang='en'              # English language model
            )
            logging.info("✅ PaddleOCR v3.1.0 initialized successfully")
            
        except ImportError as e:
            if "paddle" in str(e).lower():
                logging.error(f"❌ PaddlePaddle core framework required: {e}")
                raise ImportError(
                    "PaddleOCR requires PaddlePaddle framework. Install with:\n"
                    "  pip install paddlepaddle\n"
                    "  pip install paddleocr\n"
                    "Or use CPU version: pip install paddlepaddle-cpu"
                )
            else:
                logging.error(f"❌ PaddleOCR not installed: {e}")
                raise ImportError("PaddleOCR is required. Install with: pip install paddleocr")
        except Exception as e:
            logging.error(f"❌ PaddleOCR initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize PaddleOCR: {e}")
        
        # Store database manager for name resolution
        self.db_manager = db_manager
        
        # Mario Kart scoring system constants
        self.score_range = (1, 180)  # Valid score range for Mario Kart
        self.min_confidence = 0.5    # Minimum confidence for text detection
        
        logging.info(f"🏁 PaddleOCR processor ready - Score range: {self.score_range}")
    
    def process_image(self, image_path: str, guild_id: int = 0) -> Dict:
        """
        Main entry point - extract all player results from Mario Kart table.
        
        Processes a Mario Kart race results image to extract player names and scores.
        This is the primary method that orchestrates the entire OCR pipeline:
        detection, recognition, parsing, and validation.
        
        Args:
            image_path (str): Path to the Mario Kart results image file
            guild_id (int, optional): Guild ID for player name resolution. Defaults to 0.
            
        Returns:
            Dict: Processing results containing:
                - success (bool): Whether processing was successful
                - results (List[Dict]): List of player results with name, score, etc.
                - total_found (int): Number of players extracted
                - validation (Dict): Validation results and warnings
                - error (str, optional): Error message if processing failed
                
        Raises:
            FileNotFoundError: If image_path doesn't exist
            ValueError: If image cannot be loaded or processed
        """
        try:
            logging.info(f"🔍 Processing Mario Kart results image: {image_path}")
            
            # Validate image exists
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image not found: {image_path}")
            
            # Extract text elements with positions using PaddleOCR
            text_elements = self.extract_text_with_positions(image_path)
            
            if not text_elements:
                return {
                    'success': False,
                    'error': 'No text elements detected in image',
                    'results': [],
                    'total_found': 0
                }
            
            logging.info(f"📊 Detected {len(text_elements)} text elements")
            
            # Parse Mario Kart table data from detected text
            player_results = self.parse_mario_kart_table(text_elements, guild_id)
            
            if not player_results:
                return {
                    'success': False,
                    'error': 'No valid player results found in table',
                    'results': [],
                    'total_found': 0
                }
            
            # Validate the extracted results
            validation_result = self.validate_results(player_results, guild_id)
            
            logging.info(f"✅ Successfully extracted {len(player_results)} player results")
            
            return {
                'success': True,
                'results': player_results,
                'total_found': len(player_results),
                'validation': validation_result
            }
            
        except FileNotFoundError as e:
            logging.error(f"❌ File error: {e}")
            return {
                'success': False,
                'error': str(e),
                'results': [],
                'total_found': 0
            }
        except Exception as e:
            logging.error(f"❌ Image processing error: {e}")
            return {
                'success': False,
                'error': f'Processing failed: {str(e)}',
                'results': [],
                'total_found': 0
            }
    
    def extract_text_with_positions(self, image_path: str) -> List[Dict]:
        """
        Get text elements with bounding boxes using PaddleOCR detection.
        
        Uses PaddleOCR to detect and recognize all text in the image, returning
        structured data with text content, spatial coordinates, and confidence scores.
        This method handles the low-level OCR operations and formats results for
        further processing.
        
        Args:
            image_path (str): Path to the image file to process
            
        Returns:
            List[Dict]: List of detected text elements, each containing:
                - text (str): The recognized text content
                - bbox (List[List[int]]): Bounding box coordinates [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                - confidence (float): Recognition confidence score (0.0-1.0)
                - center_y (int): Vertical center coordinate for spatial sorting
                - center_x (int): Horizontal center coordinate for spatial analysis
                
        Raises:
            ValueError: If image cannot be loaded or processed by PaddleOCR
            RuntimeError: If OCR processing fails
        """
        try:
            logging.info(f"🔍 Extracting text from image: {image_path}")
            
            # Run PaddleOCR using the predict() API (3.1.0 compatible)
            ocr_results = self.ocr.predict(input=image_path)
            
            if not ocr_results:
                logging.warning("⚠️ No text detected by PaddleOCR")
                return []
            
            text_elements = []
            
            # Process each result object from PaddleOCR 3.1.0
            for result_obj in ocr_results:
                # Extract data from the result object
                # PaddleOCR 3.1.0 returns result objects with structured data
                if hasattr(result_obj, 'json') and result_obj.json:
                    json_data = result_obj.json
                    # Extract detection results from the JSON structure
                    if 'ocr_res' in json_data:
                        for detection in json_data['ocr_res']:
                            # Extract bbox and text data
                            bbox = detection.get('bbox', [[0, 0], [0, 0], [0, 0], [0, 0]])
                            text = detection.get('text', '')
                            confidence = detection.get('score', 0.0)
                            
                            # Filter by confidence threshold
                            if confidence < self.min_confidence:
                                continue
                            
                            # Calculate center coordinates for spatial analysis
                            bbox_array = np.array(bbox)
                            center_x = int(np.mean(bbox_array[:, 0]))
                            center_y = int(np.mean(bbox_array[:, 1]))
                            
                            text_element = {
                                'text': text.strip(),
                                'bbox': bbox,
                                'confidence': confidence,
                                'center_x': center_x,
                                'center_y': center_y
                            }
                            
                            text_elements.append(text_element)
                            logging.debug(f"  📝 '{text}' (conf: {confidence:.2f}) at ({center_x}, {center_y})")
            
            # Sort by vertical position (top to bottom) for table processing
            text_elements.sort(key=lambda x: x['center_y'])
            
            logging.info(f"✅ Extracted {len(text_elements)} text elements with positions")
            return text_elements
            
        except Exception as e:
            logging.error(f"❌ Text extraction error: {e}")
            raise RuntimeError(f"Failed to extract text with PaddleOCR: {e}")
    
    def parse_mario_kart_table(self, text_elements: List[Dict], guild_id: int) -> List[Dict]:
        """
        Extract player names and scores from detected text elements.
        
        Analyzes the spatially-organized text elements to identify player names
        and their corresponding scores in Mario Kart results tables. Handles
        special cases like names with parentheses containing race counts and 
        spatial matching between names and scores.
        
        Args:
            text_elements (List[Dict]): Text elements with positions from PaddleOCR
            guild_id (int): Guild ID for player name resolution against roster
            
        Returns:
            List[Dict]: List of player results, each containing:
                - name (str): Resolved player name (from roster if available)
                - raw_name (str): Original detected name
                - score (int): Player's race score
                - races_played (int): Number of races played (from parentheses or default 12)
                - confidence (float): Detection confidence
                - is_roster_member (bool): Whether player is in guild roster
                - raw_line (str): Original text context for debugging
                
        Note:
            This method implements spatial matching logic to pair names with scores
            based on their vertical proximity in the table layout. It also extracts
            race counts from parentheses in player names.
        """
        try:
            logging.info("🏁 Parsing Mario Kart table data")
            
            # Separate text elements into potential names and scores
            potential_names = []
            potential_scores = []
            
            for element in text_elements:
                text = element['text']
                
                # Check if text looks like a score (1-180 range)
                if self._is_valid_score(text):
                    try:
                        score = int(re.search(r'\d+', text).group())
                        if self.score_range[0] <= score <= self.score_range[1]:
                            potential_scores.append({
                                'score': score,
                                'center_y': element['center_y'],
                                'center_x': element['center_x'],
                                'confidence': element['confidence']
                            })
                            continue
                    except (ValueError, AttributeError):
                        pass
                
                # Check if text looks like a player name and extract race count
                name_info = self._parse_player_name_with_races(text)
                if name_info:
                    potential_names.append({
                        'name': name_info['name'],
                        'races_played': name_info['races_played'],
                        'raw_text': text,
                        'center_y': element['center_y'],
                        'center_x': element['center_x'],
                        'confidence': element['confidence']
                    })
            
            logging.info(f"📊 Found {len(potential_names)} names, {len(potential_scores)} scores")
            
            # Match names with scores based on spatial proximity
            player_results = self._match_names_with_scores(potential_names, potential_scores, guild_id)
            
            logging.info(f"✅ Successfully parsed {len(player_results)} player results")
            return player_results
            
        except Exception as e:
            logging.error(f"❌ Table parsing error: {e}")
            return []
    
    def validate_results(self, results: List[Dict], guild_id: int) -> Dict:
        """
        Validate extracted results make sense for Mario Kart scoring.
        
        Performs comprehensive validation of extracted player results to ensure
        they conform to Mario Kart scoring rules and expected patterns. Provides
        detailed feedback about potential issues and data quality.
        
        Args:
            results (List[Dict]): List of extracted player results to validate
            guild_id (int): Guild ID for roster-specific validation
            
        Returns:
            Dict: Validation results containing:
                - is_valid (bool): Whether results pass basic validation
                - player_count (int): Number of players found
                - is_ideal_count (bool): Whether count matches expected (12 for 6v6)
                - warnings (List[str]): Non-critical issues found
                - errors (List[str]): Critical validation failures
                - needs_confirmation (bool): Whether user confirmation is recommended
                
        Note:
            Validation includes score range checking, duplicate detection,
            roster membership analysis, and race count validation.
        """
        validation = {
            'is_valid': True,
            'warnings': [],
            'errors': [],
            'player_count': len(results),
            'is_ideal_count': False,
            'needs_confirmation': False
        }
        
        player_count = len(results)
        ideal_count = config.TOTAL_IDEAL_PLAYERS  # Expected player count
        
        logging.info(f"🔍 Validating {player_count} player results")
        
        # Check player count
        if player_count == 0:
            validation['errors'].append("No players found in image")
            validation['is_valid'] = False
        elif player_count < config.MIN_TOTAL_PLAYERS:
            validation['errors'].append(f"Too few players: {player_count} (minimum {config.MIN_TOTAL_PLAYERS})")
            validation['is_valid'] = False
        elif player_count == ideal_count:
            validation['is_ideal_count'] = True
        elif player_count < ideal_count:
            validation['warnings'].append(f"Found {player_count} players (ideal: {ideal_count})")
            validation['needs_confirmation'] = True
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
        
        # Validate score ranges, race counts, and detect roster members
        roster_members = []
        non_roster = []
        race_count_variations = []
        
        for result in results:
            score = result.get('score', 0)
            races_played = result.get('races_played', 12)
            
            # Score range validation
            if not (self.score_range[0] <= score <= self.score_range[1]):
                validation['warnings'].append(
                    f"{result['name']}: Invalid score {score} (valid range: {self.score_range[0]}-{self.score_range[1]})"
                )
            
            # Track players with non-standard race counts
            if races_played != 12:
                race_count_variations.append(f"{result['name']} ({races_played} races)")
            
            # Track roster vs non-roster players
            if result.get('is_roster_member', False):
                roster_members.append(result['name'])
            else:
                non_roster.append(result.get('raw_name', result['name']))
        
        # Add informational messages about roster composition
        if roster_members:
            validation['warnings'].append(f"Roster members found: {', '.join(roster_members)}")
        if non_roster:
            validation['warnings'].append(f"Non-roster players detected: {', '.join(non_roster)}")
        if race_count_variations:
            validation['warnings'].append(f"Non-standard race counts: {', '.join(race_count_variations)}")
        
        logging.info(f"✅ Validation complete - Valid: {validation['is_valid']}")
        return validation
    
    def create_debug_overlay(self, image_path: str, text_elements: List[Dict]) -> str:
        """
        Create visual overlay for /runocr command debugging.
        
        Generates a debug image with color-coded bounding boxes around detected text
        elements, showing confidence scores and detection results. This is essential
        for troubleshooting OCR issues and understanding what the system detects.
        
        Args:
            image_path (str): Path to the original image
            text_elements (List[Dict]): Detected text elements with positions
            
        Returns:
            str: Path to the generated debug overlay image, or None if creation failed
            
        Note:
            Colors used in overlay:
            - Green: Valid scores (1-180 range)
            - Blue: Potential player names
            - Red: Other text elements
            - Text labels show content and confidence percentage
        """
        try:
            logging.info("🎨 Creating debug overlay for visual analysis")
            
            # Load original image
            img = cv2.imread(image_path)
            if img is None:
                logging.error(f"❌ Could not load image: {image_path}")
                return None
            
            # Color scheme for different text types
            colors = {
                'score': (0, 255, 0),      # Green for scores
                'name': (255, 0, 0),       # Blue for names  
                'other': (0, 0, 255)       # Red for other text
            }
            
            # Draw bounding boxes and labels for each text element
            for element in text_elements:
                text = element['text']
                confidence = element['confidence']
                bbox = element['bbox']
                
                # Determine text type for coloring
                if self._is_valid_score(text):
                    color = colors['score']
                    text_type = 'score'
                elif self._parse_player_name_with_races(text):
                    color = colors['name']
                    text_type = 'name'
                else:
                    color = colors['other']
                    text_type = 'other'
                
                # Convert bbox to rectangle coordinates
                bbox_array = np.array(bbox, dtype=np.int32)
                cv2.polylines(img, [bbox_array], True, color, 2)
                
                # Add text label with confidence
                label = f"{text} ({confidence:.1%})"
                label_pos = (int(bbox[0][0]), int(bbox[0][1]) - 5)
                
                # Ensure label is visible
                if label_pos[1] < 20:
                    label_pos = (label_pos[0], int(bbox[2][1]) + 20)
                
                cv2.putText(img, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, color, 1, cv2.LINE_AA)
            
            # Add legend
            legend_y = 30
            legend_items = [
                ("Scores (1-180)", colors['score']),
                ("Player Names", colors['name']),
                ("Other Text", colors['other'])
            ]
            
            for i, (label, color) in enumerate(legend_items):
                cv2.putText(img, label, (10, legend_y + i * 25), cv2.FONT_HERSHEY_SIMPLEX,
                           0.6, color, 2, cv2.LINE_AA)
            
            # Save debug overlay with timestamp
            timestamp = int(time.time())
            overlay_path = f"temp_paddle_debug_overlay_{timestamp}.png"
            
            success = cv2.imwrite(overlay_path, img)
            if success:
                logging.info(f"✅ Debug overlay created: {overlay_path}")
                return overlay_path
            else:
                logging.error("❌ Failed to save debug overlay")
                return None
                
        except Exception as e:
            logging.error(f"❌ Debug overlay creation error: {e}")
            return None
    
    # Private helper methods
    
    def _is_valid_score(self, text: str) -> bool:
        """
        Check if text represents a valid Mario Kart score.
        
        Validates that the text contains a number within the valid Mario Kart
        score range (1-180). Used to distinguish score values from other
        numeric text like race counts.
        
        Args:
            text (str): Text to validate as a score
            
        Returns:
            bool: True if text represents a valid Mario Kart score
        """
        if not text or not text.strip():
            return False
        
        # Look for numbers in the text
        number_match = re.search(r'\d+', text)
        if not number_match:
            return False
        
        try:
            score = int(number_match.group())
            return self.score_range[0] <= score <= self.score_range[1]
        except ValueError:
            return False
    
    def _parse_player_name_with_races(self, text: str) -> Optional[Dict]:
        """
        Parse player name and extract race count from parentheses.
        
        Handles player names like:
        - "Cynical" -> {'name': 'Cynical', 'races_played': 12}
        - "Corbs (5)" -> {'name': 'Corbs', 'races_played': 5}
        - "Stickman (7)" -> {'name': 'Stickman', 'races_played': 7}
        
        Args:
            text (str): Raw text that might contain a player name
            
        Returns:
            Optional[Dict]: Dictionary with 'name' and 'races_played' keys,
                           or None if text is not a valid player name
        """
        if not text or len(text.strip()) < 2:
            return None
        
        text = text.strip()
        
        # Must contain at least one letter
        if not re.search(r'[A-Za-z]', text):
            return None
        
        # Reject pure numbers
        if re.match(r'^\d+$', text):
            return None
        
        # Check for name with race count in parentheses: "Name (X)"
        parentheses_match = re.match(r'^(.+?)\s*\((\d+)\)$', text)
        if parentheses_match:
            name = parentheses_match.group(1).strip()
            try:
                races_played = int(parentheses_match.group(2))
                # Validate race count is reasonable (1-12 typically)
                if 1 <= races_played <= 12:
                    return {
                        'name': name,
                        'races_played': races_played
                    }
            except ValueError:
                pass
        
        # Regular name without parentheses - default to 12 races
        if re.match(r'^[A-Za-z0-9\s]+$', text):
            return {
                'name': text,
                'races_played': 12  # Default race count
            }
        
        return None
    
    def _match_names_with_scores(self, names: List[Dict], scores: List[Dict], guild_id: int) -> List[Dict]:
        """
        Match detected names with scores based on spatial proximity.
        
        Implements spatial matching algorithm to pair player names with their
        corresponding scores in the Mario Kart results table. Prioritizes
        vertical proximity with some horizontal weighting.
        
        Args:
            names (List[Dict]): Detected name elements with positions and race counts
            scores (List[Dict]): Detected score elements with positions
            guild_id (int): Guild ID for player name resolution
            
        Returns:
            List[Dict]: List of matched player results with names, scores, and race counts
        """
        try:
            results = []
            used_scores = set()
            
            # For each name, find the closest unused score
            for name_data in names:
                best_score = None
                best_distance = float('inf')
                
                for i, score_data in enumerate(scores):
                    if i in used_scores:
                        continue
                    
                    # Calculate spatial distance (primarily vertical)
                    vertical_distance = abs(name_data['center_y'] - score_data['center_y'])
                    horizontal_distance = abs(name_data['center_x'] - score_data['center_x']) * 0.1  # Weight horizontal less
                    
                    total_distance = vertical_distance + horizontal_distance
                    
                    if total_distance < best_distance:
                        best_distance = total_distance
                        best_score = (i, score_data)
                
                # If we found a reasonable match, add it to results
                if best_score and best_distance < 50:  # Reasonable proximity threshold
                    score_index, score_data = best_score
                    used_scores.add(score_index)
                    
                    # Resolve player name using database if available
                    raw_name = name_data['name']
                    resolved_name = raw_name
                    is_roster_member = False
                    
                    if self.db_manager:
                        try:
                            db_resolved = self.db_manager.resolve_player_name(raw_name, guild_id)
                            roster_players = self.db_manager.get_roster_players(guild_id)
                            if db_resolved and db_resolved in roster_players:
                                resolved_name = db_resolved
                                is_roster_member = True
                        except Exception as e:
                            logging.debug(f"Name resolution failed for '{raw_name}': {e}")
                    
                    result = {
                        'name': resolved_name,
                        'raw_name': raw_name,
                        'score': score_data['score'],
                        'races_played': name_data['races_played'],  # Include race count
                        'confidence': min(name_data['confidence'], score_data['confidence']),
                        'is_roster_member': is_roster_member,
                        'raw_line': f"{name_data['raw_text']} {score_data['score']}"  # Original context
                    }
                    
                    results.append(result)
                    logging.debug(f"  ✅ Matched '{raw_name}' with score {score_data['score']} ({name_data['races_played']} races)")
            
            logging.info(f"🎯 Successfully matched {len(results)} name-score pairs")
            return results
            
        except Exception as e:
            logging.error(f"❌ Name-score matching error: {e}")
            return []
    
    def process_split_regions_debug(self, image_path: str, guild_id: int = 0) -> Dict:
        """
        Process image with debug overlay for compatibility with runocr command.
        
        This method provides the same interface as the Tesseract OCR processor's
        process_split_regions_debug method, allowing seamless switching between
        OCR engines in the runocr command.
        
        Args:
            image_path (str): Path to the image file to process
            guild_id (int, optional): Guild ID for player name resolution. Defaults to 0.
            
        Returns:
            Dict: Processing results containing:
                - success (bool): Whether processing was successful
                - results (List[Dict]): List of player results with name, score, etc.
                - total_found (int): Number of players extracted
                - validation (Dict): Validation results and warnings
                - debug_overlay (str, optional): Path to debug overlay image
                - error (str, optional): Error message if processing failed
        """
        try:
            logging.info(f"🎯 PaddleOCR debug processing for runocr: {image_path}")
            
            # First, extract text elements with positions
            text_elements = self.extract_text_with_positions(image_path)
            
            if not text_elements:
                return {
                    'success': False,
                    'error': 'No text elements detected by PaddleOCR',
                    'results': [],
                    'total_found': 0
                }
            
            # Create debug overlay for visual analysis
            debug_overlay_path = self.create_debug_overlay(image_path, text_elements)
            
            # Process the main image for player results
            main_result = self.process_image(image_path, guild_id)
            
            # Combine results for runocr compatibility
            result = {
                'success': main_result.get('success', False),
                'results': main_result.get('results', []),
                'total_found': main_result.get('total_found', 0),
                'validation': main_result.get('validation', {}),
                'debug_overlay': debug_overlay_path,
                'engine': 'PaddleOCR 3.1.0',
                'text_elements_detected': len(text_elements)
            }
            
            if not main_result.get('success', False):
                result['error'] = main_result.get('error', 'Unknown processing error')
            
            logging.info(f"✅ PaddleOCR debug processing complete: {result['success']}")
            return result
            
        except Exception as e:
            logging.error(f"❌ PaddleOCR debug processing error: {e}")
            return {
                'success': False,
                'error': f'PaddleOCR processing failed: {str(e)}',
                'results': [],
                'total_found': 0,
                'engine': 'PaddleOCR 3.1.0'
            }