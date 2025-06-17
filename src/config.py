import os
from typing import List

# Discord Bot Configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')  # Required: Set this in your environment variables
GUILD_ID = os.getenv('GUILD_ID')  # Optional: Restrict to specific server
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Optional: Restrict to specific channel

# Convert string IDs to integers if provided
if GUILD_ID:
    GUILD_ID = int(GUILD_ID)
if CHANNEL_ID:
    CHANNEL_ID = int(CHANNEL_ID)

# Database Configuration
DATABASE_PATH = 'mario_kart_results.db'

# Clan Roster - Add your clan members' names here
CLAN_ROSTER = [
    "Corbs",
    "Cynical",
    "DEMISE",
    "Dicey",
    "James",
    "Moon",
    "Klefki",
    "Minty",
    "Quick",
    "rx",
    "sopt",
    "yukino",
    
]

# Team roster in alphabetical order
PHANTOM_ORBIT_ROSTER = [
    "Corbs",
    "Cynical",
    "DEMISE",
    "Dicey",
    "James",
    "Moon",
    "Klefki",
    "Minty",
    "Quick",
    "rx",
    "sopt",
    "yukino",
]

# Team roster in alphabetical order (First Team)
FIRST_TEAM_ROSTER = [
    "Astralixv",
    "Christian", 
    "DEMISE",
    "Dicey",
    "Gravy on Moon",
    "Klefki",
    "Minty",
    "myst.0000",
    "Quick",
    "sopt",
    "yukino"
]

# MOONLIGHT_BOOTEL_ROSTER = [
# ]

# Table Format Presets - saved region coordinates for consistent table layouts
TABLE_PRESETS = {
    "format_1": {
        "name": "Standard 6v6 Table Format",
        "regions": [],  # Will be populated when user saves a preset
        "description": "Standard Mario Kart 6v6 race results table",
        "expected_players": 6
    }
    # Add more presets as needed
}

# Expected number of players for validation
EXPECTED_PLAYERS_PER_TEAM = 6
TOTAL_EXPECTED_PLAYERS = 12  # 6v6 format

# OCR Configuration
TESSERACT_PATH = '/usr/local/bin/tesseract'  # Adjust path as needed for your system

# Confirmation timeout (seconds)
CONFIRMATION_TIMEOUT = 60 