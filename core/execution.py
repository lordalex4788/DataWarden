#!/usr/bin/env python3
"""
DataWarden - Execution Engine
Handles AUDIT, SAFE_MOVE, and HARD_DELETE operations with snapshot integration.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.models import DuplicateGroup, ExecutionMode, FileMetadata
from core.selector import FilterAction
from core.snapshot import SnapshotManager


class ExecutionEngine:
    """Executes duplicate file operations with audit logging and snapshots."""

    def __init__(
        self,
        snapshot_manager: SnapshotManager,
        audit_log_path: Path | None = None,
    ):
        self.snapshot_manager = snapshot_manager
        self.audit_log_path = audit_log_path or Path("~/.datawarden/audit.log").expanduser()
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        groups: list[DuplicateGroup],
        selections: dict[str, dict[str, str]],  # {hash: {file_path: action}}
        mode: ExecutionMode,
        filter_config_hash: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Execute operations on selected duplicates.

        Args:
            groups: List of duplicate groups
            selections: Mapping of group hash -> {file_path -> action}
            mode: Execution mode (AUDIT, SAFE_MOVE, HARD_DELETE)
            filter_config_hash: Hash of filter configuration for snapshot
            dry_run: If True, only log what would be done

        Returns:
            Dict with results: executed, skipped, errors, snapshot_id
        """
        file_operations = []  # List of (source, destination)
        executed = []
        skipped = []
        errors = []

        for group in groups:
            if group.hash not in selections:
                continue

            actions = selections[group.hash]
            for file_path, action in actions.items():
                if action == "keep" or action == FilterAction.KEEP.value:
                    skipped.append(file_path)
                    continue

                if action not in ("delete", FilterAction.DELETE.value):
                    skipped.append(file_path)
                    continue

                # Find the file metadata
                file_meta = None
                for df in group.files:
                    if df.metadata.path == file_path:
                        file_meta = df.metadata
                        break

                if not file_meta:
                    errors.append({"path": file_path, "error": "File not found in group"})
                    continue

                try:
                    if mode == ExecutionMode.AUDIT:
                        dst = self._audit_operation(file_meta)
                    elif mode == ExecutionMode.SAFE_MOVE:
                        dst = self._safe_move_operation(file_meta, dry_run)
                    elif mode == ExecutionMode.HARD_DELETE:
                        dst = self._hard_delete_operation(file_meta, dry_run)
                    else:
                        errors.append({"path": file_path, "error": f"Unknown mode: {mode}"})
                        continue

                    file_operations.append((file_path, dst))
                    executed.append(file_path)

                except Exception as e:
                    errors.append({"path": file_path, "error": str(e)})

        # Create snapshot for non-audit modes
        snapshot_id = None
        if mode != ExecutionMode.AUDIT and file_operations:
            if not dry_run:
                description = f"Executed {mode.value} on {len(executed)} files"
                snapshot = self.snapshot_manager.create_snapshot(
                    mappings=dict(file_operations),
                    mode=mode,
                    filter_config_hash=filter_config_hash,
                    description=description,
                )
                snapshot_id = snapshot.id

        # Write audit log
        self._write_audit_log(mode, executed, skipped, errors, filter_config_hash, snapshot_id)

        return {
            "executed": executed,
            "skipped": skipped,
            "errors": errors,
            "snapshot_id": snapshot_id,
            "mode": mode.value,
            "dry_run": dry_run,
        }

    def _audit_operation(self, file_meta: FileMetadata) -> str:
        """Log audit operation - no actual file changes."""
        self._log_operation("AUDIT", file_meta.path, "AUDIT_LOG_ONLY")
        return "AUDIT_LOG_ONLY"

    def _safe_move_operation(self, file_meta: FileMetadata, dry_run: bool) -> str:
        """Move file to quarantine preserving directory structure."""
        src = Path(file_meta.path)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {src}")

        # Build quarantine path: ~/quarantine/<mount_point>/<relative_path>
        mount_point = self._get_mount_point(src)
        relative = src.relative_to(mount_point)
        quarantine_path = self.snapshot_manager.quarantine_root / mount_point.name / relative
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)

        if not dry_run:
            # Preserve metadata
            self._preserve_metadata(src, quarantine_path)
            shutil.move(str(src), str(quarantine_path))
            self._log_operation("SAFE_MOVE", str(src), str(quarantine_path))
        else:
            self._log_operation("SAFE_MOVE (dry)", str(src), str(quarantine_path))

        return str(quarantine_path)

    def _hard_delete_operation(self, file_meta: FileMetadata, dry_run: bool) -> str:
        """Permanently delete file."""
        src = Path(file_meta.path)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {src}")

        if not dry_run:
            self._log_operation("HARD_DELETE", str(src), "DELETED")
            src.unlink()
        else:
            self._log_operation("HARD_DELETE (dry)", str(src), "DELETED")

        return "DELETED"

    def _get_mount_point(self, path: Path) -> Path:
        """Find the mount point for a given path."""
        path = path.resolve()
        for mount in sorted(Path("/proc/mounts").read_text().splitlines(), key=len, reverse=True):
            parts = mount.split()
            if len(parts) >= 2:
                mnt = Path(parts[1])
                try:
                    path.relative_to(mnt)
                    return mnt
                except ValueError:
                    continue
        return Path("/")

    def _preserve_metadata(self, src: Path, dst: Path) -> None:
        """Preserve file metadata during move."""
        stat = src.stat()
        # Preserve timestamps
        os.utime(dst, (stat.st_atime, stat.st_mtime))
        # Preserve permissions
        dst.chmod(stat.st_mode)
        # Try to preserve owner (requires root)
        try:
            os.chown(dst, stat.st_uid, stat.st_gid)
        except PermissionError:
            pass
        # Preserve extended attributes
        try:
            import xattr
            for key in xattr.listxattr(src):
                xattr.setxattr(dst, key, xattr.getxattr(src, key))
        except (ImportError, OSError):
            pass

    def _log_operation(self, operation: str, source: str, destination: str) -> None:
        """Log operation to audit log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "source": source,
            "destination": destination,
            "size": Path(source).stat().st_size if Path(source).exists() else 0,
        }
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _write_audit_log(
        self,
        mode: ExecutionMode,
        executed: list[str],
        skipped: list[str],
        errors: list[dict],
        filter_config_hash: str,
        snapshot_id: str | None,
    ) -> None:
        """Write summary to audit log."""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "type": "EXECUTION_SUMMARY",
            "mode": mode.value,
            "executed_count": len(executed),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "filter_config_hash": filter_config_hash,
            "snapshot_id": snapshot_id,
        }
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(summary) + "\n")


class InitialSnapshotPrompt:
    """Handles the initial snapshot prompt on first run."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.marker_file = config_dir / ".initial_snapshot_done"

    def should_prompt(self) -> bool:
        """Check if initial snapshot prompt should be shown."""
        return not self.marker_file.exists()

    def mark_done(self) -> None:
        """Mark initial snapshot as completed."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.marker_file.write_text(str(time.time()))

    def get_prompt_text(self) -> str:
        """Get the prompt message for initial snapshot."""
        return (
            "Create an initial system snapshot?\n\n"
            "This creates a baseline of your filesystem state for future comparison.\n"
            "Recommended for first run - allows full rollback if needed.\n\n"
            "Estimated time: 1-5 minutes depending on filesystem size.\n"
            "Estimated space: 50MB - 2GB for snapshot metadata."
        )

    def create_initial_snapshot(self, scan_config: Any, indexer: Any) -> str | None:
        """Create an initial full-system snapshot."""
        # This would integrate with the indexer to create a full snapshot
        # Implementation depends on Phase 1 completion
        pass
