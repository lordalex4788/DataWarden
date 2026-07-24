#!/usr/bin/env python3
"""
DataWarden - Indexer Core Module
Async scanner with xxHash, metadata extraction, JSONL writer, savestate.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import stat
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import aiofiles
import aiofiles.os
import xxhash

from core.models import ErrorAction, FileMetadata, ScanConfig, SymlinkMode, TelemetryData


class ScanStatus(StrEnum):
    PENDING = "PENDING"
    SCANNING = "SCANNING"
    HASHING = "HASHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class FolderState:
    path: str
    status: ScanStatus = ScanStatus.PENDING
    file_count: int = 0
    files_done: int = 0
    files_total: int = 0
    current_file: str = ""
    completed_at: str | None = None
    error: str | None = None


@dataclass
class ScanError:
    path: str
    error_type: str
    action: str
    timestamp: str
    detail: str = ""


class HashEngine:
    """High-performance xxHash streaming hasher."""

    CHUNK_SIZE = 1024 * 1024  # 1MB chunks

    @staticmethod
    async def hash_file(path: Path, algorithm: str = "xxh3_64") -> str:
        """Hash a file using xxHash streaming."""
        hasher = xxhash.xxh3_64()

        async with aiofiles.open(path, 'rb') as f:
            while chunk := await f.read(HashEngine.CHUNK_SIZE):
                hasher.update(chunk)

        return hasher.hexdigest()

    @staticmethod
    def hash_bytes(data: bytes, algorithm: str = "xxh3_64") -> str:
        """Hash bytes directly."""
        return xxhash.xxh3_64(data).hexdigest()


class MetadataExtractor:
    """Extracts full filesystem metadata."""

    @staticmethod
    async def extract(path: Path, follow_symlinks: bool = False) -> FileMetadata:
        """Extract all metadata from a file."""
        try:
            if follow_symlinks:
                st = await aiofiles.os.stat(path)
            else:
                st = await aiofiles.os.lstat(path)

            suffix = path.suffix.lower()

            symlink_target = None
            if stat.S_ISLNK(st.st_mode):
                try:
                    symlink_target = await aiofiles.os.readlink(path)
                except OSError:
                    pass

            return FileMetadata(
                path=str(path),
                size=st.st_size,
                mtime=int(st.st_mtime),
                ctime=int(st.st_ctime),
                atime=int(st.st_atime),
                mode=st.st_mode,
                uid=st.st_uid,
                gid=st.st_gid,
                inode=st.st_ino,
                hash="",
                filetype=suffix,
                is_symlink=stat.S_ISLNK(st.st_mode),
                symlink_target=symlink_target,
                is_hardlink=False,
            )
        except OSError as e:
            raise MetadataError(f"Failed to extract metadata: {e}") from e


class FileTypeFilter:
    """Filters files by extension before hashing."""

    def __init__(self, whitelist: list[str] | None = None, blacklist: list[str] | None = None):
        self.whitelist = {w.lower() for w in (whitelist or [])}
        self.blacklist = {b.lower() for b in (blacklist or [])}
        self._allow_all = not self.whitelist

    def should_process(self, path: Path) -> bool:
        suffix = path.suffix.lower()

        if suffix in self.blacklist:
            return False

        if not self._allow_all and suffix not in self.whitelist:
            return False

        return True

    def should_process_size(self, size: int, min_size: int, max_size: int) -> bool:
        if size < min_size:
            return False
        if max_size > 0 and size > max_size:
            return False
        return True


class SavestateManager:
    """Manages scan progress with folder-level compression."""

    SAVESTATE_FILE = "savestate.json"

    def __init__(self, index_root: Path, root_path: Path):
        self.index_root = index_root
        self.root_path = root_path
        self.savestate_path = index_root / self.SAVESTATE_FILE
        self.folders: dict[str, FolderState] = {}
        self.errors: list[ScanError] = []
        self.config_hash = ""
        self.started_at = ""
        self.version = "0.05.30"

    def load(self) -> bool:
        """Load savestate from disk."""
        if not self.savestate_path.exists():
            return False

        try:
            data = json.loads(self.savestate_path.read_text())

            self.version = data.get("version", "0.05.30")
            self.config_hash = data.get("config_hash", "")
            self.started_at = data.get("started_at", "")

            for path, folder_data in data.get("folders", {}).items():
                self.folders[path] = FolderState(
                    path=path,
                    status=ScanStatus(folder_data["status"]),
                    file_count=folder_data.get("file_count", 0),
                    files_done=folder_data.get("files_done", 0),
                    files_total=folder_data.get("files_total", 0),
                    current_file=folder_data.get("current_file", ""),
                    completed_at=folder_data.get("completed_at"),
                    error=folder_data.get("error"),
                )

            self.errors = [ScanError(**e) for e in data.get("errors", [])]
            return True
        except Exception:
            return False

    async def save(self) -> None:
        """Save savestate to disk (append-only for crash safety)."""
        data = {
            "version": self.version,
            "root_path": str(self.root_path),
            "config_hash": self.config_hash,
            "started_at": self.started_at,
            "folders": {
                path: {
                    "status": folder.status.value,
                    "file_count": folder.file_count,
                    "files_done": folder.files_done,
                    "files_total": folder.files_total,
                    "current_file": folder.current_file,
                    "completed_at": folder.completed_at,
                    "error": folder.error,
                }
                for path, folder in self.folders.items()
            },
            "errors": [
                {
                    "path": e.path,
                    "error_type": e.error_type,
                    "action": e.action,
                    "timestamp": e.timestamp,
                    "detail": e.detail,
                }
                for e in self.errors
            ],
        }

        # Write atomically
        temp_path = self.savestate_path.with_suffix('.tmp')
        async with aiofiles.open(temp_path, 'w') as f:
            await f.write(json.dumps(data, indent=2))
        await aiofiles.os.replace(temp_path, self.savestate_path)

    def is_folder_completed(self, path: str) -> bool:
        state = self.folders.get(path)
        return state is not None and state.status == ScanStatus.COMPLETED

    def get_pending_folders(self) -> list[str]:
        return [
            path for path, state in self.folders.items()
            if state.status in (ScanStatus.PENDING, ScanStatus.SCANNING, ScanStatus.HASHING)
        ]

    def compress_completed_folders(self) -> None:
        pass


class IndexWriter:
    """Writes JSONL index files with automatic splitting."""

    def __init__(self, index_dir: Path, max_lines: int = 50000, max_mb: int = 100):
        self.index_dir = index_dir
        self.max_lines = max_lines
        self.max_bytes = max_mb * 1024 * 1024
        self.current_part = 1
        self.current_lines = 0
        self.current_bytes = 0
        self.current_file = None

    async def _open_part(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        part_path = self.index_dir / f"part_{self.current_part:03d}.jsonl"
        self.current_file = await aiofiles.open(part_path, 'a')
        self.current_lines = 0
        self.current_bytes = 0

    async def write_record(self, record: dict) -> None:
        if self.current_file is None:
            await self._open_part()

        line = json.dumps(record, separators=(',', ':')) + '\n'
        line_bytes = line.encode('utf-8')

        if (self.current_lines >= self.max_lines or
            self.current_bytes + len(line_bytes) > self.max_bytes):
            await self.current_file.close()
            self.current_part += 1
            await self._open_part()

        await self.current_file.write(line)
        self.current_lines += 1
        self.current_bytes += len(line_bytes)

    async def close(self) -> None:
        if self.current_file:
            await self.current_file.close()
            self.current_file = None

    async def write_manifest(self, total_files: int, total_bytes: int, config_hash: str) -> None:
        manifest = {
            "version": "1.0",
            "parts": self.current_part,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "config_hash": config_hash,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        manifest_path = self.index_dir / "manifest.json"
        async with aiofiles.open(manifest_path, 'w') as f:
            await f.write(json.dumps(manifest, indent=2))


class SymlinkHandler:
    """Handles symlink traversal with loop detection."""

    def __init__(self, mode: SymlinkMode = SymlinkMode.IGNORE):
        self.mode = mode
        self.visited: set[str] = set()

    def should_follow(self, path: Path) -> bool:
        if self.mode == SymlinkMode.IGNORE:
            return False
        if self.mode == SymlinkMode.RECORD_ONLY:
            return False
        return True

    def should_record(self, path: Path) -> bool:
        return self.mode in (SymlinkMode.FOLLOW, SymlinkMode.RECORD_ONLY)

    def check_loop(self, path: Path) -> bool:
        try:
            target = path.readlink() if path.is_symlink() else path
        except OSError:
            target = path

        real_path = str(target.resolve()) if hasattr(target, 'resolve') else str(target)
        symlink_path = str(path)

        if real_path in self.visited:
            return True
        if symlink_path in self.visited:
            return True

        self.visited.add(real_path)
        self.visited.add(symlink_path)
        return False

    def reset(self) -> None:
        self.visited.clear()


class HardlinkTracker:
    """Tracks hardlinks by inode."""

    def __init__(self):
        self.inode_map: dict[int, list[str]] = {}

    def register(self, inode: int, path: str) -> bool:
        if inode not in self.inode_map:
            self.inode_map[inode] = [path]
            return True
        self.inode_map[inode].append(path)
        return False

    def get_hardlinks(self, inode: int) -> list[str]:
        return self.inode_map.get(inode, [])

    def is_hardlink(self, inode: int) -> bool:
        return len(self.inode_map.get(inode, [])) > 1


class ErrorManager:
    """Manages error handling with user-defined rules."""

    def __init__(self, rules: dict[str, ErrorAction]):
        self.rules = rules
        self.retry_counts: dict[str, int] = {}

    def handle_error(self, error_type: str, path: str, detail: str = "") -> ErrorAction:
        return self.rules.get(error_type, ErrorAction.ASK)

    async def handle_with_retry(
        self,
        error_type: str,
        path: str,
        operation: Callable[[], Awaitable[FileMetadata]],
        detail: str = "",
        max_retries: int = 3,
        ask_callback: Callable[[str, str], Awaitable[ErrorAction]] | None = None,
    ) -> FileMetadata | None:
        """Execute operation with error handling and retry logic."""
        rule = self.rules.get(error_type, ErrorAction.ASK)

        if rule == ErrorAction.AUTO_SKIP:
            return None

        if rule == ErrorAction.RETRY:
            key = f"{path}:{error_type}"
            retries = self.retry_counts.get(key, 0)

            if retries >= max_retries:
                if ask_callback:
                    rule = await ask_callback(path, f"Max retries exceeded for {error_type}: {detail}")
                else:
                    return None

            if rule == ErrorAction.RETRY:
                self.retry_counts[key] = retries + 1
                await asyncio.sleep(0.5 * (retries + 1))  # Exponential backoff
                try:
                    return await operation()
                except Exception as e:
                    return await self.handle_with_retry(error_type, path, operation, str(e), max_retries, ask_callback)
            return None

        if rule == ErrorAction.ASK and ask_callback:
            rule = await ask_callback(path, detail)
            if rule == ErrorAction.AUTO_SKIP:
                return None
            if rule == ErrorAction.RETRY:
                try:
                    return await operation()
                except Exception as e:
                    return await self.handle_with_retry(error_type, path, operation, str(e), max_retries, ask_callback)
            return None

        return None

    def clear_retry(self, path: str, error_type: str) -> None:
        key = f"{path}:{error_type}"
        self.retry_counts.pop(key, None)


class MetadataError(Exception):
    pass


class Indexer:
    """Main indexer orchestrating all components."""

    def __init__(
        self,
        config: ScanConfig,
        telemetry_queue: asyncio.Queue | None = None,
        ask_callback: Callable[[str, str], Awaitable[ErrorAction]] | None = None,
    ):
        self.config = config
        self.hash_engine = HashEngine()
        self.metadata_extractor = MetadataExtractor()
        self.file_filter = FileTypeFilter(config.whitelist, config.blacklist)
        self.symlink_handler = SymlinkHandler(config.symlink_mode)
        self.hardlink_tracker = HardlinkTracker() if config.track_hardlinks else None
        self.error_manager = ErrorManager(config.error_rules)
        self.telemetry_queue = telemetry_queue
        self.ask_callback = ask_callback

        # Progress tracking
        self.total_files = 0
        self.processed_files = 0
        self.total_bytes = 0
        self.processed_bytes = 0
        self.hash_count = 0
        self.skip_count = 0
        self.error_count = 0
        self.start_time = time.time()

    def _config_hash(self) -> str:
        """Generate hash of scan config for manifest."""
        config_str = json.dumps({
            "root": self.config.root_path,
            "min_size": self.config.min_size,
            "max_size": self.config.max_size,
            "whitelist": sorted(self.config.whitelist),
            "blacklist": sorted(self.config.blacklist),
            "symlink_mode": self.config.symlink_mode.value,
            "track_hardlinks": self.config.track_hardlinks,
            "max_depth": self.config.max_depth,
        }, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    async def _emit_telemetry(self, current_file: str = "", current_folder: str = "") -> None:
        """Emit telemetry update."""
        if self.telemetry_queue is None:
            return

        elapsed = time.time() - self.start_time
        files_per_sec = self.processed_files / elapsed if elapsed > 0 else 0
        mb_per_sec = (self.processed_bytes / 1024 / 1024) / elapsed if elapsed > 0 else 0

        eta = 0
        if files_per_sec > 0:
            remaining = self.total_files - self.processed_files
            eta = remaining / files_per_sec

        data = TelemetryData(
            current_file=current_file,
            current_folder=current_folder,
            files_per_sec=files_per_sec,
            mb_per_sec=mb_per_sec,
            files_done=self.processed_files,
            files_total=self.total_files,
            bytes_done=self.processed_bytes,
            bytes_total=self.total_bytes,
            hash_count=self.hash_count,
            skip_count=self.skip_count,
            error_count=self.error_count,
            eta_seconds=eta,
            phase="scanning" if self.processed_files < self.total_files else "complete",
        )
        try:
            self.telemetry_queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    async def scan(
        self,
        root: Path,
        savestate: SavestateManager,
        index_writer: IndexWriter,
    ) -> AsyncIterator[FileMetadata]:
        """Main scan generator yielding FileMetadata for each file."""
        self.symlink_handler.reset()
        config_hash = self._config_hash()

        # Initialize savestate if needed
        if not savestate.folders:
            savestate.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            savestate.config_hash = config_hash
            savestate.version = "0.05.30"

        # Phase 1: Collect all files and group by size
        size_buckets: dict[int, list[Path]] = defaultdict(list)
        folder_totals: dict[str, int] = defaultdict(int)

        await self._collect_files(root, root, size_buckets, folder_totals, savestate)

        # Update total counts
        self.total_files = sum(len(files) for files in size_buckets.values())
        self.total_bytes = sum(size * len(files) for size, files in size_buckets.items())

        # Initialize savestate folder records
        for folder_path, count in folder_totals.items():
            if folder_path not in savestate.folders:
                savestate.folders[folder_path] = FolderState(
                    path=folder_path,
                    status=ScanStatus.PENDING,
                    files_total=count,
                )
            else:
                savestate.folders[folder_path].files_total = count

        await savestate.save()

        # Phase 2: Process size buckets - hash only collisions
        for size, files in size_buckets.items():
            if len(files) == 1:
                # Unique size - no hash needed
                file_path = files[0]
                yield await self._process_single_file(file_path, savestate, index_writer, True)
            else:
                # Collision - need to hash
                await self._process_collision_bucket(files, size, savestate, index_writer)

        # Write manifest
        await index_writer.close()
        await index_writer.write_manifest(
            total_files=sum(1 for _ in size_buckets.values()),
            total_bytes=sum(f.size for _ in size_buckets.values() for f in []),
            config_hash=config_hash,
        )

        # Final telemetry
        await self._emit_telemetry(phase="complete")

    async def _collect_files(
        self,
        root: Path,
        current: Path,
        size_buckets: dict[int, list[Path]],
        folder_totals: dict[str, int],
        savestate: SavestateManager,
        depth: int = 0,
    ) -> None:
        """Collect all files recursively, building size buckets."""
        if self.config.max_depth > 0 and depth >= self.config.max_depth:
            return

        folder_str = str(current)
        if savestate.is_folder_completed(folder_str):
            return

        # Update savestate
        if folder_str in savestate.folders:
            savestate.folders[folder_str].status = ScanStatus.SCANNING
        else:
            savestate.folders[folder_str] = FolderState(
                path=folder_str,
                status=ScanStatus.SCANNING,
            )

        await self._emit_telemetry(current_folder=folder_str)
        await savestate.save()

        try:
            entries = await aiofiles.os.scandir(current)
        except OSError as e:
            await self._handle_error("permission_denied", folder_str, str(e))
            if folder_str in savestate.folders:
                savestate.folders[folder_str].status = ScanStatus.FAILED
                savestate.folders[folder_str].error = str(e)
            await savestate.save()
            return

        for entry in entries:
            entry_path = Path(entry.path)

            # Check symlink
            if entry.is_symlink():
                if self.symlink_handler.check_loop(entry_path):
                    self.skip_count += 1
                    continue

                if not self.symlink_handler.should_follow(entry_path):
                    if self.symlink_handler.should_record(entry_path):
                        # Record symlink only
                        try:
                            meta = await self.metadata_extractor.extract(entry_path, follow_symlinks=False)
                            meta.hash = "SYMLINK"
                            meta.symlink_target = str(await aiofiles.os.readlink(entry_path))
                            yield meta
                        except OSError:
                            pass
                    self.skip_count += 1
                    continue

            if entry.is_dir():
                await self._collect_files(root, entry_path, size_buckets, folder_totals, savestate, depth + 1)
            elif entry.is_file():
                try:
                    size = entry.stat().st_size
                except OSError:
                    continue

                # Size filter
                if not self.file_filter.should_process_size(size, self.config.min_size, self.config.max_size):
                    self.skip_count += 1
                    continue

                # Extension filter
                if not self.file_filter.should_process(entry_path):
                    self.skip_count += 1
                    continue

                size_buckets[size].append(entry_path)
                folder_totals[folder_str] += 1

    async def _process_single_file(
        self,
        file_path: Path,
        savestate: SavestateManager,
        index_writer: IndexWriter,
        unique_size: bool = False,
    ) -> FileMetadata:
        """Process a file with unique size (no hash needed) or hash it."""
        rel_path = str(file_path.relative_to(self.config.root_path))

        # Update savestate
        folder = str(file_path.parent)
        if folder in savestate.folders:
            savestate.folders[folder].current_file = rel_path
            savestate.folders[folder].files_done += 1

        await self._emit_telemetry(current_file=str(file_path), current_folder=folder)

        try:
            # Extract metadata
            metadata = await self.metadata_extractor.extract(
                file_path,
                follow_symlinks=self.config.symlink_mode == SymlinkMode.FOLLOW
            )

            # Symlink target
            if metadata.is_symlink:
                try:
                    metadata.symlink_target = str(await aiofiles.os.readlink(file_path))
                except OSError:
                    metadata.symlink_target = ""

            # Hardlink detection
            if self.hardlink_tracker:
                if self.hardlink_tracker.register(metadata.inode, metadata.path):
                    metadata.is_hardlink = False
                else:
                    metadata.is_hardlink = True

            # Hash if needed (collision or forced)
            if not unique_size or self.config.track_hardlinks:
                metadata.hash = await self.hash_engine.hash_file(file_path)
                self.hash_count += 1
            else:
                metadata.hash = f"SIZE:{metadata.size}"

            # Write to index
            await index_writer.write_record({
                "hash": metadata.hash,
                "size": metadata.size,
                "path": metadata.path,
                "mtime": metadata.mtime,
                "mode": metadata.mode,
                "uid": metadata.uid,
                "gid": metadata.gid,
                "inode": metadata.inode,
                "is_ref": False,
                "symlink_target": metadata.symlink_target,
            })

            # Update progress
            self.processed_files += 1
            self.processed_bytes += metadata.size

            # Save savestate periodically (every 100 files)
            if self.processed_files % 100 == 0:
                await savestate.save()

            return metadata

        except OSError as e:
            await self._handle_error("io_error", str(file_path), str(e))
            self.error_count += 1
            raise

    async def _process_collision_bucket(
        self,
        files: list[Path],
        size: int,
        savestate: SavestateManager,
        index_writer: IndexWriter,
    ) -> None:
        """Process files with same size - need to hash to find duplicates."""
        hashes: dict[str, list[Path]] = defaultdict(list)

        for file_path in files:
            try:
                hash_val = await self.hash_engine.hash_file(file_path)
                self.hash_count += 1
                hashes[hash_val].append(file_path)
            except OSError as e:
                await self._handle_error("io_error", str(file_path), str(e))
                self.error_count += 1
                continue

        # Process each hash group
        for _hash_val, file_list in hashes.items():
            for file_path in file_list:
                await self._process_single_file(file_path, savestate, index_writer)

    async def _handle_error(
        self,
        error_type: str,
        path: str,
        detail: str,
    ) -> None:
        """Handle error according to rules."""
        action = self.error_manager.handle_error(error_type, path, detail)

        error_record = ScanError(
            path=path,
            error_type=error_type,
            action=action.value,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            detail=detail,
        )
        self.error_manager.errors.append(error_record)

        if self.ask_callback and action == ErrorAction.ASK:
            action = await self.ask_callback(path, f"{error_type}: {detail}")

        # Log error for debugging (via error_manager)
        # print(f"[ERROR] {error_type} on {path}: {detail} -> {action.value}")


async def run_indexer(config: ScanConfig, root: Path, index_dir: Path) -> tuple[SavestateManager, IndexWriter]:
    """Convenience function to run full index."""
    savestate = SavestateManager(index_dir, root)
    index_writer = IndexWriter(index_dir)

    telemetry_queue = asyncio.Queue()
    indexer = Indexer(config, telemetry_queue)

    async for _ in indexer.scan(root, savestate, index_writer):
        pass

    return savestate, index_writer

