#!/usr/bin/env python3
"""
OCR Resource Manager for MKW Stats Bot
Implements priority-based semaphore system with dynamic resource borrowing
"""

import asyncio
import logging
import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from datetime import datetime, timedelta

from .ocr_config_manager import get_ocr_config, OCRPriority, OCRMode

logger = logging.getLogger(__name__)


@dataclass
class OCRRequest:
    """Represents an OCR processing request with priority and metadata."""
    request_id: str
    priority: OCRPriority
    image_count: int
    guild_id: int
    user_id: int
    submitted_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def wait_time(self) -> float:
        """Get wait time in seconds."""
        if self.started_at:
            return (self.started_at - self.submitted_at).total_seconds()
        return (datetime.now() - self.submitted_at).total_seconds()
    
    @property
    def processing_time(self) -> Optional[float]:
        """Get processing time in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class ResourceUsageStats:
    """Tracks resource usage statistics for adaptive behavior."""
    total_requests: int = 0
    single_image_requests: int = 0
    bulk_requests: int = 0
    express_requests: int = 0
    standard_requests: int = 0
    background_requests: int = 0
    
    total_processing_time: float = 0.0
    total_wait_time: float = 0.0
    
    borrowing_events: int = 0
    mode_switches: int = 0
    
    window_start: datetime = field(default_factory=datetime.now)
    
    @property
    def bulk_ratio(self) -> float:
        """Get ratio of bulk requests to total requests."""
        return self.bulk_requests / max(self.total_requests, 1)
    
    @property
    def single_ratio(self) -> float:
        """Get ratio of single image requests to total requests."""
        return self.single_image_requests / max(self.total_requests, 1)
    
    @property
    def average_wait_time(self) -> float:
        """Get average wait time in seconds."""
        return self.total_wait_time / max(self.total_requests, 1)
    
    @property
    def average_processing_time(self) -> float:
        """Get average processing time in seconds."""
        return self.total_processing_time / max(self.total_requests, 1)


class PrioritySemaphore:
    """
    Advanced semaphore with priority support and resource borrowing capabilities.
    Allows higher priority operations to borrow unused resources from lower priority tiers.
    """
    
    def __init__(self, express_limit: int, standard_limit: int, background_limit: int,
                 borrowing_enabled: bool = True, borrowing_threshold: float = 0.8):
        """
        Initialize priority semaphore with resource limits for each tier.
        
        Args:
            express_limit: Maximum concurrent EXPRESS priority operations
            standard_limit: Maximum concurrent STANDARD priority operations  
            background_limit: Maximum concurrent BACKGROUND priority operations
            borrowing_enabled: Whether to allow resource borrowing between tiers
            borrowing_threshold: Utilization threshold to trigger borrowing (0.0-1.0)
        """
        self.express_limit = express_limit
        self.standard_limit = standard_limit
        self.background_limit = background_limit
        self.borrowing_enabled = borrowing_enabled
        self.borrowing_threshold = borrowing_threshold
        
        # Create individual semaphores for each priority level
        self.express_semaphore = asyncio.Semaphore(express_limit)
        self.standard_semaphore = asyncio.Semaphore(standard_limit)
        self.background_semaphore = asyncio.Semaphore(background_limit)
        
        # Track current usage for each priority level
        self.express_active = 0
        self.standard_active = 0
        self.background_active = 0
        
        # Lock for atomic operations on usage counters
        self._lock = asyncio.Lock()
        
        # Track borrowing events
        self.borrowing_stats = {
            'express_borrowed': 0,
            'standard_borrowed': 0,
            'total_borrowing_events': 0
        }
    
    async def acquire(self, priority: OCRPriority) -> 'PrioritySemaphoreContext':
        """
        Acquire semaphore for the specified priority level.
        Implements resource borrowing logic for optimal resource utilization.
        """
        start_time = time.time()
        
        if priority == OCRPriority.EXPRESS:
            # EXPRESS: Try direct acquisition first, then borrowing
            if self.express_semaphore.locked():
                await self._try_borrowing_for_express()
            
            await self.express_semaphore.acquire()
            async with self._lock:
                self.express_active += 1
                
        elif priority == OCRPriority.STANDARD:
            # STANDARD: Try direct acquisition first, then borrowing
            if self.standard_semaphore.locked():
                await self._try_borrowing_for_standard()
            
            await self.standard_semaphore.acquire()
            async with self._lock:
                self.standard_active += 1
                
        else:  # BACKGROUND
            # BACKGROUND: Direct acquisition only (lowest priority)
            await self.background_semaphore.acquire()
            async with self._lock:
                self.background_active += 1
        
        wait_time = time.time() - start_time
        logger.debug(f"Acquired {priority.value} semaphore after {wait_time:.2f}s wait")
        
        return PrioritySemaphoreContext(self, priority, wait_time)
    
    async def _try_borrowing_for_express(self) -> bool:
        """Try to borrow resources for EXPRESS priority operations."""
        if not self.borrowing_enabled:
            return False
        
        async with self._lock:
            # Calculate current utilization for lower priority tiers
            standard_utilization = self.standard_active / max(self.standard_limit, 1)
            background_utilization = self.background_active / max(self.background_limit, 1)
            
            # Try borrowing from STANDARD tier first
            if (standard_utilization < self.borrowing_threshold and 
                self.standard_limit > 1 and self.standard_active < self.standard_limit):
                
                # Temporarily reduce STANDARD limit to allow EXPRESS borrowing
                self.standard_limit -= 1
                self.express_limit += 1
                
                # Update semaphores
                self.express_semaphore._value += 1
                self.standard_semaphore._value = max(0, self.standard_semaphore._value - 1)
                
                self.borrowing_stats['express_borrowed'] += 1
                self.borrowing_stats['total_borrowing_events'] += 1
                
                logger.debug(f"EXPRESS borrowed 1 resource from STANDARD "
                           f"(utilization: {standard_utilization:.1%})")
                return True
            
            # Try borrowing from BACKGROUND tier if STANDARD borrowing failed
            elif (background_utilization < self.borrowing_threshold and 
                  self.background_limit > 1 and self.background_active < self.background_limit):
                
                # Temporarily reduce BACKGROUND limit to allow EXPRESS borrowing
                self.background_limit -= 1
                self.express_limit += 1
                
                # Update semaphores
                self.express_semaphore._value += 1
                self.background_semaphore._value = max(0, self.background_semaphore._value - 1)
                
                self.borrowing_stats['express_borrowed'] += 1
                self.borrowing_stats['total_borrowing_events'] += 1
                
                logger.debug(f"EXPRESS borrowed 1 resource from BACKGROUND "
                           f"(utilization: {background_utilization:.1%})")
                return True
        
        return False
    
    async def _try_borrowing_for_standard(self) -> bool:
        """Try to borrow resources for STANDARD priority operations."""
        if not self.borrowing_enabled:
            return False
        
        async with self._lock:
            # Calculate current utilization for BACKGROUND tier
            background_utilization = self.background_active / max(self.background_limit, 1)
            
            # Try borrowing from BACKGROUND tier
            if (background_utilization < self.borrowing_threshold and 
                self.background_limit > 1 and self.background_active < self.background_limit):
                
                # Temporarily reduce BACKGROUND limit to allow STANDARD borrowing
                self.background_limit -= 1
                self.standard_limit += 1
                
                # Update semaphores
                self.standard_semaphore._value += 1
                self.background_semaphore._value = max(0, self.background_semaphore._value - 1)
                
                self.borrowing_stats['standard_borrowed'] += 1
                self.borrowing_stats['total_borrowing_events'] += 1
                
                logger.debug(f"STANDARD borrowed 1 resource from BACKGROUND "
                           f"(utilization: {background_utilization:.1%})")
                return True
        
        return False
    
    async def release(self, priority: OCRPriority) -> None:
        """Release semaphore for the specified priority level."""
        async with self._lock:
            if priority == OCRPriority.EXPRESS:
                self.express_active -= 1
                self.express_semaphore.release()
            elif priority == OCRPriority.STANDARD:
                self.standard_active -= 1
                self.standard_semaphore.release()
            else:  # BACKGROUND
                self.background_active -= 1
                self.background_semaphore.release()
        
        logger.debug(f"Released {priority.value} semaphore")
    
    def get_utilization_stats(self) -> Dict[str, float]:
        """Get current utilization statistics for all priority levels."""
        return {
            'express_utilization': self.express_active / max(self.express_limit, 1),
            'standard_utilization': self.standard_active / max(self.standard_limit, 1),
            'background_utilization': self.background_active / max(self.background_limit, 1),
            'total_active': self.express_active + self.standard_active + self.background_active,
            'total_capacity': self.express_limit + self.standard_limit + self.background_limit
        }
    
    def get_borrowing_stats(self) -> Dict[str, int]:
        """Get resource borrowing statistics."""
        return self.borrowing_stats.copy()


class PrioritySemaphoreContext:
    """Context manager for priority semaphore operations."""
    
    def __init__(self, semaphore: PrioritySemaphore, priority: OCRPriority, wait_time: float):
        self.semaphore = semaphore
        self.priority = priority
        self.wait_time = wait_time
        self.acquired_at = time.time()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.semaphore.release(self.priority)
        processing_time = time.time() - self.acquired_at
        logger.debug(f"Released {self.priority.value} semaphore after {processing_time:.2f}s processing")


class OCRResourceManager:
    """
    Advanced OCR resource manager with priority-based allocation and adaptive behavior.
    Implements dynamic resource borrowing and usage pattern detection.
    """
    
    def __init__(self):
        """Initialize OCR resource manager with configuration-based settings."""
        self.config = get_ocr_config()
        self.config_obj = self.config.config
        
        # Initialize priority semaphore system
        self.semaphore = PrioritySemaphore(
            express_limit=self.config_obj.express_max_concurrent,
            standard_limit=self.config_obj.standard_max_concurrent,
            background_limit=self.config_obj.background_max_concurrent,
            borrowing_enabled=self.config_obj.enable_priority_borrowing,
            borrowing_threshold=self.config_obj.borrowing_threshold
        )
        
        # Usage tracking and statistics
        self.usage_stats = ResourceUsageStats()
        self.active_requests: Dict[str, OCRRequest] = {}
        self.completed_requests: deque = deque(maxlen=1000)  # Keep last 1000 requests
        
        # Thread-safe request ID generation
        self._request_counter = 0
        self._request_lock = threading.Lock()
        
        # Periodic tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("🚀 OCR Resource Manager initialized")
        logger.info(f"  Priority Limits - Express: {self.config_obj.express_max_concurrent}, "
                   f"Standard: {self.config_obj.standard_max_concurrent}, "
                   f"Background: {self.config_obj.background_max_concurrent}")
        logger.info(f"  Resource Borrowing: {self.config_obj.enable_priority_borrowing}")
        logger.info(f"  Usage Adaptation: {self.config_obj.enable_usage_adaptation}")
    
    def start_monitoring(self) -> None:
        """Start background monitoring and cleanup tasks."""
        if self.config_obj.enable_performance_logging:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("📊 Started OCR resource monitoring and cleanup tasks")
    
    def stop_monitoring(self) -> None:
        """Stop background monitoring and cleanup tasks."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        logger.info("⏹️ Stopped OCR resource monitoring and cleanup tasks")
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        with self._request_lock:
            self._request_counter += 1
            return f"ocr_{self._request_counter}_{int(time.time())}"
    
    def create_request(self, image_count: int, guild_id: int, user_id: int) -> OCRRequest:
        """Create new OCR request with appropriate priority."""
        priority = self.config.get_priority_for_operation(image_count)
        request_id = self._generate_request_id()
        
        request = OCRRequest(
            request_id=request_id,
            priority=priority,
            image_count=image_count,
            guild_id=guild_id,
            user_id=user_id
        )
        
        self.active_requests[request_id] = request
        logger.debug(f"Created OCR request {request_id} with {priority.value} priority ({image_count} images)")
        
        return request
    
    @asynccontextmanager
    async def acquire_resources(self, request: OCRRequest):
        """
        Acquire OCR processing resources for a request.
        Implements priority-based allocation with dynamic borrowing.
        """
        request.started_at = datetime.now()
        
        try:
            # Acquire semaphore with priority-based allocation
            async with await self.semaphore.acquire(request.priority) as context:
                logger.info(f"🔓 Acquired resources for {request.request_id} "
                           f"({request.priority.value}, {request.image_count} images, "
                           f"wait: {context.wait_time:.2f}s)")
                
                # Update usage statistics
                self._update_usage_stats(request, context.wait_time)
                
                yield context
                
        finally:
            # Mark request as completed
            request.completed_at = datetime.now()
            
            # Move to completed requests
            if request.request_id in self.active_requests:
                del self.active_requests[request.request_id]
                self.completed_requests.append(request)
            
            # Update processing time statistics
            if request.processing_time:
                self.usage_stats.total_processing_time += request.processing_time
            
            logger.info(f"🔒 Released resources for {request.request_id} "
                       f"(processing: {request.processing_time:.2f}s)")
    
    def _update_usage_stats(self, request: OCRRequest, wait_time: float) -> None:
        """Update usage statistics with new request data."""
        self.usage_stats.total_requests += 1
        self.usage_stats.total_wait_time += wait_time
        
        # Track request types
        if request.image_count == 1:
            self.usage_stats.single_image_requests += 1
        elif request.image_count >= self.config_obj.bulk_operation_threshold:
            self.usage_stats.bulk_requests += 1
        
        # Track priority distribution
        if request.priority == OCRPriority.EXPRESS:
            self.usage_stats.express_requests += 1
        elif request.priority == OCRPriority.STANDARD:
            self.usage_stats.standard_requests += 1
        else:
            self.usage_stats.background_requests += 1
    
    async def _monitoring_loop(self) -> None:
        """Background task for performance monitoring and adaptive behavior."""
        try:
            while True:
                await asyncio.sleep(self.config_obj.metrics_collection_interval)
                
                # Collect current metrics
                utilization = self.semaphore.get_utilization_stats()
                borrowing = self.semaphore.get_borrowing_stats()
                
                # Log performance metrics
                logger.info("📊 OCR Resource Metrics:")
                logger.info(f"  Active Requests: {len(self.active_requests)}")
                logger.info(f"  Utilization - Express: {utilization['express_utilization']:.1%}, "
                           f"Standard: {utilization['standard_utilization']:.1%}, "
                           f"Background: {utilization['background_utilization']:.1%}")
                logger.info(f"  Usage Stats - Total: {self.usage_stats.total_requests}, "
                           f"Bulk Ratio: {self.usage_stats.bulk_ratio:.1%}, "
                           f"Avg Wait: {self.usage_stats.average_wait_time:.2f}s")
                logger.info(f"  Borrowing Events: {borrowing['total_borrowing_events']}")
                
                # Check for adaptive mode switching
                if self.config_obj.enable_usage_adaptation:
                    await self._check_adaptive_mode_switch()
                
        except asyncio.CancelledError:
            logger.debug("Monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
    
    async def _check_adaptive_mode_switch(self) -> None:
        """Check if current usage patterns suggest a mode switch."""
        # Only check if enough data has been collected
        if self.usage_stats.total_requests < 10:
            return
        
        # Check if usage window has elapsed
        window_elapsed = datetime.now() - self.usage_stats.window_start
        if window_elapsed.total_seconds() < self.config_obj.usage_window_minutes * 60:
            return
        
        # Prepare usage statistics for analysis
        usage_metrics = {
            'bulk_ratio': self.usage_stats.bulk_ratio,
            'single_ratio': self.usage_stats.single_ratio,
            'average_wait_time': self.usage_stats.average_wait_time,
            'total_requests': self.usage_stats.total_requests
        }
        
        # Check if mode switch is recommended
        recommended_mode = self.config.should_trigger_mode_switch(usage_metrics)
        
        if recommended_mode:
            logger.info(f"🔄 Adaptive mode switch recommended: {recommended_mode.value}")
            
            # Update configuration
            self.config.update_mode(recommended_mode)
            
            # Reset usage statistics for new window
            self.usage_stats = ResourceUsageStats()
            self.usage_stats.mode_switches += 1
    
    async def _cleanup_loop(self) -> None:
        """Background task for resource cleanup and garbage collection."""
        try:
            while True:
                await asyncio.sleep(self.config_obj.cleanup_interval_minutes * 60)
                
                # Clean up old completed requests
                cutoff_time = datetime.now() - timedelta(hours=1)
                
                # Remove old requests from completed queue
                while (self.completed_requests and 
                       self.completed_requests[0].completed_at and
                       self.completed_requests[0].completed_at < cutoff_time):
                    self.completed_requests.popleft()
                
                # Force garbage collection if memory usage is high
                import gc
                import psutil
                
                try:
                    process = psutil.Process()
                    memory_percent = process.memory_percent()
                    
                    if memory_percent > self.config_obj.memory_cleanup_threshold * 100:
                        logger.info(f"🧹 Memory usage high ({memory_percent:.1f}%), running cleanup")
                        gc.collect()
                        
                except ImportError:
                    # psutil not available, run periodic cleanup anyway
                    gc.collect()
                
                logger.debug("🧹 Completed resource cleanup cycle")
                
        except asyncio.CancelledError:
            logger.debug("Cleanup loop cancelled")
        except Exception as e:
            logger.error(f"Error in cleanup loop: {e}")
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get comprehensive current statistics."""
        utilization = self.semaphore.get_utilization_stats()
        borrowing = self.semaphore.get_borrowing_stats()
        
        return {
            'configuration': self.config.export_configuration(),
            'active_requests': len(self.active_requests),
            'completed_requests': len(self.completed_requests),
            'utilization': utilization,
            'borrowing': borrowing,
            'usage_stats': {
                'total_requests': self.usage_stats.total_requests,
                'bulk_ratio': self.usage_stats.bulk_ratio,
                'single_ratio': self.usage_stats.single_ratio,
                'average_wait_time': self.usage_stats.average_wait_time,
                'average_processing_time': self.usage_stats.average_processing_time,
                'mode_switches': self.usage_stats.mode_switches
            }
        }


# Global resource manager instance
_resource_manager: Optional[OCRResourceManager] = None


def get_ocr_resource_manager() -> OCRResourceManager:
    """Get global OCR resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = OCRResourceManager()
    return _resource_manager


def initialize_ocr_resource_manager() -> OCRResourceManager:
    """Initialize and start OCR resource manager."""
    manager = get_ocr_resource_manager()
    manager.start_monitoring()
    return manager


def shutdown_ocr_resource_manager() -> None:
    """Shutdown OCR resource manager."""
    global _resource_manager
    if _resource_manager:
        _resource_manager.stop_monitoring()
        _resource_manager = None