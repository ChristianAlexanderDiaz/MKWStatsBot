#!/usr/bin/env python3
import cv2
import json
import sys
import os
from ocr_processor import OCRProcessor
import config

class RegionSelector:
    def __init__(self, image_path):
        self.image_path = image_path
        self.image = cv2.imread(image_path)
        if self.image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        self.original_image = self.image.copy()
        self.regions = []
        self.current_region = None
        self.drawing = False
        self.ocr = OCRProcessor()
        
        # Window settings
        self.window_name = "Mario Kart Region Selector"
        
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events for region selection."""
        
        if event == cv2.EVENT_LBUTTONDOWN:
            # Start drawing rectangle
            self.drawing = True
            self.current_region = [(x, y), (x, y)]
            
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                # Update rectangle end point
                self.current_region[1] = (x, y)
                self.draw_regions()
                
        elif event == cv2.EVENT_LBUTTONUP:
            # Finish drawing rectangle
            self.drawing = False
            if self.current_region:
                # Only add if rectangle has some size
                start_x, start_y = self.current_region[0]
                end_x, end_y = self.current_region[1]
                if abs(end_x - start_x) > 10 and abs(end_y - start_y) > 10:
                    # Normalize coordinates (top-left, bottom-right)
                    x1, x2 = min(start_x, end_x), max(start_x, end_x)
                    y1, y2 = min(start_y, end_y), max(start_y, end_y)
                    self.regions.append(((x1, y1), (x2, y2)))
                    print(f"✅ Added region {len(self.regions)}: ({x1}, {y1}) to ({x2}, {y2})")
                self.current_region = None
                self.draw_regions()
    
    def draw_regions(self):
        """Draw all regions on the image."""
        # Start with original image
        self.image = self.original_image.copy()
        
        # Draw saved regions in green
        for i, (start, end) in enumerate(self.regions):
            cv2.rectangle(self.image, start, end, (0, 255, 0), 2)
            # Add region number
            cv2.putText(self.image, f"#{i+1}", 
                       (start[0], start[1] - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Draw current region being drawn in blue
        if self.current_region and self.drawing:
            cv2.rectangle(self.image, self.current_region[0], self.current_region[1], (255, 0, 0), 2)
        
        cv2.imshow(self.window_name, self.image)
    
    def run_interactive_selection(self):
        """Run the interactive region selection."""
        print("🖱️  Mario Kart Region Selector")
        print("=" * 50)
        print("Instructions:")
        print("• Click and drag to select player data regions")
        print("• Press 't' to test OCR on selected regions")
        print("• Press 'c' to clear all regions")
        print("• Press 'u' to undo last region")
        print("• Press 's' to save regions to file")
        print("• Press 'l' to load regions from file")
        print("• Press 'q' to quit")
        print("=" * 50)
        
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)
        
        # Initial display
        self.draw_regions()
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord('c'):
                # Clear all regions
                self.regions = []
                print("🧹 Cleared all regions")
                self.draw_regions()
            elif key == ord('u'):
                # Undo last region
                if self.regions:
                    removed = self.regions.pop()
                    print(f"↩️  Removed region: {removed}")
                    self.draw_regions()
            elif key == ord('t'):
                # Test OCR on selected regions
                self.test_ocr_on_regions()
            elif key == ord('s'):
                # Save regions
                self.save_regions()
            elif key == ord('l'):
                # Load regions
                self.load_regions()
        
        cv2.destroyAllWindows()
        return self.regions
    
    def test_ocr_on_regions(self):
        """Test OCR on all selected regions with visual feedback."""
        if not self.regions:
            print("❌ No regions selected!")
            return
        
        print("\n🔍 Testing OCR on selected regions...")
        print("=" * 50)
        
        all_results = []
        detection_image = self.original_image.copy()
        
        for i, (start, end) in enumerate(self.regions, 1):
            print(f"\n📋 Region {i}: ({start[0]}, {start[1]}) to ({end[0]}, {end[1]})")
            
            # Extract region from image
            x1, y1 = start
            x2, y2 = end
            region_image = self.original_image[y1:y2, x1:x2]
            
            # Save temporary region image
            temp_path = f"temp_region_{i}.png"
            cv2.imwrite(temp_path, region_image)
            
            try:
                # Run OCR on region
                results = self.ocr.process_image(temp_path)
                
                if results['success'] and results['results']:
                    print(f"✅ Found {len(results['results'])} clan members:")
                    for result in results['results']:
                        print(f"   • {result['name']}: {result['score']}")
                        all_results.append(result)
                        
                        # Add red box around detected clan member
                        # For now, just highlight the whole region - we could improve this later
                        cv2.rectangle(detection_image, (x1, y1), (x2, y2), (0, 0, 255), 3)
                        cv2.putText(detection_image, f"{result['name']}: {result['score']}", 
                                   (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                else:
                    # Show raw text for debugging
                    raw_texts = self.ocr.extract_text_from_image(temp_path)
                    print(f"⚠️  No clan members found")
                    if raw_texts:
                        print(f"   Raw text samples: {[t.strip()[:50] for t in raw_texts if t.strip()]}")
                
                # Clean up temp file
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"❌ Error processing region {i}: {e}")
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        # Show detection results
        if all_results:
            print(f"\n🎯 Total Results Found: {len(all_results)}")
            print("Final extracted data:")
            for result in all_results:
                print(f"   • {result['name']}: {result['score']}")
            
            # Display image with red boxes
            cv2.imshow("Clan Member Detections", detection_image)
            print("\n📺 Showing detection results in new window (press any key to close)")
            cv2.waitKey(0)
            cv2.destroyWindow("Clan Member Detections")
        else:
            print("\n❌ No clan member results found in any region")
    
    def save_regions(self):
        """Save regions to a JSON file."""
        if not self.regions:
            print("❌ No regions to save!")
            return
        
        # Create regions data
        regions_data = {
            'image_path': self.image_path,
            'regions': [
                {
                    'start': list(start),
                    'end': list(end)
                }
                for start, end in self.regions
            ]
        }
        
        # Save to file
        filename = f"regions_{os.path.splitext(os.path.basename(self.image_path))[0]}.json"
        with open(filename, 'w') as f:
            json.dump(regions_data, f, indent=2)
        
        print(f"💾 Saved {len(self.regions)} regions to {filename}")
    
    def load_regions(self):
        """Load regions from a JSON file."""
        filename = f"regions_{os.path.splitext(os.path.basename(self.image_path))[0]}.json"
        
        if not os.path.exists(filename):
            print(f"❌ No saved regions file found: {filename}")
            return
        
        try:
            with open(filename, 'r') as f:
                regions_data = json.load(f)
            
            self.regions = [
                (tuple(region['start']), tuple(region['end']))
                for region in regions_data['regions']
            ]
            
            print(f"📂 Loaded {len(self.regions)} regions from {filename}")
            self.draw_regions()
            
        except Exception as e:
            print(f"❌ Error loading regions: {e}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python region_selector.py <image_path>")
        print("Example: python region_selector.py mario_kart_results.png")
        return
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"❌ Image file not found: {image_path}")
        return
    
    try:
        selector = RegionSelector(image_path)
        regions = selector.run_interactive_selection()
        
        if regions:
            print(f"\n✅ Final result: {len(regions)} regions selected")
        else:
            print("\n❌ No regions selected")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 