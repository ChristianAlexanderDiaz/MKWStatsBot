#!/bin/bash

# Mario Kart World Clan Stats Bot Startup Script
# Professional startup script with error handling and logging

echo "🏁 Starting Mario Kart World Clan Stats Bot..."

# Check if virtual environment exists (check parent directory first)
if [ -d "../venv" ]; then
    echo "🔧 Using existing virtual environment from parent directory..."
    source ../venv/bin/activate
elif [ -d "venv" ]; then
    echo "🔧 Using local virtual environment..."
    source venv/bin/activate
else
    echo "❌ Virtual environment not found. Creating one..."
    python3 -m venv venv
    echo "✅ Virtual environment created."
    source venv/bin/activate
fi

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists or if DISCORD_BOT_TOKEN is set in environment
if [ ! -f ".env" ] && [ -z "$DISCORD_BOT_TOKEN" ]; then
    echo "⚠️  No .env file found and DISCORD_BOT_TOKEN not set in environment."
    echo "   Option 1: Create .env file:"
    echo "     cp config/env_example.txt .env"
    echo "     Then edit .env with your Discord bot token."
    echo "   Option 2: Your token is already in .zshrc, so you can continue!"
    echo "   🚀 Proceeding with environment variables from shell..."
elif [ -f ".env" ]; then
    echo "✅ Found .env file."
elif [ ! -z "$DISCORD_BOT_TOKEN" ]; then
    echo "✅ Using DISCORD_BOT_TOKEN from environment."
fi

# Check if database is initialized
if [ ! -f "database/mario_kart_clan.db" ]; then
    echo "🗄️  Database not found. Initializing clan players..."
    python tools/setup_players.py
    echo "✅ Database initialized with clan players."
fi

# Start the bot
echo "🚀 Launching bot..."
python main.py 