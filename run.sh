#!/bin/bash

# Mario Kart Discord Bot Launcher

echo "🏁 Starting Mario Kart Results Bot..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check if Discord token is set
if [ -z "$DISCORD_BOT_TOKEN" ]; then
    echo "❌ Error: DISCORD_BOT_TOKEN environment variable is not set!"
    echo "Please set it with: export DISCORD_BOT_TOKEN='your_token_here'"
    exit 1
fi

# Check if tesseract is installed
if ! command -v tesseract &> /dev/null; then
    echo "❌ Error: Tesseract OCR is not installed!"
    echo "Please install it:"
    echo "  macOS: brew install tesseract"
    echo "  Ubuntu: sudo apt-get install tesseract-ocr"
    exit 1
fi

echo "✅ All dependencies verified!"
echo "🚀 Starting bot..."

# Run the bot
python main.py 