#!/usr/bin/env python3
"""
DataWarden - Telemetry Engine (STUB)
Async metrics streaming for live UI updates.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from collections import deque


@dataclass
class TelemetryMetrics:
    """Current telemetry snapshot."""
    current_file: str = ""
    current_folder: str = ""
    files_per_sec: float = 0.0
    mb_per_sec: float = 0.0
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    hash_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    eta_seconds: float = 0.0
    phase: str = "idle"  # idle, scanning, hashing, comparing, selecting, executing
    
    @property
    def progress_percent(self) -> float:
        if self.files_total > 0:
            return (self.files_done / self.files_total) * 100
        return 0.0
    
    @property
    def bytes_progress_percent(self) -> float:
        if self.bytes_total > 0:
            return (self.bytes_done / self.bytes_total) * 100
        return 0.0


class TelemetryEngine:
    """Async telemetry collector and broadcaster."""
    
    def __init__(self, update_interval: float = 0.5):
        self.update_interval = update_interval
        self.metrics = TelemetryMetrics()
        self._subscribers: list[asyncio.Queue] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Internal counters
        self._last_update = time.time()
        self._last_files_done = 0
        self._last_bytes_done = 0
        self._speed_samples = deque(maxlen=10)
    
    async def start(self) -> None:
        """Start the telemetry broadcast loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())
    
    async def stop(self) -> None:
        """Stop the telemetry loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    def subscribe(self) -> asyncio.Queue:
        """Create a new subscription queue for UI components."""
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscription."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
    
    def update_file(self, path: str) -> None:
        """Update current file being processed."""
        self.metrics.current_file = path
    
    def update_folder(self, path: str) -> None:
        """Update current folder being scanned."""
        self.metrics.current_folder = path
    
    def increment_files(self, count: int = 1) -> None:
        """Increment files processed counter."""
        self.metrics.files_done += count
    
    def increment_bytes(self, count: int) -> None:
        """Increment bytes processed counter."""
        self.metrics.bytes_done += count
    
    def increment_hashes(self, count: int = 1) -> None:
        """Increment hash calculations counter."""
        self.metrics.hash_count += count
    
    def increment_skipped(self, count: int = 1) -> None:
        """Increment skipped files counter."""
        self.metrics.skip_count += count
    
    def increment_errors(self, count: int = 1) -> None:
        """Increment errors counter."""
        self.metrics.error_count += count
    
    def set_totals(self, files: int, bytes: int) -> None:
        """Set total expected counts."""
        self.metrics.files_total = files
        self.metrics.bytes_total = bytes
    
    def set_phase(self, phase: str) -> None:
        """Set current processing phase."""
        self.metrics.phase = phase
    
    def _calculate_speeds(self) -> None:
        """Calculate rolling speed averages."""
        now = time.time()
        elapsed = now - self._last_update
        
        if elapsed > 0:
            files_delta = self.metrics.files_done - self._last_files_done
            bytes_delta = self.metrics.bytes_done - self._last_bytes_done
            
            files_per_sec = files_delta / elapsed
            mb_per_sec = (bytes_delta / 1024 / 1024) / elapsed
            
            self._speed_samples.append((files_per_sec, mb_per_sec))
            
            if self._speed_samples:
                avg_fps = sum(s[0] for s in self._speed_samples) / len(self._speed_samples)
                avg_mbps = sum(s[1] for s in self._speed_samples) / len(self._speed_samples)
                self.metrics.files_per_sec = avg_fps
                self.metrics.mb_per_sec = avg_mbps
            
            # ETA
            remaining_files = self.metrics.files_total - self.metrics.files_done
            if self.metrics.files_per_sec > 0:
                self.metrics.eta_seconds = remaining_files / self.metrics.files_per_sec
        
        self._last_update = now
        self._last_files_done = self.metrics.files_done
        self._last_bytes_done = self.metrics.bytes_done
    
    async def _broadcast_loop(self) -> None:
        """Main broadcast loop - sends metrics to all subscribers."""
        while self._running:
            self._calculate_speeds()
            
            # Send to all subscribers
            for queue in self._subscribers:
                try:
                    queue.put_nowait(self.metrics)
                except asyncio.QueueFull:
                    pass  # Drop if UI can't keep up
            
            await asyncio.sleep(self.update_interval)
    
    def get_current(self) -> TelemetryMetrics:
        """Get current metrics snapshot (non-async)."""
        return self.metrics
    
    async def get_metrics_stream(self):
        """Async generator for metrics stream."""
        queue = self.subscribe()
        try:
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe(queue)


# Global telemetry instance (for easy access)
_telemetry: Optional[TelemetryEngine] = None

def get_telemetry() -> TelemetryEngine:
    """Get or create global telemetry instance."""
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryEngine()
    return _telemetry