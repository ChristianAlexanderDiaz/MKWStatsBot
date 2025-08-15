#!/usr/bin/env python3
"""
OCR Configuration Manager for MKW Stats Bot
Handles Railway environment variable-based OCR resource configuration
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OCRMode(Enum):
    """OCR operation modes for different usage patterns."""
    BULK_HEAVY = "bulk_heavy"      # Optimized for large bulk scanning operations
    SINGLE_FOCUSED = "single_focused"  # Optimized for fast single image processing
    BALANCED = "balanced"          # Balanced for mixed usage patterns


class OCRPriority(Enum):
    """Priority levels for OCR operations."""
    EXPRESS = "express"     # Single image scans, immediate processing
    STANDARD = "standard"   # Small bulk scans (2-10 images), normal processing
    BACKGROUND = "background"  # Large bulk scans (10+ images), queued processing


@dataclass
class OCRResourceConfig:
    """Configuration for OCR resource allocation."""
    # Core OCR Settings
    mode: OCRMode = OCRMode.BALANCED
    max_concurrent: int = 2
    enable_priority_borrowing: bool = True
    enable_usage_adaptation: bool = True
    
    # Priority-based Resource Limits
    express_max_concurrent: int = 4
    standard_max_concurrent: int = 2
    background_max_concurrent: int = 1
    borrowing_threshold: float = 0.8  # 80% utilization threshold for borrowing
    
    # PaddleOCR Performance Settings
    paddle_cpu_threads: int = 4
    memory_limit_mb: int = 2048
    batch_size: int = 3
    
    # Adaptive Behavior Settings
    usage_window_minutes: int = 60  # Time window for usage pattern analysis
    mode_switch_threshold: float = 0.7  # Usage ratio to trigger mode switch
    bulk_operation_threshold: int = 10  # Images count to classify as bulk operation
    
    # Railway Environment Limits
    railway_max_cpu_cores: int = 8
    railway_max_memory_gb: int = 8
    
    # Performance Monitoring
    enable_performance_logging: bool = True
    metrics_collection_interval: int = 30  # seconds
    
    # Resource Cleanup
    cleanup_interval_minutes: int = 5
    memory_cleanup_threshold: float = 0.85  # 85% memory usage triggers cleanup


class OCRConfigManager:
    """
    Manages OCR configuration from Railway environment variables.
    Provides secure, production-ready configuration management.
    """
    
    def __init__(self):
        """Initialize configuration manager with Railway environment variables."""
        self.config = self._load_configuration()
        self._validate_configuration()
        self._log_configuration()
    
    def _load_configuration(self) -> OCRResourceConfig:
        """Load configuration from Railway environment variables."""
        try:
            # Parse OCR mode
            mode_str = os.getenv('OCR_MODE', 'balanced').lower()
            try:
                mode = OCRMode(mode_str)
            except ValueError:
                logger.warning(f"Invalid OCR_MODE '{mode_str}', defaulting to 'balanced'")
                mode = OCRMode.BALANCED
            
            # Core settings with Railway environment variable overrides
            config = OCRResourceConfig(
                # Core OCR Settings
                mode=mode,
                max_concurrent=self._get_int_env('OCR_MAX_CONCURRENT', 2, min_val=1, max_val=8),
                enable_priority_borrowing=self._get_bool_env('OCR_ENABLE_PRIORITY_BORROWING', True),
                enable_usage_adaptation=self._get_bool_env('OCR_ENABLE_USAGE_ADAPTATION', True),
                
                # Priority-based Resource Limits
                express_max_concurrent=self._get_int_env('OCR_EXPRESS_MAX_CONCURRENT', 4, min_val=1, max_val=8),
                standard_max_concurrent=self._get_int_env('OCR_STANDARD_MAX_CONCURRENT', 2, min_val=1, max_val=6),
                background_max_concurrent=self._get_int_env('OCR_BACKGROUND_MAX_CONCURRENT', 1, min_val=1, max_val=4),
                borrowing_threshold=self._get_float_env('OCR_BORROWING_THRESHOLD', 0.8, min_val=0.5, max_val=0.95),
                
                # PaddleOCR Performance Settings
                paddle_cpu_threads=self._get_int_env('OCR_PADDLE_CPU_THREADS', 4, min_val=1, max_val=8),
                memory_limit_mb=self._get_int_env('OCR_MEMORY_LIMIT_MB', 2048, min_val=512, max_val=6144),
                batch_size=self._get_int_env('OCR_BATCH_SIZE', 3, min_val=1, max_val=10),
                
                # Adaptive Behavior Settings
                usage_window_minutes=self._get_int_env('OCR_USAGE_WINDOW_MINUTES', 60, min_val=15, max_val=240),
                mode_switch_threshold=self._get_float_env('OCR_MODE_SWITCH_THRESHOLD', 0.7, min_val=0.5, max_val=0.9),
                bulk_operation_threshold=self._get_int_env('OCR_BULK_OPERATION_THRESHOLD', 10, min_val=5, max_val=50),
                
                # Railway Environment Limits
                railway_max_cpu_cores=self._get_int_env('RAILWAY_MAX_CPU_CORES', 8, min_val=1, max_val=16),
                railway_max_memory_gb=self._get_int_env('RAILWAY_MAX_MEMORY_GB', 8, min_val=1, max_val=32),
                
                # Performance Monitoring
                enable_performance_logging=self._get_bool_env('OCR_ENABLE_PERFORMANCE_LOGGING', True),
                metrics_collection_interval=self._get_int_env('OCR_METRICS_INTERVAL', 30, min_val=10, max_val=300),
                
                # Resource Cleanup
                cleanup_interval_minutes=self._get_int_env('OCR_CLEANUP_INTERVAL', 5, min_val=1, max_val=30),
                memory_cleanup_threshold=self._get_float_env('OCR_MEMORY_CLEANUP_THRESHOLD', 0.85, min_val=0.7, max_val=0.95)
            )
            
            return config
            
        except Exception as e:
            logger.error(f"Error loading OCR configuration: {e}")
            logger.info("Using default OCR configuration")
            return OCRResourceConfig()
    
    def _get_int_env(self, key: str, default: int, min_val: int = None, max_val: int = None) -> int:
        """Get integer environment variable with validation."""
        try:
            value = int(os.getenv(key, default))
            if min_val is not None and value < min_val:
                logger.warning(f"{key}={value} below minimum {min_val}, using minimum")
                return min_val
            if max_val is not None and value > max_val:
                logger.warning(f"{key}={value} above maximum {max_val}, using maximum")
                return max_val
            return value
        except (ValueError, TypeError):
            logger.warning(f"Invalid {key} value, using default {default}")
            return default
    
    def _get_float_env(self, key: str, default: float, min_val: float = None, max_val: float = None) -> float:
        """Get float environment variable with validation."""
        try:
            value = float(os.getenv(key, default))
            if min_val is not None and value < min_val:
                logger.warning(f"{key}={value} below minimum {min_val}, using minimum")
                return min_val
            if max_val is not None and value > max_val:
                logger.warning(f"{key}={value} above maximum {max_val}, using maximum")
                return max_val
            return value
        except (ValueError, TypeError):
            logger.warning(f"Invalid {key} value, using default {default}")
            return default
    
    def _get_bool_env(self, key: str, default: bool) -> bool:
        """Get boolean environment variable."""
        value = os.getenv(key, str(default)).lower()
        return value in ('true', '1', 'yes', 'on', 'enabled')
    
    def _validate_configuration(self) -> None:
        """Validate configuration for consistency and Railway limits."""
        config = self.config
        
        # Validate priority-based limits don't exceed Railway resources
        total_max_concurrent = (config.express_max_concurrent + 
                              config.standard_max_concurrent + 
                              config.background_max_concurrent)
        
        if total_max_concurrent > config.railway_max_cpu_cores * 2:
            logger.warning(
                f"Total max concurrent ({total_max_concurrent}) exceeds Railway CPU capacity. "
                f"Resource borrowing will manage actual allocation."
            )
        
        # Validate memory settings
        estimated_memory_usage = config.max_concurrent * config.memory_limit_mb
        railway_memory_mb = config.railway_max_memory_gb * 1024
        
        if estimated_memory_usage > railway_memory_mb * 0.8:  # Use 80% of available memory
            logger.warning(
                f"Estimated memory usage ({estimated_memory_usage}MB) may exceed Railway capacity "
                f"({railway_memory_mb}MB). Consider reducing memory_limit_mb or max_concurrent."
            )
        
        # Validate mode-specific settings
        if config.mode == OCRMode.BULK_HEAVY:
            if config.background_max_concurrent < 2:
                logger.info("BULK_HEAVY mode: Consider increasing background_max_concurrent for better throughput")
        
        elif config.mode == OCRMode.SINGLE_FOCUSED:
            if config.express_max_concurrent < 3:
                logger.info("SINGLE_FOCUSED mode: Consider increasing express_max_concurrent for faster response")
    
    def _log_configuration(self) -> None:
        """Log current configuration for debugging and monitoring."""
        config = self.config
        
        logger.info("🔧 OCR Configuration Loaded:")
        logger.info(f"  Mode: {config.mode.value}")
        logger.info(f"  Priority Limits - Express: {config.express_max_concurrent}, "
                   f"Standard: {config.standard_max_concurrent}, "
                   f"Background: {config.background_max_concurrent}")
        logger.info(f"  PaddleOCR - Threads: {config.paddle_cpu_threads}, "
                   f"Memory Limit: {config.memory_limit_mb}MB, "
                   f"Batch Size: {config.batch_size}")
        logger.info(f"  Resource Borrowing: {config.enable_priority_borrowing} "
                   f"(threshold: {config.borrowing_threshold:.1%})")
        logger.info(f"  Usage Adaptation: {config.enable_usage_adaptation}")
        logger.info(f"  Railway Limits - CPU: {config.railway_max_cpu_cores} cores, "
                   f"Memory: {config.railway_max_memory_gb}GB")
    
    def get_priority_for_operation(self, image_count: int) -> OCRPriority:
        """Determine priority level based on operation characteristics."""
        if image_count == 1:
            return OCRPriority.EXPRESS
        elif image_count <= self.config.bulk_operation_threshold:
            return OCRPriority.STANDARD
        else:
            return OCRPriority.BACKGROUND
    
    def get_max_concurrent_for_priority(self, priority: OCRPriority) -> int:
        """Get maximum concurrent operations for a priority level."""
        if priority == OCRPriority.EXPRESS:
            return self.config.express_max_concurrent
        elif priority == OCRPriority.STANDARD:
            return self.config.standard_max_concurrent
        else:
            return self.config.background_max_concurrent
    
    def get_paddle_ocr_config(self) -> Dict[str, Any]:
        """Get PaddleOCR configuration using tested settings from existing implementation."""
        # Use the exact tested settings from ocr_processor.py to maintain compatibility
        base_config = {
            'use_angle_cls': False,  # Disable angle classification to save memory
            'lang': 'en',  # Use English model (smaller than multilingual)
            'use_gpu': False,  # CPU only for Railway deployment
            'det_model_dir': None,  # Use default lightweight models
            'rec_model_dir': None,
            'cls_model_dir': None,
            'show_log': False,
            'use_space_char': True
        }
        
        # Only add Railway optimizations if explicitly enabled via environment variables
        if os.getenv('OCR_ENABLE_ADVANCED_OPTIMIZATIONS', 'false').lower() == 'true':
            # Advanced optimizations that can be enabled optionally
            base_config.update({
                'cpu_threads': self.config.paddle_cpu_threads,
                'enable_mkldnn': True,  # Intel optimization
                'use_tensorrt': False,  # Disable TensorRT (not available on Railway)
            })
            logger.info("🔧 Advanced PaddleOCR optimizations enabled via environment variable")
        
        return base_config
    
    def should_trigger_mode_switch(self, usage_stats: Dict[str, float]) -> Optional[OCRMode]:
        """
        Analyze usage statistics and determine if mode switch is beneficial.
        
        Args:
            usage_stats: Dict containing usage metrics like 'bulk_ratio', 'single_ratio', etc.
        
        Returns:
            New mode to switch to, or None if current mode is optimal
        """
        if not self.config.enable_usage_adaptation:
            return None
        
        bulk_ratio = usage_stats.get('bulk_ratio', 0.0)
        single_ratio = usage_stats.get('single_ratio', 0.0)
        
        current_mode = self.config.mode
        threshold = self.config.mode_switch_threshold
        
        # Switch to BULK_HEAVY if mostly bulk operations
        if bulk_ratio > threshold and current_mode != OCRMode.BULK_HEAVY:
            logger.info(f"Usage pattern suggests BULK_HEAVY mode (bulk ratio: {bulk_ratio:.1%})")
            return OCRMode.BULK_HEAVY
        
        # Switch to SINGLE_FOCUSED if mostly single operations
        elif single_ratio > threshold and current_mode != OCRMode.SINGLE_FOCUSED:
            logger.info(f"Usage pattern suggests SINGLE_FOCUSED mode (single ratio: {single_ratio:.1%})")
            return OCRMode.SINGLE_FOCUSED
        
        # Switch to BALANCED if mixed usage
        elif (bulk_ratio < threshold and single_ratio < threshold and 
              current_mode != OCRMode.BALANCED):
            logger.info(f"Usage pattern suggests BALANCED mode (mixed usage)")
            return OCRMode.BALANCED
        
        return None
    
    def update_mode(self, new_mode: OCRMode) -> None:
        """Update current OCR mode (runtime configuration change)."""
        old_mode = self.config.mode
        self.config.mode = new_mode
        logger.info(f"🔄 OCR mode changed: {old_mode.value} → {new_mode.value}")
    
    def get_memory_settings(self) -> Dict[str, int]:
        """Get memory-related settings for OCR operations."""
        return {
            'memory_limit_mb': self.config.memory_limit_mb,
            'cleanup_threshold': self.config.memory_cleanup_threshold,
            'cleanup_interval_minutes': self.config.cleanup_interval_minutes,
            'max_memory_mb': self.config.railway_max_memory_gb * 1024
        }
    
    def export_configuration(self) -> Dict[str, Any]:
        """Export current configuration for debugging and monitoring."""
        return {
            'mode': self.config.mode.value,
            'resource_limits': {
                'express_max': self.config.express_max_concurrent,
                'standard_max': self.config.standard_max_concurrent,
                'background_max': self.config.background_max_concurrent,
                'borrowing_enabled': self.config.enable_priority_borrowing,
                'borrowing_threshold': self.config.borrowing_threshold
            },
            'paddle_ocr': {
                'cpu_threads': self.config.paddle_cpu_threads,
                'memory_limit_mb': self.config.memory_limit_mb,
                'batch_size': self.config.batch_size
            },
            'railway_limits': {
                'max_cpu_cores': self.config.railway_max_cpu_cores,
                'max_memory_gb': self.config.railway_max_memory_gb
            },
            'adaptive_settings': {
                'usage_adaptation': self.config.enable_usage_adaptation,
                'usage_window_minutes': self.config.usage_window_minutes,
                'mode_switch_threshold': self.config.mode_switch_threshold,
                'bulk_threshold': self.config.bulk_operation_threshold
            }
        }


# Global configuration instance
_config_manager: Optional[OCRConfigManager] = None


def get_ocr_config() -> OCRConfigManager:
    """Get global OCR configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = OCRConfigManager()
    return _config_manager


def reload_ocr_config() -> OCRConfigManager:
    """Reload OCR configuration from environment variables."""
    global _config_manager
    _config_manager = OCRConfigManager()
    return _config_manager