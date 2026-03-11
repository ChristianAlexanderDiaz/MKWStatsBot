#!/usr/bin/env python3
"""
OCR Processor for MKW Stats Bot
Based on working Discord bot PaddleOCR implementation
Enhanced with Railway-optimized resource management
"""

import asyncio
import gc
import logging
import os
import re
import threading
import traceback
from enum import Enum

# PaddleOCR imports
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw

# Enhanced resource management imports (optional - falls back gracefully)
try:
    from .ocr_config_manager import get_ocr_config
    from .ocr_performance_monitor import get_ocr_performance_monitor
    from .ocr_resource_manager import get_ocr_resource_manager
    RESOURCE_MANAGEMENT_AVAILABLE = True
except ImportError:
    RESOURCE_MANAGEMENT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.info("Resource management modules not available - using basic OCR processing")

# Thread lock for OCR operations (preserved for compatibility)
ocr_lock = threading.Lock()


def _is_race_count_token(stripped: str, patterns: list[re.Pattern]) -> bool:
    """Return True if token matches a race-count pattern like (5) or 5)."""
    for pattern in patterns:
        m = pattern.match(stripped)
        if m and 1 <= int(m.group(1)) <= 11:
            logging.debug(f"Skipping race count token '{stripped}' in score detection")
            return True
    return False

