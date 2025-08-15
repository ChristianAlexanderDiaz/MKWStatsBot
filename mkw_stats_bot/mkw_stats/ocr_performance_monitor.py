#!/usr/bin/env python3
"""
OCR Performance Monitor for MKW Stats Bot
Real-time performance tracking, metrics collection, and adaptive optimization
"""

import asyncio
import logging
import time
import threading
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from .ocr_config_manager import get_ocr_config, OCRPriority, OCRMode

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for OCR operations."""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Request metrics
    total_requests: int = 0
    active_requests: int = 0
    queued_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    
    # Timing metrics
    average_wait_time: float = 0.0
    average_processing_time: float = 0.0
    peak_wait_time: float = 0.0
    peak_processing_time: float = 0.0
    
    # Resource utilization
    express_utilization: float = 0.0
    standard_utilization: float = 0.0
    background_utilization: float = 0.0
    overall_utilization: float = 0.0
    
    # Memory and CPU metrics
    memory_usage_mb: float = 0.0
    memory_utilization: float = 0.0
    cpu_utilization: float = 0.0
    
    # Quality metrics
    success_rate: float = 0.0
    throughput_requests_per_minute: float = 0.0
    
    # Adaptive behavior metrics
    borrowing_events: int = 0
    mode_switches: int = 0
    current_mode: str = "balanced"


@dataclass
class OperationProfile:
    """Detailed profile of an OCR operation."""
    operation_id: str
    priority: OCRPriority
    image_count: int
    guild_id: int
    user_id: int
    
    # Timing breakdown
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Performance data
    wait_time: float = 0.0
    processing_time: float = 0.0
    memory_peak_mb: float = 0.0
    
    # Results
    success: bool = False
    error_message: Optional[str] = None
    players_detected: int = 0
    confidence_score: float = 0.0
    
    @property
    def total_time(self) -> float:
        """Get total operation time from queue to completion."""
        if self.queued_at and self.completed_at:
            return (self.completed_at - self.queued_at).total_seconds()
        return 0.0


class AdaptiveBehaviorAnalyzer:
    """Analyzes performance patterns and suggests optimizations."""
    
    def __init__(self, window_minutes: int = 60):
        self.window_minutes = window_minutes
        self.performance_history: deque = deque(maxlen=1440)  # 24 hours of minute-level data
        self.optimization_suggestions: List[str] = []
        
        # Pattern detection thresholds
        self.high_wait_time_threshold = 10.0  # seconds
        self.low_utilization_threshold = 0.3  # 30%
        self.high_utilization_threshold = 0.85  # 85%
        self.bulk_heavy_threshold = 0.7  # 70% bulk operations
        self.single_heavy_threshold = 0.8  # 80% single operations
    
    def add_performance_sample(self, metrics: PerformanceMetrics) -> None:
        """Add performance sample to analysis window."""
        self.performance_history.append(metrics)
        
        # Clean old data outside window
        cutoff_time = datetime.now() - timedelta(minutes=self.window_minutes)
        while (self.performance_history and 
               self.performance_history[0].timestamp < cutoff_time):
            self.performance_history.popleft()
    
    def analyze_patterns(self) -> Dict[str, Any]:
        """Analyze performance patterns and generate insights."""
        if len(self.performance_history) < 5:
            return {'status': 'insufficient_data'}
        
        # Calculate aggregated metrics
        recent_metrics = list(self.performance_history)[-min(30, len(self.performance_history)):]
        
        avg_wait_time = sum(m.average_wait_time for m in recent_metrics) / len(recent_metrics)
        avg_utilization = sum(m.overall_utilization for m in recent_metrics) / len(recent_metrics)
        avg_success_rate = sum(m.success_rate for m in recent_metrics) / len(recent_metrics)
        avg_throughput = sum(m.throughput_requests_per_minute for m in recent_metrics) / len(recent_metrics)
        
        # Detect performance issues
        issues = []
        suggestions = []
        
        if avg_wait_time > self.high_wait_time_threshold:
            issues.append("high_wait_times")
            suggestions.append("Consider increasing resource limits or enabling resource borrowing")
        
        if avg_utilization < self.low_utilization_threshold:
            issues.append("low_utilization")
            suggestions.append("Resources may be over-provisioned; consider reducing limits to save costs")
        
        if avg_utilization > self.high_utilization_threshold:
            issues.append("high_utilization")
            suggestions.append("Resources may be under-provisioned; consider increasing limits")
        
        if avg_success_rate < 0.95:
            issues.append("low_success_rate")
            suggestions.append("OCR failures detected; check image quality or model configuration")
        
        # Detect usage patterns
        mode_distribution = defaultdict(int)
        for metrics in recent_metrics:
            mode_distribution[metrics.current_mode] += 1
        
        dominant_mode = max(mode_distribution.items(), key=lambda x: x[1])[0] if mode_distribution else "unknown"
        
        pattern_analysis = {
            'timeframe': f"Last {len(recent_metrics)} minutes",
            'average_wait_time': avg_wait_time,
            'average_utilization': avg_utilization,
            'average_success_rate': avg_success_rate,
            'average_throughput': avg_throughput,
            'dominant_mode': dominant_mode,
            'detected_issues': issues,
            'optimization_suggestions': suggestions,
            'trend': self._detect_trend(recent_metrics)
        }
        
        return pattern_analysis
    
    def _detect_trend(self, metrics: List[PerformanceMetrics]) -> str:
        """Detect performance trend (improving, degrading, stable)."""
        if len(metrics) < 10:
            return "insufficient_data"
        
        # Compare first half vs second half
        mid_point = len(metrics) // 2
        first_half = metrics[:mid_point]
        second_half = metrics[mid_point:]
        
        first_avg_wait = sum(m.average_wait_time for m in first_half) / len(first_half)
        second_avg_wait = sum(m.average_wait_time for m in second_half) / len(second_half)
        
        first_avg_util = sum(m.overall_utilization for m in first_half) / len(first_half)
        second_avg_util = sum(m.overall_utilization for m in second_half) / len(second_half)
        
        # Determine trend based on wait time and utilization changes
        wait_change = (second_avg_wait - first_avg_wait) / max(first_avg_wait, 0.1)
        util_change = (second_avg_util - first_avg_util) / max(first_avg_util, 0.1)
        
        if wait_change > 0.2:  # 20% increase in wait time
            return "degrading"
        elif wait_change < -0.2:  # 20% decrease in wait time
            return "improving"
        else:
            return "stable"
    
    def suggest_mode_optimization(self, current_stats: Dict[str, Any]) -> Optional[OCRMode]:
        """Suggest optimal mode based on current usage patterns."""
        usage_stats = current_stats.get('usage_stats', {})
        
        bulk_ratio = usage_stats.get('bulk_ratio', 0.0)
        single_ratio = usage_stats.get('single_ratio', 0.0)
        avg_wait_time = usage_stats.get('average_wait_time', 0.0)
        
        current_mode_str = current_stats.get('configuration', {}).get('mode', 'balanced')
        try:
            current_mode = OCRMode(current_mode_str)
        except ValueError:
            current_mode = OCRMode.BALANCED
        
        # Suggest mode based on usage patterns and performance
        if bulk_ratio > self.bulk_heavy_threshold and current_mode != OCRMode.BULK_HEAVY:
            if avg_wait_time > self.high_wait_time_threshold:
                return OCRMode.BULK_HEAVY
        
        elif single_ratio > self.single_heavy_threshold and current_mode != OCRMode.SINGLE_FOCUSED:
            if avg_wait_time > 5.0:  # Lower threshold for single operations
                return OCRMode.SINGLE_FOCUSED
        
        elif (bulk_ratio < self.bulk_heavy_threshold and 
              single_ratio < self.single_heavy_threshold and 
              current_mode != OCRMode.BALANCED):
            return OCRMode.BALANCED
        
        return None


class PerformanceCollector:
    """Collects system and application performance metrics."""
    
    def __init__(self):
        self.start_time = time.time()
        self.total_operations = 0
        self.successful_operations = 0
        self.failed_operations = 0
        
        # Operation tracking
        self.active_operations: Dict[str, OperationProfile] = {}
        self.completed_operations: deque = deque(maxlen=1000)
        
        # Performance sampling
        self.last_sample_time = time.time()
        self.request_count_last_minute = 0
        
        # Memory and CPU tracking
        self._system_monitor_available = self._check_system_monitoring()
    
    def _check_system_monitoring(self) -> bool:
        """Check if system monitoring libraries are available."""
        try:
            import psutil
            return True
        except ImportError:
            logger.warning("psutil not available - system metrics will be limited")
            return False
    
    def start_operation(self, operation_id: str, priority: OCRPriority, 
                       image_count: int, guild_id: int, user_id: int) -> OperationProfile:
        """Start tracking a new OCR operation."""
        profile = OperationProfile(
            operation_id=operation_id,
            priority=priority,
            image_count=image_count,
            guild_id=guild_id,
            user_id=user_id,
            queued_at=datetime.now()
        )
        
        self.active_operations[operation_id] = profile
        self.total_operations += 1
        
        logger.debug(f"Started tracking operation {operation_id}")
        return profile
    
    def mark_operation_started(self, operation_id: str) -> None:
        """Mark operation as started processing."""
        if operation_id in self.active_operations:
            profile = self.active_operations[operation_id]
            profile.started_at = datetime.now()
            
            if profile.queued_at:
                profile.wait_time = (profile.started_at - profile.queued_at).total_seconds()
    
    def complete_operation(self, operation_id: str, success: bool, 
                          players_detected: int = 0, confidence_score: float = 0.0, 
                          error_message: str = None) -> None:
        """Complete operation tracking."""
        if operation_id not in self.active_operations:
            return
        
        profile = self.active_operations[operation_id]
        profile.completed_at = datetime.now()
        profile.success = success
        profile.players_detected = players_detected
        profile.confidence_score = confidence_score
        profile.error_message = error_message
        
        if profile.started_at:
            profile.processing_time = (profile.completed_at - profile.started_at).total_seconds()
        
        # Update counters
        if success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1
        
        # Move to completed operations
        self.completed_operations.append(profile)
        del self.active_operations[operation_id]
        
        logger.debug(f"Completed tracking operation {operation_id} (success: {success})")
    
    def collect_current_metrics(self, resource_stats: Dict[str, Any]) -> PerformanceMetrics:
        """Collect current performance metrics."""
        current_time = time.time()
        
        # Calculate request rate
        time_diff = current_time - self.last_sample_time
        if time_diff >= 60:  # Update every minute
            self.request_count_last_minute = len([
                op for op in self.completed_operations 
                if op.completed_at and (datetime.now() - op.completed_at).total_seconds() < 60
            ])
            self.last_sample_time = current_time
        
        # Calculate timing metrics from recent operations
        recent_ops = [op for op in self.completed_operations 
                     if op.completed_at and (datetime.now() - op.completed_at).total_seconds() < 300]
        
        if recent_ops:
            avg_wait = sum(op.wait_time for op in recent_ops) / len(recent_ops)
            avg_processing = sum(op.processing_time for op in recent_ops) / len(recent_ops)
            peak_wait = max(op.wait_time for op in recent_ops)
            peak_processing = max(op.processing_time for op in recent_ops)
        else:
            avg_wait = avg_processing = peak_wait = peak_processing = 0.0
        
        # Get system metrics if available
        memory_usage = memory_utilization = cpu_utilization = 0.0
        
        if self._system_monitor_available:
            try:
                import psutil
                process = psutil.Process()
                
                memory_info = process.memory_info()
                memory_usage = memory_info.rss / (1024 * 1024)  # MB
                
                # System memory utilization
                system_memory = psutil.virtual_memory()
                memory_utilization = system_memory.percent / 100.0
                
                # CPU utilization (average over last interval)
                cpu_utilization = process.cpu_percent() / 100.0
                
            except Exception as e:
                logger.debug(f"Error collecting system metrics: {e}")
        
        # Extract resource utilization from stats
        utilization = resource_stats.get('utilization', {})
        
        # Calculate success rate
        total_ops = self.successful_operations + self.failed_operations
        success_rate = self.successful_operations / max(total_ops, 1)
        
        # Get current mode
        current_mode = resource_stats.get('configuration', {}).get('mode', 'balanced')
        
        return PerformanceMetrics(
            total_requests=self.total_operations,
            active_requests=len(self.active_operations),
            queued_requests=len([op for op in self.active_operations.values() if not op.started_at]),
            completed_requests=len(self.completed_operations),
            failed_requests=self.failed_operations,
            
            average_wait_time=avg_wait,
            average_processing_time=avg_processing,
            peak_wait_time=peak_wait,
            peak_processing_time=peak_processing,
            
            express_utilization=utilization.get('express_utilization', 0.0),
            standard_utilization=utilization.get('standard_utilization', 0.0),
            background_utilization=utilization.get('background_utilization', 0.0),
            overall_utilization=utilization.get('total_active', 0) / max(utilization.get('total_capacity', 1), 1),
            
            memory_usage_mb=memory_usage,
            memory_utilization=memory_utilization,
            cpu_utilization=cpu_utilization,
            
            success_rate=success_rate,
            throughput_requests_per_minute=self.request_count_last_minute,
            
            borrowing_events=resource_stats.get('borrowing', {}).get('total_borrowing_events', 0),
            mode_switches=resource_stats.get('usage_stats', {}).get('mode_switches', 0),
            current_mode=current_mode
        )


class OCRPerformanceMonitor:
    """
    Comprehensive OCR performance monitoring system.
    Tracks metrics, analyzes patterns, and provides optimization recommendations.
    """
    
    def __init__(self):
        """Initialize performance monitor."""
        self.config = get_ocr_config()
        self.collector = PerformanceCollector()
        self.analyzer = AdaptiveBehaviorAnalyzer(
            window_minutes=self.config.config.usage_window_minutes
        )
        
        # Monitoring state
        self.monitoring_active = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # Metrics storage
        self.metrics_history: deque = deque(maxlen=1440)  # 24 hours
        self.performance_reports: List[Dict[str, Any]] = []
        
        logger.info("📊 OCR Performance Monitor initialized")
    
    def start_monitoring(self) -> None:
        """Start performance monitoring."""
        if not self.monitoring_active:
            self.monitoring_active = True
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("🚀 Performance monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        self.monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
        logger.info("⏹️ Performance monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        try:
            while self.monitoring_active:
                await asyncio.sleep(self.config.config.metrics_collection_interval)
                
                # Collect current metrics (this will be called from resource manager)
                # await self._collect_and_analyze()
                
        except asyncio.CancelledError:
            logger.debug("Performance monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in performance monitoring loop: {e}")
    
    async def collect_and_analyze(self, resource_stats: Dict[str, Any]) -> None:
        """Collect metrics and perform analysis."""
        try:
            # Collect current performance metrics
            metrics = self.collector.collect_current_metrics(resource_stats)
            
            # Store metrics
            self.metrics_history.append(metrics)
            
            # Add to analyzer
            self.analyzer.add_performance_sample(metrics)
            
            # Perform pattern analysis
            if len(self.metrics_history) % 10 == 0:  # Every 10 samples
                pattern_analysis = self.analyzer.analyze_patterns()
                
                if pattern_analysis.get('status') != 'insufficient_data':
                    logger.info("🔍 Performance Analysis:")
                    logger.info(f"  Trend: {pattern_analysis.get('trend', 'unknown')}")
                    logger.info(f"  Average Wait Time: {pattern_analysis.get('average_wait_time', 0):.2f}s")
                    logger.info(f"  Average Utilization: {pattern_analysis.get('average_utilization', 0):.1%}")
                    
                    issues = pattern_analysis.get('detected_issues', [])
                    if issues:
                        logger.warning(f"  Detected Issues: {', '.join(issues)}")
                    
                    suggestions = pattern_analysis.get('optimization_suggestions', [])
                    if suggestions:
                        logger.info(f"  Suggestions: {'; '.join(suggestions[:2])}")  # Show first 2
                
                # Store analysis report
                self.performance_reports.append({
                    'timestamp': datetime.now().isoformat(),
                    'metrics': asdict(metrics),
                    'analysis': pattern_analysis
                })
                
                # Keep only last 24 reports
                self.performance_reports = self.performance_reports[-24:]
        
        except Exception as e:
            logger.error(f"Error in collect_and_analyze: {e}")
    
    @asynccontextmanager
    async def track_operation(self, operation_id: str, priority: OCRPriority, 
                             image_count: int, guild_id: int, user_id: int):
        """Context manager for tracking OCR operations."""
        # Start tracking
        profile = self.collector.start_operation(
            operation_id, priority, image_count, guild_id, user_id
        )
        
        try:
            yield profile
            
            # Mark as successful if no exception
            self.collector.complete_operation(operation_id, success=True)
            
        except Exception as e:
            # Mark as failed
            self.collector.complete_operation(
                operation_id, success=False, error_message=str(e)
            )
            raise
    
    def mark_operation_started(self, operation_id: str) -> None:
        """Mark operation as started processing."""
        self.collector.mark_operation_started(operation_id)
    
    def update_operation_results(self, operation_id: str, players_detected: int, 
                                confidence_score: float) -> None:
        """Update operation with OCR results."""
        if operation_id in self.collector.active_operations:
            profile = self.collector.active_operations[operation_id]
            profile.players_detected = players_detected
            profile.confidence_score = confidence_score
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        if not self.metrics_history:
            return {'status': 'no_data'}
        
        latest_metrics = self.metrics_history[-1]
        
        return {
            'current_metrics': asdict(latest_metrics),
            'active_operations': len(self.collector.active_operations),
            'total_operations': self.collector.total_operations,
            'success_rate': latest_metrics.success_rate,
            'recent_analysis': self.performance_reports[-1] if self.performance_reports else None,
            'uptime_hours': (time.time() - self.collector.start_time) / 3600
        }
    
    def get_performance_report(self, hours: int = 1) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter recent metrics
        recent_metrics = [
            m for m in self.metrics_history 
            if m.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            return {'status': 'no_data', 'timeframe': f'last_{hours}_hours'}
        
        # Calculate aggregated statistics
        total_requests = sum(m.total_requests for m in recent_metrics)
        avg_wait_time = sum(m.average_wait_time for m in recent_metrics) / len(recent_metrics)
        avg_utilization = sum(m.overall_utilization for m in recent_metrics) / len(recent_metrics)
        avg_success_rate = sum(m.success_rate for m in recent_metrics) / len(recent_metrics)
        peak_throughput = max(m.throughput_requests_per_minute for m in recent_metrics)
        
        # Get recent analysis
        recent_analysis = self.analyzer.analyze_patterns()
        
        return {
            'timeframe': f'last_{hours}_hours',
            'summary': {
                'total_requests': total_requests,
                'average_wait_time': avg_wait_time,
                'average_utilization': avg_utilization,
                'average_success_rate': avg_success_rate,
                'peak_throughput': peak_throughput,
                'data_points': len(recent_metrics)
            },
            'analysis': recent_analysis,
            'recommendations': recent_analysis.get('optimization_suggestions', []),
            'generated_at': datetime.now().isoformat()
        }


# Global performance monitor instance
_performance_monitor: Optional[OCRPerformanceMonitor] = None


def get_ocr_performance_monitor() -> OCRPerformanceMonitor:
    """Get global OCR performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = OCRPerformanceMonitor()
    return _performance_monitor