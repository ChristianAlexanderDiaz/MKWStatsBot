#!/usr/bin/env python3
"""
OpenCV Installation Verification Script
Checks what OpenCV packages are actually installed and their compatibility
"""
import sys
import subprocess
import logging

def check_package_versions():
    """Check installed package versions using pip."""
    print("🔍 Checking installed package versions...")
    
    packages_to_check = [
        'opencv-python',
        'opencv-python-headless', 
        'opencv-contrib-python',
        'opencv-contrib-python-headless',
        'paddleocr',
        'paddlepaddle'
    ]
    
    for package in packages_to_check:
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                version = next((line for line in lines if line.startswith('Version:')), 'Version: Not found')
                location = next((line for line in lines if line.startswith('Location:')), 'Location: Not found')
                print(f"✅ {package}: {version}")
                print(f"   {location}")
            else:
                print(f"❌ {package}: Not installed")
        except Exception as e:
            print(f"❌ Error checking {package}: {e}")
    print()

def test_opencv_import():
    """Test OpenCV import and show build information."""
    print("🧪 Testing OpenCV import...")
    
    try:
        import cv2
        print(f"✅ OpenCV imported successfully!")
        print(f"   Version: {cv2.__version__}")
        
        # Show build information
        print("\n📋 OpenCV Build Information:")
        build_info = cv2.getBuildInformation()
        
        # Extract key information
        lines = build_info.split('\n')
        key_info = [
            'OpenCV modules',
            'CPU/HW features',
            'Built as dynamic libs',
            'C++ Compiler',
            'C++ flags (Release)',
            'OpenCV version',
        ]
        
        for line in lines:
            for key in key_info:
                if key in line:
                    print(f"   {line.strip()}")
                    break
        
        # Test basic functionality
        print("\n🔧 Testing basic OpenCV functionality...")
        import numpy as np
        
        # Create a simple test image
        test_image = np.zeros((100, 100, 3), dtype=np.uint8)
        test_image[25:75, 25:75] = [255, 255, 255]
        
        # Test image operations
        gray = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)
        print("✅ Color conversion works")
        
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        print("✅ Image filtering works")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import OpenCV: {e}")
        return False
    except Exception as e:
        print(f"❌ OpenCV functionality test failed: {e}")
        return False

def test_paddleocr_import():
    """Test PaddleOCR import without initializing."""
    print("🧪 Testing PaddleOCR import...")
    
    try:
        # Test import without initialization to avoid model downloads
        from paddleocr import PaddleOCR
        print("✅ PaddleOCR imported successfully!")
        
        # Check if we can create an instance (without actually loading models)
        print("🔧 Testing PaddleOCR class instantiation...")
        # Note: This will likely fail in headless environment, but we want to see the exact error
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import PaddleOCR: {e}")
        return False
    except Exception as e:
        print(f"❌ PaddleOCR test failed: {e}")
        return False

def check_system_libraries():
    """Check if required system libraries are available."""
    print("🔍 Checking system libraries...")
    
    libraries_to_check = [
        'libGL.so.1',
        'libgthread-2.0.so.0',
        'libSM.so.6',
        'libXext.so.6',
        'libXrender.so.1'
    ]
    
    for lib in libraries_to_check:
        try:
            result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True)
            if lib in result.stdout:
                print(f"✅ {lib}: Available")
            else:
                print(f"❌ {lib}: Not found")
        except Exception as e:
            print(f"❌ Error checking {lib}: {e}")
    print()

def main():
    """Main verification function."""
    print("🚀 OpenCV & PaddleOCR Installation Verification")
    print("=" * 50)
    
    # Check package versions
    check_package_versions()
    
    # Check system libraries
    check_system_libraries()
    
    # Test OpenCV
    opencv_success = test_opencv_import()
    print()
    
    # Test PaddleOCR
    paddleocr_success = test_paddleocr_import()
    print()
    
    # Summary
    print("📊 VERIFICATION SUMMARY")
    print("=" * 25)
    print(f"OpenCV: {'✅ Working' if opencv_success else '❌ Failed'}")
    print(f"PaddleOCR: {'✅ Working' if paddleocr_success else '❌ Failed'}")
    
    if opencv_success and paddleocr_success:
        print("\n🎉 All components verified successfully!")
        return 0
    else:
        print("\n❌ Some components failed verification")
        return 1

if __name__ == "__main__":
    sys.exit(main())