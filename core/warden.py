#!/usr/bin/env python3
"""
DataWarden - FileSystem Warden (STUB)
Watchdog daemon for real-time filesystem governance.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable, Any, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from core.ai_filter import AIFilterEngine
from core.models import WardenZone, WardenIncident


class IncidentSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentType(Enum):
    PERMISSION_VIOLATION = "permission"
    NAMING_VIOLATION = "naming"
    CLASSIFICATION_VIOLATION = "classification"
    SUSPICIOUS_ACTIVITY = "suspicious"


@dataclass
class WardenIncident:
    """An incident detected by the Warden."""
    id: str
    timestamp: float
    zone_name: str
    file_path: str
    incident_type: IncidentType
    severity: IncidentSeverity
    description: str
    details: Dict = field(default_factory=dict)
    llm_suggestion: Optional[str] = None
    status: str = "open"  # open, auto_fixed, pending_review, resolved
    resolved_at: Optional[float] = None
    resolved_by: str = ""
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["incident_type"] = self.incident_type.value
        d["severity"] = self.severity.value
        return d


class WardenEventHandler(FileSystemEventHandler):
    """Watchdog event handler for filesystem events."""
    
    def __init__(self, warden: 'FileSystemWarden'):
        self.warden = warden
        self._pending_events: asyncio.Queue = asyncio.Queue()
    
    def on_created(self, event):
        if not event.is_directory:
            asyncio.create_task(self._pending_events.put(
                ("created", event.src_path)
            ))
    
    def on_moved(self, event):
        if not event.is_directory:
            asyncio.create_task(self._pending_events.put(
                ("moved", event.dest_path)
            ))
    
    async def get_event(self) -> tuple:
        return await self._pending_events.get()


class FileSystemWarden:
    """
    Real-time filesystem governance daemon.
    Monitors zones, validates 3 pillars, triggers LLM triage.
    """
    
    def __init__(self, 
                 zones: List[WardenZone],
                 ai_engine: AIFilterEngine,
                 incident_callback: Callable[[WardenIncident], Awaitable[None]] = None):
        self.zones = {z.path: z for z in zones}
        self.ai_engine = ai_engine
        self.incident_callback = incident_callback
        
        self.observer: Optional[Observer] = None
        self.handler: Optional[WardenEventHandler] = None
        self.running = False
        
        # Incident storage
        self.incidents: List[WardenIncident] = []
        self.max_incidents = 10000
        
        # Processing queue
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None
        
        # File locks for race condition prevention
        self._path_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, path: str) -> asyncio.Lock:
        """Get or create lock for a path."""
        if path not in self._path_locks:
            self._path_locks[path] = asyncio.Lock()
        return self._path_locks[path]
    
    async def start(self) -> None:
        """Start the watchdog observer."""
        if self.running:
            return
        
        self.handler = WardenEventHandler(self)
        self.observer = Observer()
        
        for zone in self.zones.values():
            self.observer.schedule(self.handler, zone.path, recursive=True)
        
        self.observer.start()
        self.running = True
        
        # Start event processor
        self._processor_task = asyncio.create_task(self._process_events())
        
        print(f"[Warden] Started monitoring {len(self.zones)} zones")
    
    async def stop(self) -> None:
        """Stop the watchdog observer."""
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        print("[Warden] Stopped")
    
    async def _process_events(self) -> None:
        """Process filesystem events from queue."""
        while self.running:
            try:
                event_type, file_path = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )
                
                # Find matching zone
                zone = self._find_zone(file_path)
                if zone:
                    await self._validate_file(file_path, zone, event_type)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[Warden] Event processing error: {e}")
    
    def _find_zone(self, path: str) -> Optional[WardenZone]:
        """Find the most specific zone containing this path."""
        path_obj = Path(path)
        matching = None
        for zone_path, zone in self.zones.items():
            try:
                path_obj.relative_to(zone_path)
                if matching is None or len(zone_path) > len(matching.path):
                    matching = zone
            except ValueError:
                continue
        return matching
    
    async def _validate_file(self, file_path: str, zone: WardenZone, event_type: str) -> None:
        """Validate a file against zone policies."""
        lock = self._get_lock(file_path)
        async with lock:
            path_obj = Path(file_path)
            if not path_obj.exists():
                return
            
            violations = []
            
            # Pillar 1: Permissions
            if zone.auto_fix_permissions:
                perm_violation = await self._check_permissions(path_obj, zone)
                if perm_violation:
                    violations.append(perm_violation)
            
            # Pillar 2: Naming Convention
            if zone.naming_regex:
                naming_violation = await self._check_naming(path_obj, zone)
                if naming_violation:
                    violations.append(naming_violation)
            
            # Pillar 3: Classification
            if zone.classification_rules:
                class_violation = await self._check_classification(path_obj, zone)
                if class_violation:
                    violations.append(class_violation)
            
            # Process violations
            for violation in violations:
                await self._create_incident(zone, file_path, violation)
    
    async def _check_permissions(self, path: Path, zone: WardenZone) -> Optional[Dict]:
        """Check and optionally fix permissions."""
        try:
            current_mode = oct(path.stat().st_mode & 0o777)[2:]
            expected = zone.expected_permissions
            
            if current_mode != expected:
                return {
                    "type": IncidentType.PERMISSION_VIOLATION,
                    "severity": IncidentSeverity.WARNING,
                    "description": f"Permissions {current_mode} != expected {expected}",
                    "details": {"current": current_mode, "expected": expected},
                    "auto_fixable": True,
                    "fix_action": "chmod",
                    "fix_params": {"mode": expected}
                }
        except Exception:
            pass
        return None
    
    async def _check_naming(self, path: Path, zone: WardenZone) -> Optional[Dict]:
        """Check filename against zone regex."""
        try:
            pattern = re.compile(zone.naming_regex)
            if not pattern.match(path.name):
                # Get LLM suggestion for rename
                llm_suggestion = await self._get_llm_rename_suggestion(path, zone)
                
                return {
                    "type": IncidentType.NAMING_VIOLATION,
                    "severity": IncidentSeverity.WARNING,
                    "description": f"Filename '{path.name}' doesn't match pattern",
                    "details": {"pattern": zone.naming_regex, "filename": path.name},
                    "auto_fixable": False,
                    "llm_suggestion": llm_suggestion
                }
        except re.error:
            pass
        return None
    
    async def _check_classification(self, path: Path, zone: WardenZone) -> Optional[Dict]:
        """Check if file is correctly classified/placed."""
        # Simplified: check extension matches folder purpose
        # Could be extended with content analysis
        return None
    
    async def _get_llm_rename_suggestion(self, path: Path, zone: WardenZone) -> str:
        """Get LLM suggestion for compliant rename."""
        if not self.ai_engine or not self.ai_engine._initialized:
            return "LLM nicht verfügbar"
        
        try:
            prompt = f"""Datei: {path.name}
