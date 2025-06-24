#!/bin/bash
# Install system dependencies for Render deployment

# Install Tesseract OCR
apt-get update
apt-get install -y tesseract-ocr tesseract-ocr-eng

# Install Python dependencies
pip install -r requirements.txt

echo "✅ Build completed successfully!" 