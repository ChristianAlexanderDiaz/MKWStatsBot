"""
MKWStatsBot - Mario Kart Wii Statistics Discord Bot

Core application package containing bot logic, OCR processing, and database operations.
"""

from .bot import MarioKartBot, setup_bot
from .database import DatabaseManager
# OCRProcessor removed - using only PaddleOCR
from . import config

__version__ = "2.0.0"
__all__ = ["MarioKartBot", "setup_bot", "DatabaseManager", "config"] 