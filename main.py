#!/usr/bin/env python3
"""
MKWStatsBot - Main Entry Point

Mario Kart Wii Statistics Discord Bot
Extracts player scores from race result images using OCR and maintains statistics.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.bot import setup_bot
from src import config
import logging

def main():
    """Main entry point for the bot."""
    
    # Check if Discord token is set
    if not config.DISCORD_TOKEN:
        print("❌ Please set DISCORD_BOT_TOKEN environment variable")
        print("Run: python utils/setup_discord.py")
        return
    
    # Setup and run bot
    print("🏁 Starting MKWStatsBot...")
    bot = setup_bot()
    
    try:
        bot.run(config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
        print(f"❌ Bot crashed: {e}")

if __name__ == "__main__":
    main() 