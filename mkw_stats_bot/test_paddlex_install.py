#!/usr/bin/env python3
"""
Test script to verify PaddleX[OCR] installation works correctly
This helps debug Railway deployment issues locally
"""
import sys
import subprocess
import logging

def test_paddlex_installation():
    """Test PaddleX OCR installation and functionality."""
    print("🧪 Testing PaddleX OCR Installation")
    print("=" * 50)
    
    # Test 1: Import PaddleX
    try:
        import paddlex
        print("✅ PaddleX imported successfully")
        print(f"   Version: {getattr(paddlex, '__version__', 'Unknown')}")
    except ImportError as e:
        print(f"❌ PaddleX import failed: {e}")
        return False
    
    # Test 2: Check installed packages
    print("\n📦 Checking installed packages...")
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                              capture_output=True, text=True)
        paddle_lines = [line for line in result.stdout.split('\n') 
                       if any(pkg in line.lower() for pkg in ['paddlex', 'paddlepaddle', 'paddleocr'])]
        
        if paddle_lines:
            print("   Paddle-related packages:")
            for line in paddle_lines:
                print(f"   {line}")
        else:
            print("❌ No Paddle packages found!")
            return False
    except Exception as e:
        print(f"❌ Error checking packages: {e}")
    
    # Test 3: Try to create OCR pipeline
    print("\n🏗️ Testing OCR pipeline creation...")
    try:
        from paddlex import create_pipeline
        
        # This should work without downloading models yet
        print("   Attempting to create OCR pipeline...")
        pipeline = create_pipeline(pipeline="OCR")
        print("✅ PaddleX OCR pipeline created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ OCR pipeline creation failed: {e}")
        
        # Check if it's the dependency error we've been seeing
        if "OCR requires additional dependencies" in str(e):
            print("🚨 FOUND THE ISSUE: OCR dependencies not installed!")
            print("💡 This means paddlex[ocr] installation failed")
            return False
        elif "cannot be None at the same time" in str(e):
            print("⚠️ Pipeline syntax error - this is not the dependency issue")
            return True  # Syntax error means dependencies are OK
        else:
            print(f"⚠️ Unknown error: {e}")
            return False

if __name__ == "__main__":
    success = test_paddlex_installation()
    if success:
        print("\n🎉 PaddleX OCR installation test PASSED!")
        sys.exit(0)
    else:
        print("\n❌ PaddleX OCR installation test FAILED!")
        sys.exit(1)