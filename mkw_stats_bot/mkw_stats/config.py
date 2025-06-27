import os
from typing import List

# Bot Version (for debugging deployments)
BOT_VERSION = "1.0.10"  # Increment this for each deployment

# Discord Bot Configuration  
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')  # Required: Set this in your environment variables
GUILD_ID = os.getenv('GUILD_ID')  # Optional: Restrict to specific server
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Optional: Restrict to specific channel (legacy)
ALLOWED_CHANNELS = os.getenv('ALLOWED_CHANNELS')  # Optional: Multiple channels (comma-separated)

# Convert string IDs to integers if provided
if GUILD_ID:
    GUILD_ID = int(GUILD_ID)
if CHANNEL_ID:
    CHANNEL_ID = int(CHANNEL_ID)
if ALLOWED_CHANNELS:
    ALLOWED_CHANNELS = [int(ch.strip()) for ch in ALLOWED_CHANNELS.split(',')]

# Database Configuration (PostgreSQL)
# DATABASE_URL is automatically set by Railway or can be set manually
# Format: postgresql://user:password@host:port/database
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('RAILWAY_POSTGRES_URL')

# Complete Player Roster - All clan members for validation
# NOTE: Nicknames are managed in the database via management/setup_players.py
CLAN_ROSTER = [
    "Ami",
    "Benji", 
    "Corbs",
    "Cynical",
    "Danika",
    "DEMISE",
    "Dicey",
    "Hollow",
    "Jacob",
    "Jake",
    "James",
    "Juice",
    "Klefki",
    "Koopalings",
    "Minty",
    "Moon",
    "Mook",
    "Nick F",
    "Quick",
    "rx",
    "sopt",
    "Vortex",
    "Wilbur",
    "yukino"
]

# Table presets for different war result formats
# Start with empty presets - load custom formats from data/formats/ folder
TABLE_PRESETS = {}

# Default preset to use (will be set when custom format is loaded)
DEFAULT_TABLE_PRESET = None

# War/Race Configuration - Flexible player counts for substitutions
IDEAL_PLAYERS_PER_TEAM = 6      # Ideal 6v6 format
TOTAL_IDEAL_PLAYERS = 6        # 6v6 = 12 total players (ideal, but flexible)
MIN_PLAYERS_PER_TEAM = 1        # Minimum players to accept
MAX_PLAYERS_PER_TEAM = 12       # Maximum players per team (allows for subs)
EXPECTED_PLAYERS_PER_TEAM = 6   # Expected players per team (for compatibility)

# Total player limits (flexible for substitutions)
MIN_TOTAL_PLAYERS = 2           # Minimum total players (1v1)
MAX_TOTAL_PLAYERS = 20          # Maximum total players (allows for multiple subs)

DEFAULT_RACE_COUNT = 12  # Most wars are 12 races
MIN_RACE_COUNT = 1  # Minimum races in a war
MAX_RACE_COUNT = 12  # Maximum races in a war

# War result metadata that can be extracted or manually entered
WAR_METADATA_FIELDS = [
    'date',           # Date of the war
    'time',           # Time the war was played
    'race_count',     # Number of races (usually 12)
    'war_type',       # Type of war (e.g., "6v6", "FFA", etc.)
    'notes'           # Additional notes
]

# OCR Configuration
TESSERACT_PATH = os.getenv('TESSERACT_PATH')  # Let the system auto-detect if not set

# Confirmation timeout (seconds)
CONFIRMATION_TIMEOUT = 300  # 5 minutes 