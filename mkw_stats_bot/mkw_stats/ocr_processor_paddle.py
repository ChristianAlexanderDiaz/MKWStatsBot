#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaddleOCR Processor for MKW Stats Bot
Railway/Linux compatible implementation based on working Windows code
"""
import os
import logging
import numpy as np
import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from PIL import Image, ImageDraw

# PaddleOCR imports - lazy loaded to avoid startup crashes

class PaddleOCRProcessor:
    """PaddleOCR processor for Mario Kart race result images."""
    
    # Hardcoded ROI coordinates for Mario Kart table region
    DEFAULT_ROI_COORDS = [567, 96, 1068, 1012]  # [x1, y1, x2, y2]
    
    def __init__(self, db_manager=None):
        """Initialize PaddleOCR processor."""
        self.db_manager = db_manager
        
        # Setup Railway/Linux environment optimizations
        self._setup_environment()
        
        # Initialize PaddleOCR with working settings
        self.ocr = None
        self._initialize_ocr()
    
    def _setup_environment(self):
        """Setup environment for Railway/Linux deployment."""
        # Set PaddleOCR to use faster model downloads
        os.environ['PADDLE_PDX_MODEL_SOURCE'] = 'BOS'
        
        # Force OpenCV to use headless mode (Railway/Docker compatibility)
        os.environ['OPENCV_IO_ENABLE_JASPER'] = 'false'
        os.environ['OPENCV_IO_ENABLE_OPENEXR'] = 'false'
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        
        # Railway/Docker aggressive headless fixes
        os.environ['DISPLAY'] = ''
        os.environ['MPLBACKEND'] = 'Agg'
        
        # Create output directory if needed
        Path("output").mkdir(exist_ok=True)
        
        # Try to fix OpenCV conflicts at runtime
        self._fix_opencv_conflicts()
        
        logging.info("🚀 PaddleOCR environment configured for Railway/Linux")
    
    def _fix_opencv_conflicts(self):
        """Aggressively fix OpenCV conflicts for Railway deployment."""
        try:
            import subprocess
            import sys
            
            logging.info("🔧 Checking OpenCV installation status...")
            
            # First, try to import cv2 to see if it works
            cv2_working = False
            try:
                import cv2
                cv2_working = True
                logging.info(f"✅ OpenCV already working - Version: {cv2.__version__}")
                return  # If it works, don't mess with it
            except ImportError:
                logging.warning("❌ OpenCV not available - checking packages...")
            except Exception as e:
                logging.warning(f"❌ OpenCV import error: {e} - checking packages...")
            
            # Check what's installed
            opencv_packages = ['opencv-python', 'opencv-contrib-python']
            headless_packages = ['opencv-python-headless', 'opencv-contrib-python-headless']
            
            conflicts_found = []
            headless_found = []
            
            for package in opencv_packages:
                try:
                    result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        conflicts_found.append(package)
                        logging.info(f"Found GUI package: {package}")
                except:
                    pass
            
            for package in headless_packages:
                try:
                    result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        headless_found.append(package)
                        logging.info(f"Found headless package: {package}")
                except:
                    pass
            
            # If no OpenCV at all, install headless
            if not conflicts_found and not headless_found:
                logging.info("📦 No OpenCV found - installing headless version...")
                try:
                    result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'opencv-contrib-python-headless>=4.5.0'], 
                                          capture_output=True, text=True, timeout=120)
                    if result.returncode == 0:
                        logging.info("✅ Successfully installed opencv-contrib-python-headless")
                    else:
                        logging.error(f"Failed to install headless OpenCV: {result.stderr}")
                except Exception as e:
                    logging.error(f"Failed to install headless OpenCV: {e}")
            
            # If conflicts exist but headless also exists, prefer headless
            elif conflicts_found and headless_found:
                logging.warning(f"⚠️ Both GUI {conflicts_found} and headless {headless_found} packages found")
                logging.info("🔧 Removing GUI packages to prevent libGL.so.1 errors...")
                
                for package in conflicts_found:
                    try:
                        logging.info(f"🗑️ Removing {package}...")
                        result = subprocess.run([sys.executable, '-m', 'pip', 'uninstall', package, '-y'], 
                                               capture_output=True, text=True, timeout=60)
                        if result.returncode == 0:
                            logging.info(f"✅ Successfully removed {package}")
                    except Exception as e:
                        logging.warning(f"Failed to remove {package}: {e}")
            
            # If only conflicts found, replace with headless
            elif conflicts_found and not headless_found:
                logging.warning(f"⚠️ Found GUI packages {conflicts_found} that will cause libGL.so.1 errors")
                logging.info("🔧 Replacing with headless version...")
                
                # Remove GUI packages first
                for package in conflicts_found:
                    try:
                        logging.info(f"🗑️ Removing {package}...")
                        subprocess.run([sys.executable, '-m', 'pip', 'uninstall', package, '-y'], 
                                     capture_output=True, text=True, timeout=60)
                    except Exception as e:
                        logging.warning(f"Failed to remove {package}: {e}")
                
                # Install headless version
                try:
                    logging.info("📦 Installing opencv-contrib-python-headless...")
                    result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'opencv-contrib-python-headless>=4.5.0'], 
                                          capture_output=True, text=True, timeout=120)
                    if result.returncode == 0:
                        logging.info("✅ Successfully installed opencv-contrib-python-headless")
                    else:
                        logging.error(f"Failed to install headless OpenCV: {result.stderr}")
                except Exception as e:
                    logging.error(f"Failed to install headless OpenCV: {e}")
            
            # Final verification
            try:
                import cv2
                logging.info(f"✅ OpenCV verification successful - Version: {cv2.__version__}")
            except ImportError:
                logging.error("❌ OpenCV still not available after fix attempt")
                raise ImportError("OpenCV not available - Railway deployment may need manual intervention")
            except Exception as e:
                logging.error(f"❌ OpenCV verification failed: {e}")
                
        except Exception as e:
            logging.warning(f"OpenCV conflict check failed: {e}")
            # Don't raise - let the main process continue but log the issue
    
    def _verify_opencv_installation(self):
        """Verify OpenCV installation and log detailed information."""
        try:
            import cv2
            import subprocess
            import sys
            
            logging.info(f"✅ OpenCV imported successfully - Version: {cv2.__version__}")
            
            # Check which OpenCV packages are installed
            opencv_packages = [
                'opencv-python',
                'opencv-python-headless', 
                'opencv-contrib-python',
                'opencv-contrib-python-headless'
            ]
            
            installed_packages = []
            for package in opencv_packages:
                try:
                    result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        lines = result.stdout.split('\n')
                        version = next((line for line in lines if line.startswith('Version:')), 'Version: Unknown')
                        installed_packages.append(f"{package} ({version.replace('Version: ', '')})")
                except:
                    pass
            
            if installed_packages:
                logging.info(f"📦 Installed OpenCV packages: {', '.join(installed_packages)}")
            else:
                logging.warning("⚠️ No OpenCV packages found via pip")
            
            # Test basic OpenCV functionality
            import numpy as np
            test_image = np.zeros((10, 10, 3), dtype=np.uint8)
            _ = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)  # Test color conversion
            logging.info("✅ OpenCV basic functionality test passed")
            
        except ImportError as e:
            logging.error(f"❌ OpenCV import failed: {e}")
            raise
        except Exception as e:
            logging.warning(f"⚠️ OpenCV verification warning: {e}")
            # Don't raise, just warn - OpenCV might still work
    
    def _initialize_ocr(self):
        """Initialize PaddleOCR with WORKING configuration (lazy loaded)."""
        try:
            logging.info("🚀 Lazy loading PaddleOCR - importing now...")
            
            # First, verify OpenCV installation
            self._verify_opencv_installation()
            
            # Lazy import PaddleOCR only when actually needed
            from paddleocr import PaddleOCR
            
            logging.info("🚀 Using the WORKING OCR configuration...")
            
            self.ocr = PaddleOCR(
                lang='en',                           # English preprocessing
                ocr_version='PP-OCRv5',             # Latest version
                text_det_limit_side_len=1080,       # High resolution processing
                text_det_limit_type='max',          # Limit maximum side
                text_det_thresh=0.2,                # Lower detection threshold
                use_textline_orientation=False,      # Disabled for cleaner results
                use_doc_orientation_classify=False,   # Disable document orientation classification
                use_doc_unwarping=False             # Disable document unwarping
            )
            
            logging.info("✅ PaddleOCR initialized successfully with working configuration")
            
        except ImportError as e:
            logging.error(f"❌ Failed to import PaddleOCR: {e}")
            logging.error("💡 This might indicate missing dependencies or memory issues")
            raise
        except Exception as e:
            logging.error(f"❌ Failed to initialize PaddleOCR: {e}")
            logging.error("💡 This might indicate insufficient memory or model download issues")
            raise
    
    def process_image(self, image_path: str, message_timestamp=None, guild_id: int = 0) -> Dict:
        """Process image using PaddleOCR with ROI extension (based on working Windows code)."""
        try:
            # Ensure PaddleOCR is initialized (lazy loading)
            if self.ocr is None:
                self._initialize_ocr()
            logging.info(f"🧪 Testing PaddleOCR with: {image_path}")
            
            if not os.path.exists(image_path):
                logging.error(f"❌ File not found: {image_path}")
                return {
                    'success': False,
                    'error': f'Image file not found: {image_path}',
                    'results': []
                }
            
            # Prepare image input with ROI extension
            with Image.open(image_path) as img:
                orig_width, orig_height = img.size
                logging.info(f"📏 Original image size: {orig_width} x {orig_height} pixels")
                
                # Use hardcoded ROI coordinates
                x1, y1, x2, y2 = self.DEFAULT_ROI_COORDS
                
                # ⭐ EXTEND ROI TO BOTTOM OF IMAGE (creates vertical "channels")
                y2_extended = orig_height  # Extend to full image height
                logging.info(f"📏 Original ROI: ({x1}, {y1}) to ({x2}, {y2})")
                logging.info(f"📏 Extended ROI: ({x1}, {y1}) to ({x2}, {y2_extended}) - extended downward")
                
                roi_image = img.crop((x1, y1, x2, y2_extended))
                logging.info(f"✂️ Cropped to extended ROI: {x2-x1} x {y2_extended-y1} pixels")
                
                if roi_image.mode != 'RGB':
                    roi_image = roi_image.convert('RGB')
                
                roi_image.save("debug_roi.png")
                logging.info("💾 Saved ROI as debug_roi.png")
                image_input = np.array(roi_image)
            
            # Run PaddleOCR prediction
            result = self.ocr.predict(input=image_input)
            
            if not result:
                logging.error("❌ No OCR results")
                return {
                    'success': False,
                    'error': 'No OCR results returned',
                    'results': []
                }
            
            # Extract and filter results (based on working Windows code)
            extracted_data = self._extract_and_filter_results(result)
            
            if not extracted_data['texts']:
                return {
                    'success': False,
                    'error': 'No valid text found in image after filtering',
                    'results': []
                }
            
            # Parse Mario Kart results
            parsed_results = self._parse_mario_kart_results(extracted_data, guild_id)
            
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
            
            # Validate results using built-in validation
            validation_result = self._validate_results(parsed_results, guild_id)
            
            logging.info("🎉 SUCCESS! PaddleOCR processing completed!")
            
            return {
                'success': True,
                'results': parsed_results,
                'total_found': len(parsed_results),
                'war_metadata': war_metadata,
                'validation': validation_result,
                'processing_engine': 'PaddleOCR'
            }
            
        except Exception as e:
            logging.error(f"❌ PaddleOCR processing error: {e}")
            return {
                'success': False,
                'error': f'PaddleOCR processing failed: {str(e)}',
                'results': []
            }
    
    def _extract_and_filter_results(self, result) -> Dict:
        """Extract and filter OCR results (based on working Windows code)."""
        try:
            # Extract results
            result_data = result[0].res if hasattr(result[0], 'res') else result[0]
            texts = result_data['rec_texts']
            scores = result_data['rec_scores']
            boxes = result_data['rec_polys']
            
            # ⭐ FILTER OUT JUNK - Keep only characters, numbers, and parentheses
            filtered_texts = []
            filtered_scores = []
            filtered_boxes = []
            
            for i, (text, score, box) in enumerate(zip(texts, scores, boxes)):
                text_clean = text.strip()
                
                # Only keep text that contains ONLY: letters, numbers, spaces, punctuation, parentheses
                # FIXED: Complete the regex pattern that was broken in original code
                if (text_clean and  # Exclude empty strings
                    re.match(r'^[a-zA-Z0-9\s.,\-+%$()]+$', text_clean)):  # Characters, numbers, parentheses only
                    
                    filtered_texts.append(text_clean)
                    filtered_scores.append(score)
                    filtered_boxes.append(box)
            
            # Use filtered data for display
            texts = filtered_texts
            scores = filtered_scores
            
            logging.info(f"📊 OCR RESULTS ({len(texts)} items found):")
            logging.info("=" * 60)
            
            # Display all results
            for i, (text, score) in enumerate(zip(texts, scores), 1):
                confidence_percent = score * 100
                confidence_indicator = "🟢" if score > 0.9 else "🟡" if score > 0.7 else "🔴"
                logging.info(f"{i:2d}. {confidence_indicator} '{text}' - {confidence_percent:.1f}%")
            
            # Extract just the numbers
            numbers_only = []
            for i, (text, score) in enumerate(zip(texts, scores)):
                # FIXED: Complete the regex pattern that was broken in original code
                if re.match(r'^[\d\s.,\-+%$]+$', text.strip()):
                    numbers_only.append({
                        'position': i + 1,
                        'number': text.strip(),
                        'confidence': score * 100
                    })
            
            if numbers_only:
                logging.info(f"🔢 EXTRACTED NUMBERS ({len(numbers_only)} items):")
                logging.info("-" * 40)
                for item in numbers_only:
                    quality = "🟢 HIGH" if item['confidence'] > 90 else "🟡 MED" if item['confidence'] > 70 else "🔴 LOW"
                    logging.info(f"   Position #{item['position']}: {item['number']} - {quality} ({item['confidence']:.1f}%)")
            
            return {
                'texts': filtered_texts,
                'scores': filtered_scores,  
                'boxes': filtered_boxes
            }
            
        except Exception as e:
            logging.error(f"Error extracting OCR results: {e}")
            return {'texts': [], 'scores': [], 'boxes': []}
    
    def _parse_mario_kart_results(self, extracted_data: Dict, guild_id: int = 0) -> List[Dict]:
        """Parse extracted text to find Mario Kart player results."""
        try:
            results = []
            texts = extracted_data['texts']
            
            # Get current roster from database for nickname resolution
            roster_players = self.db_manager.get_roster_players(guild_id) if self.db_manager else []
            
            # Create single text string for processing
            combined_text = '\n'.join(texts)
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
                                'preset_used': 'paddle_ocr_roi',
                                'confidence': 0.9 if is_roster_member else 0.7,
                                'is_roster_member': is_roster_member
                            })
                            break  # Only take first valid name per line
            
            return results
            
        except Exception as e:
            logging.error(f"Error parsing Mario Kart results: {e}")
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
            logging.error(f"Error during validation: {e}")
            return {
                'is_valid': False,
                'errors': [f"Validation failed: {str(e)}"],
                'warnings': []
            }
    
    def _create_default_war_metadata(self, message_timestamp=None) -> Dict:
        """Create default war metadata."""
        from . import config
        
        metadata = {
            'date': None,
            'time': None, 
            'race_count': config.DEFAULT_RACE_COUNT,
            'war_type': '6v6',
            'notes': 'Auto-processed with PaddleOCR'
        }
        
        # Use message timestamp as primary source for date/time
        if message_timestamp:
            metadata['date'] = message_timestamp.strftime('%Y-%m-%d')
            metadata['time'] = message_timestamp.strftime('%H:%M:%S')
        
        return metadata
    
    def create_debug_overlay(self, image_path: str) -> str:
        """Create debug overlay showing PaddleOCR detection results (based on working Windows code)."""
        try:
            logging.info("🎨 Creating visualization...")
            
            # Load original image
            image = Image.open(image_path).convert('RGB')
            _, orig_height = image.size  # Only need height for ROI extension
            draw = ImageDraw.Draw(image)
            
            # Get extended ROI coordinates and draw ROI boundary
            x1, y1, x2, y2 = self.DEFAULT_ROI_COORDS
            y2_extended = orig_height
            
            # Draw ROI boundaries
            draw.rectangle([x1, y1, x2, y2], outline="yellow", width=3)
            draw.text((x1, y1-20), "Original ROI", fill="yellow")
            
            if y2_extended != y2:
                draw.rectangle([x1, y2, x2, y2_extended], outline="orange", width=2)
                draw.text((x1, y2+5), "Extended to Bottom", fill="orange")
            
            # Process ROI and get detection results
            roi_image = image.crop((x1, y1, x2, y2_extended))
            if roi_image.mode != 'RGB':
                roi_image = roi_image.convert('RGB')
            
            # Run OCR on ROI
            image_input = np.array(roi_image)
            result = self.ocr.predict(input=image_input)
            
            if result:
                result_data = result[0].res if hasattr(result[0], 'res') else result[0]
                texts = result_data['rec_texts']
                scores = result_data['rec_scores']
                boxes = result_data['rec_polys']
                
                # Draw detection boxes (adjust coordinates back to original image)
                for i, (box, text, _) in enumerate(zip(boxes, texts, scores)):
                    # Convert box to rectangle
                    x_coords = box[:, 0]
                    y_coords = box[:, 1]
                    box_x1, box_y1 = int(min(x_coords)) + x1, int(min(y_coords)) + y1
                    box_x2, box_y2 = int(max(x_coords)) + x1, int(max(y_coords)) + y1
                    
                    # Color based on content type (from working Windows code)
                    if re.match(r'^[\d\s.,\-+%$]+$', text.strip()):
                        color = "blue"  # Numbers in blue
                    else:
                        color = "green"  # Names in green
                    
                    draw.rectangle([box_x1, box_y1, box_x2, box_y2], outline=color, width=2)
                    
                    # Draw text label
                    label = f"{text}"
                    try:
                        draw.text((box_x1, box_y1-20), label, fill=color)
                    except:
                        draw.text((box_x1, box_y1-20), label, fill=color)
            
            # Add legend
            legend_items = [
                ("Original ROI", "yellow"),
                ("Extended ROI", "orange"), 
                ("Names", "green"),
                ("Numbers", "blue")
            ]
            
            for i, (text, color) in enumerate(legend_items):
                draw.text((10, 30 + i * 25), text, fill=color)
            
            # Save visualization (based on working Windows code)
            output_name = Path(image_path).stem
            visual_path = f"output/{output_name}_paddle_results.jpg"
            image.save(visual_path)
            logging.info(f"📊 PaddleOCR visualization saved: {visual_path}")
            return visual_path
            
        except Exception as e:
            logging.error(f"Error creating PaddleOCR debug overlay: {e}")
            return None