Ziel-Ordner: {zone.path}
Namens-Pattern: {zone.naming_regex}

Schlage einen konformen neuen Dateinamen vor.
Antworte NUR mit dem neuen Namen."""
            
            return await self.ai_engine.client.generate(prompt, stream=False)
        except Exception:
            return "LLM-Fehler"
    
    async def _create_incident(self, zone: WardenZone, file_path: str, violation: Dict) -> None:
        """Create and dispatch incident."""
        incident = WardenIncident(
            id=f"inc_{int(time.time() * 1000)}",
            timestamp=time.time(),
            zone_name=zone.name,
            file_path=file_path,
            incident_type=violation["type"],
            severity=violation["severity"],
            description=violation["description"],
            details=violation.get("details", {}),
            llm_suggestion=violation.get("llm_suggestion")
        )
        
        # Auto-fix if possible and enabled
        if violation.get("auto_fixable") and zone.auto_fix_permissions:
            await self._apply_auto_fix(incident, violation)
            incident.status = "auto_fixed"
            incident.resolved_at = time.time()
            incident.resolved_by = "auto"
        else:
            incident.status = "pending_review"
        
        self.incidents.append(incident)
        
        # Trim if too many
        if len(self.incidents) > self.max_incidents:
            self.incidents = self.incidents[-self.max_incidents:]
        
        # Callback to UI
        if self.incident_callback:
            await self.incident_callback(incident)
    
    async def _apply_auto_fix(self, incident: WardenIncident, violation: Dict) -> None:
        """Apply automatic fix for permission violations."""
        if violation.get("fix_action") == "chmod":
            try:
                mode = int(violation["fix_params"]["mode"], 8)
                Path(incident.file_path).chmod(mode)
            except Exception as e:
                print(f"[Warden] Auto-fix failed: {e}")
    
    def add_zone(self, zone: WardenZone) -> None:
        """Add a new monitoring zone."""
        self.zones[zone.path] = zone
        if self.observer and self.running:
            self.observer.schedule(self.handler, zone.path, recursive=True)
    
    def remove_zone(self, path: str) -> bool:
        """Remove a monitoring zone."""
        if path in self.zones:
            del self.zones[path]
            # Note: watchdog doesn't easily support unscheduling by path
            # Would need observer restart for full removal
            return True
        return False
    
    def get_incidents(self, 
                     zone: Optional[str] = None,
                     status: Optional[str] = None,
                     severity: Optional[IncidentSeverity] = None,
                     limit: int = 100) -> List[WardenIncident]:
        """Get filtered incidents."""
        results = self.incidents
        
        if zone:
            results = [i for i in results if i.zone_name == zone]
        if status:
            results = [i for i in results if i.status == status]
        if severity:
            results = [i for i in results if i.severity == severity]
        
        return results[-limit:]
    
    def resolve_incident(self, incident_id: str, resolved_by: str) -> bool:
        """Mark incident as resolved."""
        for inc in self.incidents:
            if inc.id == incident_id:
                inc.status = "resolved"
                inc.resolved_at = time.time()
                inc.resolved_by = resolved_by
                return True
        return False
    
    async def query_natural_language(self, query: str, index_stats: Dict) -> str:
        """
        Natural language query for file search.
        'Wo ist die Tabelle mit Umsatz Q2 von letzter Woche?'
        """
        if not self.ai_engine or not self.ai_engine._initialized:
            return "KI nicht verfügbar"
        
        return await self.ai_engine.warden_query(query, index_stats)


class WardenDashboard:
    """Data provider for Warden dashboard UI."""
    
    def __init__(self, warden: FileSystemWarden):
        self.warden = warden
    
    def get_stats(self) -> Dict:
        """Get dashboard statistics."""
        total = len(self.warden.incidents)
        by_severity = {}
        by_type = {}
        by_zone = {}
        by_status = {}
        
        for inc in self.warden.incidents:
            by_severity[inc.severity.value] = by_severity.get(inc.severity.value, 0) + 1
            by_type[inc.incident_type.value] = by_type.get(inc.incident_type.value, 0) + 1
            by_zone[inc.zone_name] = by_zone.get(inc.zone_name, 0) + 1
            by_status[inc.status] = by_status.get(inc.status, 0) + 1
        
        return {
            "total_incidents": total,
            "by_severity": by_severity,
            "by_type": by_type,
            "by_zone": by_zone,
            "by_status": by_status,
            "zones_monitored": len(self.warden.zones)
        }
    
    def get_recent_incidents(self, limit: int = 50) -> List[WardenIncident]:
        """Get most recent incidents for display."""
        return self.warden.incidents[-limit:]
    
    def get_open_critical(self) -> List[WardenIncident]:
        """Get critical open incidents requiring attention."""
        return [
            i for i in self.warden.incidents
            if i.severity == IncidentSeverity.CRITICAL and i.status == "pending_review"
        ]