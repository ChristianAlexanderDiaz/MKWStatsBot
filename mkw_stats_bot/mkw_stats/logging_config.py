#!/usr/bin/env python3
"""
Centralized logging configuration for MKW Stats Bot.

Provides structured logging with multiple handlers, proper formatting,
and environment-based log levels for both development and production.
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Log levels mapping
LOG_LEVELS = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[41m',   # Red background
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        """Format log record with colors for console output."""
        # Add color to levelname
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}"
                f"{record.levelname:8}"
                f"{self.COLORS['RESET']}"
            )
        
        # Format the message
        formatted = super().format(record)
        return formatted


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True
) -> logging.Logger:
    """
    Setup centralized logging configuration.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (default: mario_kart_bot.log)
        enable_console: Enable console logging
        enable_file: Enable file logging
        
    Returns:
        Configured logger instance
    """
    
    # Determine log level
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    if log_level not in LOG_LEVELS:
        log_level = 'INFO'
    
    level = LOG_LEVELS[log_level]
    
    # Determine log file path
    if log_file is None:
        log_file = os.getenv('LOG_FILE', 'mario_kart_bot.log')
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler with colors
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        console_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # File handler with rotation
    if enable_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        
        file_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Log startup message
    logger.info("=" * 80)
    logger.info(f"🏁 MKW Stats Bot - Logging Initialized")
    logger.info(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"📊 Log Level: {log_level}")
    if enable_file:
        logger.info(f"📁 Log File: {log_file}")
    logger.info("=" * 80)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Module name (usually __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_function_call(func):
    """
    Decorator to log function calls with parameters and execution time.
    
    Usage:
        @log_function_call
        def my_function(param1, param2):
            pass
    """
    import functools
    import time
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        
        # Log function entry
        logger.debug(f"🔵 Entering {func.__name__}()")
        
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Log successful completion
            logger.debug(
                f"✅ Completed {func.__name__}() in {execution_time:.3f}s"
            )
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            # Log exception
            logger.error(
                f"❌ Exception in {func.__name__}() after {execution_time:.3f}s: {e}"
            )
            raise
    
    return wrapper


def log_database_operation(operation: str, table: str = None, count: int = None):
    """
    Log database operations for monitoring and debugging.
    
    Args:
        operation: Type of operation (SELECT, INSERT, UPDATE, DELETE)
        table: Table name (optional)
        count: Number of records affected (optional)
    """
    logger = get_logger('mkw_stats.database')
    
    message = f"🗄️  Database {operation}"
    if table:
        message += f" on {table}"
    if count is not None:
        message += f" ({count} records)"
    
    logger.debug(message)


def log_ocr_operation(image_path: str, success: bool, players_found: int = 0):
    """
    Log OCR operations for monitoring image processing.
    
    Args:
        image_path: Path to processed image
        success: Whether OCR was successful
        players_found: Number of players detected
    """
    logger = get_logger('mkw_stats.ocr')
    
    if success:
        logger.info(f"🖼️  OCR Success: {image_path} - Found {players_found} players")
    else:
        logger.warning(f"🖼️  OCR Failed: {image_path}")


def log_discord_command(command: str, user: str, guild: str = None):
    """
    Log Discord command usage for monitoring.
    
    Args:
        command: Command name
        user: User who executed the command
        guild: Guild name (optional)
    """
    logger = get_logger('mkw_stats.discord')
    
    message = f"💬 Command '{command}' by {user}"
    if guild:
        message += f" in {guild}"
    
    logger.info(message)


# Configure logging on module import
# Note: Logging setup is now handled explicitly in bot.py to avoid duplicate initialization


# Test the logging configuration
if __name__ == "__main__":
    print("🧪 Testing logging configuration...")
    
    # Setup logging
    logger = setup_logging(log_level='DEBUG')
    
    # Test different log levels
    logger.debug("🔍 This is a debug message")
    logger.info("ℹ️  This is an info message")
    logger.warning("⚠️  This is a warning message")
    logger.error("❌ This is an error message")
    logger.critical("🚨 This is a critical message")
    
    # Test module logger
    module_logger = get_logger('test_module')
    module_logger.info("📦 This is from a module logger")
    
    # Test decorators
    @log_function_call
    def test_function():
        import time
        time.sleep(0.1)
        return "Success"
    
    result = test_function()
    logger.info(f"✅ Function result: {result}")
    
    # Test specialized logging functions
    log_database_operation("SELECT", "players", 10)
    log_ocr_operation("test_image.png", True, 6)
    log_discord_command("mkstats", "TestUser", "TestGuild")
    
    print("✅ Logging test completed - check mario_kart_bot.log")