#!/usr/bin/env python3
"""
Interactive coordinate picker for selecting OCR crop regions on Mario Kart table images.

Usage:
1. Place your image in data/formats/smalltable.png
2. Run: python coordinate_picker.py
3. Click and drag to select the table region
4. Coordinates will be printed to console
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import RectangleSelector
from PIL import Image
import os
import sys

class CoordinatePicker:
    def __init__(self, image_path):
        self.image_path = image_path
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        
        # Load and display image
        self.load_image()
        self.setup_plot()
        
    def load_image(self):
        """Load the image and get its dimensions."""
        try:
            self.image = Image.open(self.image_path)
            self.img_width, self.img_height = self.image.size
            print(f"📸 Loaded image: {self.img_width}x{self.img_height}")
        except Exception as e:
            print(f"❌ Error loading image {self.image_path}: {e}")
            sys.exit(1)
            
    def setup_plot(self):
        """Setup matplotlib plot with image and selection tools."""
        self.fig, self.ax = plt.subplots(1, 1, figsize=(12, 8))
        self.ax.imshow(self.image)
        self.ax.set_title(f"Click and drag to select table region\nImage: {self.img_width}x{self.img_height}")
        
        # Setup rectangle selector
        self.selector = RectangleSelector(
            self.ax, 
            self.on_rectangle_select,
            useblit=True,
            button=[1],  # Only left mouse button
            minspanx=10, minspany=10,  # Minimum selection size
            spancoords='pixels',
            interactive=True
        )
        
        # Add instructions
        plt.figtext(0.5, 0.02, 
                   "Instructions: Click and drag to select the table region. Close window when done.",
                   ha='center', fontsize=10, style='italic')
        
    def on_rectangle_select(self, eclick, erelease):
        """Callback function when rectangle selection is made."""
        # Get coordinates (matplotlib coordinates)
        x1, y1 = int(eclick.xdata), int(eclick.ydata)
        x2, y2 = int(erelease.xdata), int(erelease.ydata)
        
        # Ensure correct order (top-left to bottom-right)
        self.start_x = min(x1, x2)
        self.start_y = min(y1, y2)
        self.end_x = max(x1, x2)
        self.end_y = max(y1, y2)
        
        # Ensure coordinates are within image bounds
        self.start_x = max(0, min(self.start_x, self.img_width))
        self.start_y = max(0, min(self.start_y, self.img_height))
        self.end_x = max(0, min(self.end_x, self.img_width))
        self.end_y = max(0, min(self.end_y, self.img_height))
        
        width = self.end_x - self.start_x
        height = self.end_y - self.start_y
        
        # Update title with current selection
        self.ax.set_title(
            f"Selected region: ({self.start_x},{self.start_y}) to ({self.end_x},{self.end_y})\n"
            f"Size: {width}x{height} pixels"
        )
        
        # Print coordinates in real-time
        print(f"🎯 Selection: start_x={self.start_x}, start_y={self.start_y}, "
              f"end_x={self.end_x}, end_y={self.end_y}")
        print(f"   Region size: {width}x{height}")
        
    def show(self):
        """Display the image and start coordinate selection."""
        print("🖱️  Click and drag on the image to select the table region")
        print("🔍 Coordinates will be shown in real-time")
        print("❌ Close the window when you're satisfied with the selection")
        plt.show()
        
        # Print final results
        if all(coord is not None for coord in [self.start_x, self.start_y, self.end_x, self.end_y]):
            print("\n" + "="*60)
            print("🎉 FINAL COORDINATES:")
            print("="*60)
            print(f"start_x = {self.start_x}")
            print(f"start_y = {self.start_y}")
            print(f"end_x = {self.end_x}")
            print(f"end_y = {self.end_y}")
            print()
            print("📋 Copy this into your code:")
            print(f"CROP_COORDS = {{")
            print(f"    'start_x': {self.start_x},")
            print(f"    'start_y': {self.start_y},")
            print(f"    'end_x': {self.end_x},")
            print(f"    'end_y': {self.end_y}")
            print(f"}}")
            
            # Calculate region size
            width = self.end_x - self.start_x
            height = self.end_y - self.start_y
            print(f"\n📏 Selected region size: {width}x{height} pixels")
            print(f"📊 Coverage: {width/self.img_width:.1%} width, {height/self.img_height:.1%} height")
        else:
            print("⚠️  No selection made")

def main():
    """Main function to run the coordinate picker."""
    # Default image path
    default_path = "data/formats/smalltable.png"
    
    # Check if image exists
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = default_path
        
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        print("📁 Please place your image at: data/formats/smalltable.png")
        print("🔧 Or specify path: python coordinate_picker.py path/to/your/image.png")
        sys.exit(1)
        
    # Create coordinate picker and run
    picker = CoordinatePicker(image_path)
    picker.show()

if __name__ == "__main__":
    main()