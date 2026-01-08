#!/usr/bin/env python3
"""
Enhanced Region Selection Tool for Mario Kart OCR

Interactive tool to select regions on any image with name/score separator.

Usage:
    python region_selector.py [image_path]
    python region_selector.py mkw_stats_bot/data/formats/IMG_9254.png

Two-Step Process:
    1. Click and drag to select main region (yellow box)
    2. Click inside region to place vertical separator line (red line)

Controls:
    - Step 1: Click and drag for main region
    - Step 2: Single click for separator placement
    - Press 's' to save region + separator
    - Press 'r' to reset everything
    - Press 'q' to quit
"""

import cv2
import json
import os
import sys
import argparse
from datetime import datetime

class RegionSelector:
    def __init__(self, image_path=None):
        self.image_path = image_path or "data/formats/IMG_9254.png"
        self.output_path = "data/formats/selected_regions.json"
        self.image = None
        self.clone = None
        self.start_point = None
        self.end_point = None
        self.drawing = False
        self.selected_regions = []
        # New: Separator line support
        self.separator_x = None
        self.region_selected = False
        self.separator_placed = False
        
    def load_image(self):
        """Load the specified image."""
        if not os.path.exists(self.image_path):
            print(f"❌ Error: {self.image_path} not found!")
            print(f"Please provide a valid image path or place the image in the correct directory.")
            return False
            
        self.image = cv2.imread(self.image_path)
        if self.image is None:
            print(f"❌ Error: Could not load {self.image_path}")
            return False
            
        self.clone = self.image.copy()
        print(f"✅ Loaded image: {self.image_path}")
        print(f"   Image size: {self.image.shape[1]}x{self.image.shape[0]}")
        return True
    
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events for region selection and separator placement."""
        
        if event == cv2.EVENT_LBUTTONDOWN:
            if not self.region_selected:
                # Phase 1: Start drawing rectangle
                self.drawing = True
                self.start_point = (x, y)
                self.end_point = (x, y)
                print(f"🖱️  Start region selection at: ({x}, {y})")
            else:
                # Phase 2: Place separator line (single click)
                if self.selected_regions:
                    region = self.selected_regions[0]
                    start_x, start_y = region['start']
                    end_x, end_y = region['end']
                    
                    # Validate separator is within region bounds
                    if start_x <= x <= end_x and start_y <= y <= end_y:
                        self.separator_x = x
                        self.separator_placed = True
                        print(f"📏 Separator placed at X={x}")
                        
                        # Draw separator line on the clone (persistent display)
                        cv2.line(self.clone, (x, start_y), (x, end_y), (0, 0, 255), 2)  # Red line
                        cv2.putText(self.clone, "Names | Scores", 
                                   (start_x, end_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        cv2.imshow("Region Selector", self.clone)
                    else:
                        print(f"❌ Separator must be within the selected region!")
            
        elif event == cv2.EVENT_MOUSEMOVE:
            # Update rectangle while dragging (only in phase 1)
            if self.drawing and not self.region_selected:
                self.end_point = (x, y)
                temp_image = self.clone.copy()
                cv2.rectangle(temp_image, self.start_point, self.end_point, (0, 255, 255), 2)  # Yellow
                cv2.imshow("Region Selector", temp_image)
                
        elif event == cv2.EVENT_LBUTTONUP:
            # Finish drawing rectangle (only in phase 1)
            if self.drawing and not self.region_selected:
                self.drawing = False
                self.end_point = (x, y)
                
                # Calculate rectangle properties
                x1, y1 = self.start_point
                x2, y2 = self.end_point
                
                # Ensure top-left to bottom-right order
                start_x = min(x1, x2)
                start_y = min(y1, y2)
                end_x = max(x1, x2)
                end_y = max(y1, y2)
                
                width = end_x - start_x
                height = end_y - start_y
                
                print(f"🖱️  Region selected: ({start_x}, {start_y}) to ({end_x}, {end_y})")
                print(f"📏 Size: {width} x {height}")
                print(f"👆 Now click inside the region to place the separator line")
                
                # Store the selection
                self.selected_regions = [{
                    "name": "main_region",
                    "start": [start_x, start_y],
                    "end": [end_x, end_y],
                    "width": width,
                    "height": height
                }]
                
                self.region_selected = True
                
                # Draw the selected region on clone (persistent display)
                cv2.rectangle(self.clone, (start_x, start_y), (end_x, end_y), (0, 255, 255), 2)  # Yellow
                cv2.putText(self.clone, f"Region: {width}x{height}", 
                           (start_x, start_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow("Region Selector", self.clone)
    
    def save_regions(self):
        """Save selected regions with separator to JSON file."""
        if not self.selected_regions:
            print("❌ No regions selected! Please select a region first.")
            return False
            
        if not self.separator_placed:
            print("❌ No separator placed! Please click within the region to place separator line.")
            return False
            
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # Add separator_x to the region data
        region_with_separator = self.selected_regions[0].copy()
        region_with_separator["separator_x"] = self.separator_x
        
        # Prepare output data
        output_data = {
            "regions": [region_with_separator],
            "image_source": os.path.basename(self.image_path),
            "image_size": {
                "width": self.image.shape[1],
                "height": self.image.shape[0]
            },
            "created_date": datetime.now().isoformat(),
            "description": "OCR region selection with name/score separator for Mario Kart table format"
        }
        
        try:
            with open(self.output_path, 'w') as f:
                json.dump(output_data, f, indent=2)
            
            print(f"✅ Regions saved to: {self.output_path}")
            print(f"📊 Saved {len(self.selected_regions)} region(s)")
            return True
            
        except Exception as e:
            print(f"❌ Error saving regions: {e}")
            return False
    
    def reset_selection(self):
        """Reset the current selection."""
        self.selected_regions = []
        self.start_point = None
        self.end_point = None
        self.drawing = False
        # Reset separator variables
        self.separator_x = None
        self.region_selected = False
        self.separator_placed = False
        self.clone = self.image.copy()
        cv2.imshow("Region Selector", self.clone)
        print("🔄 Selection and separator reset")
    
    def run(self):
        """Run the region selector interface."""
        print("🏁 Mario Kart OCR Region Selector")
        print("=" * 40)
        
        if not self.load_image():
            return
        
        # Create window and set mouse callback
        cv2.namedWindow("Region Selector", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Region Selector", self.mouse_callback)
        cv2.imshow("Region Selector", self.image)
        
        print("\n🎮 Controls:")
        print("  - Step 1: Click and drag to select main region (yellow box)")
        print("  - Step 2: Click inside region to place separator line (red line)")
        print("  - Press 's' to save region + separator")
        print("  - Press 'r' to reset everything")  
        print("  - Press 'q' to quit")
        print("\n⌨️  Waiting for region selection...")
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("👋 Quitting region selector")
                break
                
            elif key == ord('s'):
                if self.save_regions():
                    print("💾 Regions saved successfully!")
                else:
                    print("❌ Failed to save regions")
                    
            elif key == ord('r'):
                self.reset_selection()
        
        cv2.destroyAllWindows()
        print("🏁 Region selector closed")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Enhanced Region Selection Tool for Mario Kart OCR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python region_selector.py
  python region_selector.py data/formats/Table1.png
  python region_selector.py mkw_stats_bot/data/formats/IMG_9254.png
        """
    )
    parser.add_argument(
        'image_path',
        nargs='?',
        default=None,
        help='Path to the image file (default: data/formats/IMG_9254.png)'
    )

    args = parser.parse_args()

    selector = RegionSelector(image_path=args.image_path)
    selector.run()

if __name__ == "__main__":
    main()