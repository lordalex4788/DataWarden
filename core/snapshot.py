#!/usr/bin/env python3
"""
DataWarden - Snapshot Manager
Transactional snapshots with rollback and retention.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path

from core.models import ExecutionMode, Snapshot


class SnapshotManager:
    """Manages transactional snapshots for undo/redo."""

    def __init__(
        self,
        quarantine_root: str = "~/.datawarden/quarantine",
        max_size_gb: float = 10.0,
        max_count: int = 100,
    ):
        self.quarantine_root = Path(quarantine_root).expanduser()
        self.snapshots_dir = self.quarantine_root / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_gb = max_size_gb
        self.max_count = max_count

    def create_snapshot(
        self,
        mappings: dict[str, str],
        mode: ExecutionMode,
        filter_config_hash: str = "",
        description: str = "",
    ) -> Snapshot:
        """Create a new snapshot with the given mappings."""
        snapshot_id = f"snap_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        timestamp = time.time()

        # Calculate total size
        total_size = 0
        for qpath in mappings.keys():
            qfile = Path(qpath)
            if qfile.exists() and not str(qpath).startswith("DELETED:") and not str(qpath).startswith("AUDIT_LOG_ONLY:"):
                total_size += qfile.stat().st_size

        snapshot = Snapshot(
            id=snapshot_id,
            timestamp=timestamp,
            mode=mode,
            mappings=mappings,
            total_size=total_size,
            filter_config_hash=filter_config_hash,
            description=description,
        )

        self._save_snapshot(snapshot)
        self._enforce_retention()

        return snapshot

    def _save_snapshot(self, snapshot: Snapshot) -> None:
        """Save snapshot metadata to disk."""
        snap_file = self.snapshots_dir / f"{snapshot.id}.json"
        data = {
            "id": snapshot.id,
            "timestamp": snapshot.timestamp,
            "mode": snapshot.mode.value,
            "mappings": snapshot.mappings,
            "total_size": snapshot.total_size,
            "filter_config_hash": snapshot.filter_config_hash,
            "description": snapshot.description,
        }
        with open(snap_file, "w") as f:
            json.dump(data, f, indent=2)

    def rollback(self, snapshot_id: str) -> dict[str, bool]:
        """Rollback a snapshot - restore files to original locations."""
        snap_file = self.snapshots_dir / f"{snapshot_id}.json"
        if not snap_file.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

        with open(snap_file) as f:
            data = json.load(f)

        results = {}
        for quarantine_path, original_path in data["mappings"].items():
            if quarantine_path.startswith("DELETED:") or quarantine_path.startswith("AUDIT_LOG_ONLY:"):
                # Can't rollback hard deletes or audit logs
                results[original_path] = False
                continue

            qpath = Path(quarantine_path)
            opath = Path(original_path)

            try:
                if qpath.exists():
                    opath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(qpath), str(opath))
                    results[original_path] = True
                else:
                    results[original_path] = False
            except Exception:
                results[original_path] = False

        return results

    def _enforce_retention(self) -> None:
        """Enforce retention policy - remove oldest snapshots if limits exceeded."""
        snapshots = self.list_snapshots()

        # Check count limit
        while len(snapshots) > self.max_count:
            oldest = snapshots[0]
            self._delete_snapshot(oldest.id)
            snapshots = snapshots[1:]

        # Check size limit
        total_size = sum(s.total_size for s in snapshots)
        max_bytes = int(self.max_size_gb * 1024 * 1024 * 1024)

        while total_size > max_bytes and snapshots:
            oldest = snapshots[0]
            self._delete_snapshot(oldest.id)
            total_size -= oldest.total_size
            snapshots = snapshots[1:]

    def _delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot and its quarantine files."""
        snap_file = self.snapshots_dir / f"{snapshot_id}.json"
        if not snap_file.exists():
            return

        with open(snap_file) as f:
            data = json.load(f)

        # Delete quarantine files
        for qpath in data["mappings"].keys():
            if qpath.startswith("DELETED:") or qpath.startswith("AUDIT_LOG_ONLY:"):
                continue
            qfile = Path(qpath)
            if qfile.exists():
                try:
                    qfile.unlink()
                except Exception:
                    pass

        # Remove snapshot file
        snap_file.unlink(missing_ok=True)

    def list_snapshots(self) -> list[Snapshot]:
        """List all snapshots sorted by timestamp (oldest first)."""
        snapshots = []
        for snap_file in sorted(self.snapshots_dir.glob("snap_*.json")):
            try:
                with open(snap_file) as f:
                    data = json.load(f)
                snapshots.append(Snapshot(
                    id=data["id"],
                    timestamp=data["timestamp"],
                    mode=ExecutionMode(data["mode"]),
                    mappings=data["mappings"],
                    total_size=data["total_size"],
                    filter_config_hash=data["filter_config_hash"],
                    description=data.get("description", ""),
                ))
            except Exception:
                continue
        return snapshots

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        """Get a specific snapshot by ID."""
        snap_file = self.snapshots_dir / f"{snapshot_id}.json"
        if not snap_file.exists():
            return None

        with open(snap_file) as f:
            data = json.load(f)
        return Snapshot(
            id=data["id"],
            timestamp=data["timestamp"],
            mode=ExecutionMode(data["mode"]),
            mappings=data["mappings"],
            total_size=data["total_size"],
            filter_config_hash=data["filter_config_hash"],
            description=data.get("description", ""),
        )

    def get_quarantine_usage(self) -> tuple[int, int]:
        """Get current quarantine usage (used_bytes, limit_bytes)."""
        used = 0
        for f in self.quarantine_root.rglob("*"):
            if f.is_file():
                used += f.stat().st_size
        limit = int(self.max_size_gb * 1024 * 1024 * 1024)
        return used, limit

    def prune_empty_dirs(self) -> int:
        """Remove empty directories in quarantine. Returns count removed."""
        count = 0
        for root, dirs, _files in os.walk(self.quarantine_root, topdown=False):
            for d in dirs:
                dpath = Path(root) / d
                if not any(dpath.iterdir()):
                    dpath.rmdir()
                    count += 1
        return count
