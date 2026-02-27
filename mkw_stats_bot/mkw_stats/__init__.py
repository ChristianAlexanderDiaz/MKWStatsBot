"""
MKWStatsBot - Mario Kart Wii Statistics Discord Bot

Core application package containing bot logic, OCR processing, and database operations.
"""

# OCRProcessor removed - using only PaddleOCR
from . import config
from .bot import MarioKartBot, setup_bot
from .database import DatabaseManager

__version__ = "2.0.0"
__all__ = ["MarioKartBot", "setup_bot", "DatabaseManager", "config"]