class TableFormat(Enum):
    """Enumeration of supported Mario Kart table formats."""
    LARGE = "large"
    MEDIUM = "medium"
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
    TableFormat.MEDIUM: {
        'name': 'Medium Format',
        'expected_width': 1290,
        'crop_coords': {
            'start_x': 434,
            'start_y': 84,
            'end_x': 796,
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

        # Initialize OCR sub-modules
        from .ocr import NameResolver, ScorePairer, TeamSplitter
        self.name_resolver = NameResolver(db_manager)
        self.score_pairer = ScorePairer()
        self.team_splitter = TeamSplitter(db_manager)

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

    def set_roster_data(self, guild_id: int, roster_data: list[dict]) -> None:
        """Inject pre-fetched roster data into OCR sub-modules for a specific guild.

        Call this from async context BEFORE dispatching sync work to an
        executor so that NameResolver and TeamSplitter can operate without
        making database calls.
        """
        self.name_resolver.set_roster_data(guild_id, roster_data)
        self.team_splitter.set_roster_data(guild_id, roster_data)

    def _initialize_ocr(self):
        """Initialize PaddleOCR with optimized settings."""
        try:
            logging.info("🚀 Initializing PaddleOCR with memory-optimized settings...")

            # Memory-optimized PaddleOCR settings (from working Discord bot)
            # Try different parameter combinations for compatibility with different PaddleOCR versions

            # Try full Railway configuration first
            try:
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
                logging.info("✅ PaddleOCR initialized (full config)")
                return
            except TypeError:
                pass  # Try next configuration

            # Try without show_log (older versions)
            try:
                self.ocr = PaddleOCR(
                    use_angle_cls=False,
                    lang='en',
                    use_gpu=False,
                    det_model_dir=None,
                    rec_model_dir=None,
                    cls_model_dir=None,
                    use_space_char=True
                )
                logging.info("✅ PaddleOCR initialized (no show_log)")
                return
            except TypeError:
                pass  # Try next configuration

            # Try minimal configuration (maximum compatibility)
            self.ocr = PaddleOCR(
                use_angle_cls=False,
                lang='en',
                use_gpu=False
            )
            logging.info("✅ PaddleOCR initialized (minimal config)")

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

    def process_image(self, image_path: str, message_timestamp=None, guild_id: int = 0, roster_data: list[dict] | None = None) -> dict:
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
                    bbox = item.get("bbox", None)

                    # Filter out junk - keep only characters, numbers, spaces, punctuation, parentheses
                    if text and re.match(r'^[a-zA-Z0-9\s.,\-+%$()]+$', text):
                        extracted_texts.append({
                            'text': text,
                            'confidence': confidence,
                            'bbox': bbox
                        })

            if not extracted_texts:
                return {
                    'success': False,
                    'error': 'No valid text found in image after filtering',
                    'results': []
                }

            # Parse Mario Kart results
            parsed_results = self._parse_mario_kart_results(extracted_texts, guild_id, roster_data=roster_data)

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
                                 message_timestamp=None) -> dict:
        """
        Async process image with resource management and priority allocation.
        Falls back to sync processing if resource management is unavailable.

        Pre-fetches roster data before entering the executor so that sync
        OCR sub-modules (NameResolver, TeamSplitter) can work without DB calls.
        """
        # Pre-fetch roster data for sync sub-modules (async DB -> sync executor)
        roster_data: list[dict] = []
        if self.db_manager and hasattr(self.db_manager, 'players'):
            try:
                roster_data = await self.db_manager.players.get_all_players_stats(guild_id) or []
            except Exception as e:
                logging.warning(f"Failed to pre-fetch roster data: {e}")
                roster_data = []

        if not self.resource_management_enabled:
            # Fallback: run sync processing in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self.process_image, image_path, message_timestamp, guild_id, roster_data
            )

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
            ):

                # Acquire resources with priority allocation
                async with self.resource_manager.acquire_resources(request) as context:
                    self.performance_monitor.mark_operation_started(request.request_id)

                    # Perform OCR processing in executor to avoid blocking
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None,
                        self.process_image,
                        image_path,
                        message_timestamp,
                        guild_id,
                        roster_data
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
            # Fallback: run sync processing in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self.process_image, image_path, message_timestamp, guild_id, roster_data
            )

    async def process_bulk_images_async(self, image_data_list: list[dict], guild_id: int,
                                       user_id: int) -> list[dict]:
        """
        Process multiple images with intelligent batching and resource management.
        Falls back to individual sync processing if resource management is unavailable.

        Pre-fetches roster data once before processing any images so that sync
        OCR sub-modules can work without DB calls.
        """
        # Pre-fetch roster data for sync sub-modules (async DB -> sync executor)
        roster_data: list[dict] = []
        if self.db_manager and hasattr(self.db_manager, 'players'):
            try:
                roster_data = await self.db_manager.players.get_all_players_stats(guild_id) or []
            except Exception as e:
                logging.warning(f"Failed to pre-fetch roster data for bulk processing: {e}")
                roster_data = []

        if not self.resource_management_enabled:
            # Fallback: run sync processing in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            results = []
            for image_data in image_data_list:
                result = await loop.run_in_executor(
                    None, self.process_image,
                    image_data['path'], image_data.get('timestamp'), guild_id, roster_data
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
            ):

                # Acquire resources with priority allocation
                async with self.resource_manager.acquire_resources(request):
                    self.performance_monitor.mark_operation_started(request.request_id)

                    # Process images based on batch size configuration
                    batch_size = getattr(self.config_manager.config, 'batch_size', 3)
                    results = []

                    for i in range(0, image_count, batch_size):
                        batch = image_data_list[i:i + batch_size]

                        # Process batch in executor
                        loop = asyncio.get_running_loop()
                        batch_tasks = []

                        for image_data in batch:
                            task = loop.run_in_executor(
                                None,
                                self.process_image,
                                image_data['path'],
                                image_data.get('timestamp'),
                                guild_id,
                                roster_data
                            )
                            batch_tasks.append(task)

                        # Wait for batch completion
                        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                        # Handle any exceptions in batch results
                        for _j, result in enumerate(batch_results):
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
            # Fallback to individual processing off the event loop
            results = []
            for image_data in image_data_list:
                try:
                    result = await asyncio.to_thread(
                        self.process_image,
                        image_data['path'],
                        image_data.get('timestamp'),
                        guild_id,
                        roster_data,
                    )
                    results.append(result)
                except Exception as individual_error:
                    results.append({
                        'success': False,
                        'error': str(individual_error),
                        'results': []
                    })
            return results

    def get_performance_stats(self) -> dict:
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

    @staticmethod
    def _build_token_bboxes(extracted_texts: list[dict], tokens: list[str]) -> dict[int, list]:
        """Map each token index to the bounding box of its source OCR line."""
        token_bboxes: dict[int, list] = {}
        token_idx = 0
        for item in extracted_texts:
            item_tokens = item['text'].split()
            bbox = item.get('bbox')
            for _ in item_tokens:
                if token_idx < len(tokens) and bbox:
                    token_bboxes[token_idx] = bbox
                token_idx += 1
        return token_bboxes

    @staticmethod
    def _find_score_positions(tokens: list[str]) -> list[int]:
        """Identify token indices that represent valid scores (1-180)."""
        from .ocr import extract_score_from_corrupted_token

        race_count_patterns = [
            re.compile(r'^\((\d+)\)$'),
            re.compile(r'^\((\d+)$'),
            re.compile(r'^(\d+)\)$'),
        ]
        score_positions: list[int] = []

        for i, token in enumerate(tokens):
            stripped = token.strip()
            if _is_race_count_token(stripped, race_count_patterns):
                continue

            if token.isdigit() and 1 <= int(token) <= 180:
                score_positions.append(i)
                logging.debug(f"Found score: {token} at position {i}")
                continue

            # Embedded scores in corrupted tokens (e.g. "RIC69")
            # Only if NOT followed by a valid standalone score
            if i < len(tokens) - 1 and tokens[i + 1].isdigit() and 1 <= int(tokens[i + 1]) <= 180:
                logging.debug(f"Skipping potential embedded score in '{token}' because followed by valid score '{tokens[i + 1]}'")
                continue

            embedded_score = extract_score_from_corrupted_token(token)
            if embedded_score:
                score_positions.append(i)
                logging.debug(f"Found embedded score: {embedded_score} in token '{token}' at position {i}")

        return score_positions

    def _parse_mario_kart_results(self, extracted_texts: list[dict], guild_id: int = 0, roster_data: list[dict] | None = None) -> list[dict]:
        """Parse extracted text to find Mario Kart player results using database validation."""
        try:
            if not self.db_manager:
                logging.error("No database manager available for player validation")
                return []

            if roster_data is not None:
                self.name_resolver.set_roster_data(guild_id, roster_data)
                self.team_splitter.set_roster_data(guild_id, roster_data)

            combined_text = ' '.join([item['text'] for item in extracted_texts])
            tokens = combined_text.split()
            token_bboxes = self._build_token_bboxes(extracted_texts, tokens)

            logging.debug(f"OCR tokens: {tokens}")

            score_positions = self._find_score_positions(tokens)
            valid_names = self.name_resolver.find_valid_names_with_window(tokens, guild_id)
            results = self.score_pairer.pair_names_with_scores(valid_names, score_positions, tokens, token_bboxes)

            all_detected_scores = len(score_positions)
            guild_players_found = len(results)

            if 11 <= all_detected_scores <= 20:
                logging.debug(f"Team Split Detection: {all_detected_scores} players, {guild_players_found} guild members")
                results = self.team_splitter.apply_dynamic_team_splitting(results, tokens, guild_id, all_detected_scores)
                guild_players_found = len(results)

            opponent_players = all_detected_scores - guild_players_found
            logging.info(f"OCR Results: {guild_players_found} guild players found, {opponent_players} opponent players detected")

            if results:
                team_summary = ", ".join([f"{result['name']} {result['score']}" for result in results])
                logging.info(f"Your team: {team_summary}")

            return results

        except Exception as e:
            logging.error(f"Error parsing Mario Kart results: {e}")
            return []

    # ------------------------------------------------------------------
    # Backward-compat stubs – implementations live in ocr/ sub-modules
    # ------------------------------------------------------------------

    def _apply_6v6_team_splitting(self, guild_results: list[dict], tokens: list[str], guild_id: int) -> list[dict]:
        """Delegate to TeamSplitter.apply_6v6_team_splitting."""
        return self.team_splitter.apply_6v6_team_splitting(guild_results, tokens, guild_id)

    def _apply_dynamic_team_splitting(
        self, guild_results: list[dict], tokens: list[str], guild_id: int, total_players: int
    ) -> list[dict]:
        """Delegate to TeamSplitter.apply_dynamic_team_splitting."""
        return self.team_splitter.apply_dynamic_team_splitting(guild_results, tokens, guild_id, total_players)

    def _map_guild_positions(self, guild_results: list[dict], all_players: list[tuple]) -> dict[str, int]:
        """Delegate to TeamSplitter.map_guild_positions."""
        return self.team_splitter.map_guild_positions(guild_results, all_players)

    def _extract_all_players_from_tokens(self, tokens: list[str], guild_id: int = 0) -> list[tuple]:
        """Delegate to TeamSplitter.extract_all_players_from_tokens."""
        return self.team_splitter.extract_all_players_from_tokens(tokens, guild_id)

    def _find_valid_names_with_window(self, tokens: list[str], guild_id: int) -> list[tuple]:
        """Delegate to NameResolver.find_valid_names_with_window."""
        return self.name_resolver.find_valid_names_with_window(tokens, guild_id)

    def _find_guild_name_in_substring(self, corrupted_token: str, guild_id: int) -> tuple:
        """Delegate to NameResolver.find_guild_name_in_substring."""
        return self.name_resolver.find_guild_name_in_substring(corrupted_token, guild_id)

    def _extract_score_from_corrupted_token(self, token: str) -> int | None:
        """Delegate to module-level extract_score_from_corrupted_token."""
        from .ocr import extract_score_from_corrupted_token
        return extract_score_from_corrupted_token(token)

    def _pair_names_with_scores(
        self, valid_names: list[tuple], score_positions: list[int],
        tokens: list[str], token_bboxes: dict[int, list] | None = None
    ) -> list[dict]:
        """Delegate to ScorePairer.pair_names_with_scores."""
        return self.score_pairer.pair_names_with_scores(valid_names, score_positions, tokens, token_bboxes)

    def _get_bbox_center_x(self, bbox: list) -> float:
        """Delegate to ScorePairer.get_bbox_center_x."""
        return self.score_pairer.get_bbox_center_x(bbox)

    def _get_bbox_center_y(self, bbox: list) -> float:
        """Delegate to ScorePairer.get_bbox_center_y."""
        return self.score_pairer.get_bbox_center_y(bbox)

    def _validate_results(self, results: list[dict], guild_id: int = 0) -> dict:
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
            duplicates = {name for name in names if names.count(name) > 1}
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

    def _create_default_war_metadata(self, message_timestamp=None) -> dict:
        """Create default war metadata."""
        try:
            from . import config
            default_race_count = getattr(config, 'DEFAULT_RACE_COUNT', 12)
        except Exception:
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

    def create_debug_overlay(self, image_path: str) -> str | None:
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
                for _i, result in enumerate(ocr_result["results"]):
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

