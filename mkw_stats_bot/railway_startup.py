#!/usr/bin/env python3
"""
Railway Startup Script - Fix OpenCV conflicts before starting the bot
This script runs BEFORE the main bot to ensure OpenCV headless version is installed
"""

import subprocess
import sys
import os
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

def fix_opencv_railway():
    """Fix OpenCV conflicts aggressively for Railway deployment."""
    
    logging.info("🚀 Railway startup - Fixing OpenCV conflicts...")
    
    # Set headless environment variables early
    os.environ['QT_QPA_PLATFORM'] = 'offscreen' 
    os.environ['DISPLAY'] = ''
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['OPENCV_IO_ENABLE_JASPER'] = 'false'
    os.environ['OPENCV_IO_ENABLE_OPENEXR'] = 'false'
    
    try:
        # Check what OpenCV packages are installed
        opencv_gui_packages = ['opencv-python', 'opencv-contrib-python']
        opencv_headless_packages = ['opencv-python-headless', 'opencv-contrib-python-headless']
        
        conflicts_found = []
        headless_found = []
        
        # Check for GUI OpenCV packages (these cause libGL.so.1 errors)
        for package in opencv_gui_packages:
            try:
                result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    conflicts_found.append(package)
                    logging.warning(f"❌ Found conflicting package: {package}")
            except Exception:
                pass
        
        # Check for headless packages
        for package in opencv_headless_packages:
            try:
                result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    headless_found.append(package)
                    logging.info(f"✅ Found headless package: {package}")
            except Exception:
                pass
        
        # If we found conflicts, fix them
        if conflicts_found:
            logging.info("🔧 Fixing OpenCV conflicts for Railway...")
            
            # Uninstall GUI versions
            for package in conflicts_found:
                try:
                    logging.info(f"🗑️ Uninstalling {package}...")
                    result = subprocess.run([sys.executable, '-m', 'pip', 'uninstall', package, '-y'], 
                                          capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        logging.info(f"✅ Successfully removed {package}")
                    else:
                        logging.warning(f"⚠️ Failed to remove {package}: {result.stderr}")
                except Exception as e:
                    logging.error(f"❌ Error removing {package}: {e}")
            
            # Install headless version if not already present
            if not headless_found:
                try:
                    logging.info("📦 Installing opencv-contrib-python-headless...")
                    result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'opencv-contrib-python-headless>=4.5.0'], 
                                          capture_output=True, text=True, timeout=120)
                    if result.returncode == 0:
                        logging.info("✅ Successfully installed opencv-contrib-python-headless")
                    else:
                        logging.error(f"❌ Failed to install headless OpenCV: {result.stderr}")
                except Exception as e:
                    logging.error(f"❌ Error installing headless OpenCV: {e}")
        
        # Final verification
        try:
            import cv2
            logging.info(f"✅ OpenCV verification successful - Version: {cv2.__version__}")
            return True
        except Exception as e:
            logging.error(f"❌ OpenCV verification failed: {e}")
            return False
            
    except Exception as e:
        logging.error(f"❌ Railway OpenCV fix failed: {e}")
        return False

def main():
    """Main startup function."""
    logging.info("🚀 Starting Railway OpenCV fix...")
    
    # Fix OpenCV conflicts
    success = fix_opencv_railway()
    
    if success:
        logging.info("✅ Railway startup completed successfully")
        
        # Now start the actual bot
        logging.info("🚀 Starting MKW Stats Bot...")
        try:
            # Import and run the main bot
            import main
        except Exception as e:
            logging.error(f"❌ Bot startup failed: {e}")
            sys.exit(1)
    else:
        logging.error("❌ Railway startup failed - OpenCV conflicts not resolved")
        sys.exit(1)

if __name__ == "__main__":
    main()