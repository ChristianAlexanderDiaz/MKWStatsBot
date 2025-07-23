#!/usr/bin/env python3
"""
Region Selection Tool for Mario Kart OCR

Interactive tool to select regions on Table6v6.png and save coordinates to JSON.

Usage:
    python region_selector.py

Controls:
    - Click and drag to select rectangle
    - Press 's' to save coordinates
    - Press 'r' to reset selection
    - Press 'q' to quit
"""

import cv2
import json
import os
from datetime import datetime

class RegionSelector:
    def __init__(self):
        self.image_path = "data/formats/Table6v6.png"
        self.output_path = "data/formats/selected_regions.json"
        self.image = None
        self.clone = None
        self.start_point = None
        self.end_point = None
        self.drawing = False
        self.selected_regions = []
        
    def load_image(self):
        """Load the Table6v6.png image."""
        if not os.path.exists(self.image_path):
            print(f"❌ Error: {self.image_path} not found!")
            print("Please place Table6v6.png in the data/formats/ directory.")
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
        """Handle mouse events for region selection."""
        
        if event == cv2.EVENT_LBUTTONDOWN:
            # Start drawing rectangle
            self.drawing = True
            self.start_point = (x, y)
            self.end_point = (x, y)
            print(f"🖱️  Start selection at: ({x}, {y})")
            
        elif event == cv2.EVENT_MOUSEMOVE:
            # Update rectangle while dragging
            if self.drawing:
                self.end_point = (x, y)
                # Create fresh copy and draw current rectangle
                temp_image = self.clone.copy()
                cv2.rectangle(temp_image, self.start_point, self.end_point, (0, 255, 0), 2)
                cv2.imshow("Region Selector", temp_image)
                
        elif event == cv2.EVENT_LBUTTONUP:
            # Finish drawing rectangle
            if self.drawing:
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
                
                print(f"🖱️  End selection at: ({x}, {y})")
                print(f"📐 Selected region: ({start_x}, {start_y}) to ({end_x}, {end_y})")
                print(f"📏 Size: {width} x {height}")
                
                # Store the selection (replace previous if exists)
                self.selected_regions = [{
                    "name": "main_region",
                    "start": [start_x, start_y],
                    "end": [end_x, end_y],
                    "width": width,
                    "height": height
                }]
                
                # Draw final rectangle
                cv2.rectangle(self.clone, (start_x, start_y), (end_x, end_y), (0, 255, 0), 2)
                cv2.putText(self.clone, f"Region: {width}x{height}", 
                           (start_x, start_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Region Selector", self.clone)
    
    def save_regions(self):
        """Save selected regions to JSON file."""
        if not self.selected_regions:
            print("❌ No regions selected! Please select a region first.")
            return False
            
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # Prepare output data
        output_data = {
            "regions": self.selected_regions,
            "image_source": "Table6v6.png",
            "image_size": {
                "width": self.image.shape[1],
                "height": self.image.shape[0]
            },
            "created_date": datetime.now().isoformat(),
            "description": "OCR region selection for Ice Mario table format"
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
        self.clone = self.image.copy()
        cv2.imshow("Region Selector", self.clone)
        print("🔄 Selection reset")
    
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
        print("  - Click and drag to select region")
        print("  - Press 's' to save coordinates")
        print("  - Press 'r' to reset selection")  
        print("  - Press 'q' to quit")
        print("\n⌨️  Waiting for input...")
        
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
    selector = RegionSelector()
    selector.run()

if __name__ == "__main__":
    main()