#!/usr/bin/env python3
"""
DataWarden - Indexer Core Module (STUB)
Async scanner with xxHash, metadata extraction, JSONL writer, savestate.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Set
from enum import Enum

import xxhash
import aiofiles
import aiofiles.os

from core.models import ScanConfig, FileMetadata


class ScanStatus(Enum):
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
    completed_at: Optional[str] = None
    error: Optional[str] = None


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
            
            # File type detection
            suffix = path.suffix.lower()
            
            # Symlink target
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
                hash="",  # Filled later
                filetype=suffix,
                is_symlink=stat.S_ISLNK(st.st_mode),
                symlink_target=symlink_target,
                is_hardlink=False,  # Determined by inode tracking
            )
        except OSError as e:
            raise MetadataError(f"Failed to extract metadata: {e}") from e


class FileTypeFilter:
    """Filters files by extension before hashing."""
    
    def __init__(self, whitelist: Optional[List[str]] = None, blacklist: Optional[List[str]] = None):
        self.whitelist = set(w.lower() for w in (whitelist or []))
        self.blacklist = set(b.lower() for b in (blacklist or []))
        self._allow_all = not self.whitelist
    
    def should_process(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        
        # Check blacklist first
        if suffix in self.blacklist:
            return False
        
        # If whitelist exists, must be in it
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
        self.folders: Dict[str, FolderState] = {}
        self.errors: List[ScanError] = []
        self.config_hash = ""
        self.started_at = ""
        self.version = "0.05.30"
    
    def load(self) -> bool:
        """Load savestate from disk."""
        if not self.savestate_path.exists():
            return False
        
        try:
            async with aiofiles.open(self.savestate_path, 'r') as f:
                data = json.loads(await f.read())
            
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
    
    def compress_completed_folders(self) -> None:
        """Compress: remove individual file tracking for completed folders."""
        # Implementation: when folder is COMPLETED, we only keep the folder record
        # Individual file states are no longer needed
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
        self.current_file: Optional[aiofiles.threadpool.AsyncFileIO] = None
    
    async def _open_part(self) -> None:
        """Open a new index part file."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        part_path = self.index_dir / f"part_{self.current_part:03d}.jsonl"
        self.current_file = await aiofiles.open(part_path, 'a')
        self.current_lines = 0
        self.current_bytes = 0
    
    async def write_record(self, record: Dict) -> None:
        """Write a single JSONL record."""
        if self.current_file is None:
            await self._open_part()
        
        line = json.dumps(record, separators=(',', ':')) + '\n'
        line_bytes = line.encode('utf-8')
        
        # Check if we need to split
        if (self.current_lines >= self.max_lines or 
            self.current_bytes + len(line_bytes) > self.max_bytes):
            await self.current_file.close()
            self.current_part += 1
            await self._open_part()
        
        await self.current_file.write(line)
        self.current_lines += 1
        self.current_bytes += len(line_bytes)
    
    async def close(self) -> None:
        """Close current file."""
        if self.current_file:
            await self.current_file.close()
            self.current_file = None
    
    async def write_manifest(self, total_files: int, total_bytes: int, config_hash: str) -> None:
        """Write manifest.json for the index."""
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
    
    def __init__(self, mode: str = "ignore"):
        self.mode = mode  # ignore, follow, record
        self.visited: Set[str] = set()
    
    def should_follow(self, path: Path) -> bool:
        if self.mode == "ignore":
            return False
        if self.mode == "record":
            return False
        return True  # follow
    
    def should_record(self, path: Path) -> bool:
        return self.mode in ("follow", "record")
    
    def check_loop(self, resolved_path: Path) -> bool:
        """Check if path creates a loop. Returns True if loop detected."""
        real_path = str(resolved_path.resolve())
        if real_path in self.visited:
            return True
        self.visited.add(real_path)
        return False
    
    def reset(self) -> None:
        self.visited.clear()


class HardlinkTracker:
    """Tracks hardlinks by inode."""
    
    def __init__(self):
        self.inode_map: Dict[int, List[str]] = {}
    
    def register(self, inode: int, path: str) -> bool:
        """Register a file. Returns True if this is the first file for this inode."""
        if inode not in self.inode_map:
            self.inode_map[inode] = [path]
            return True
        self.inode_map[inode].append(path)
        return False
    
    def get_hardlinks(self, inode: int) -> List[str]:
        return self.inode_map.get(inode, [])
    
    def is_hardlink(self, inode: int) -> bool:
        return len(self.inode_map.get(inode, [])) > 1


class ErrorManager:
    """Manages error handling with user-defined rules."""
    
    class Action(Enum):
        ASK = "ASK"
        AUTO_SKIP = "AUTO_SKIP"
        RETRY = "RETRY"
    
    def __init__(self, rules: Dict[str, Action]):
        self.rules = rules
    
    def handle_error(self, error_type: str, path: str, detail: str) -> Action:
        """Determine action for an error."""
        return self.rules.get(error_type, self.Action.ASK)


class MetadataError(Exception):
    pass


class Indexer:
    """Main indexer orchestrating all components."""
    
    def __init__(self, config: ScanConfig):
        self.config = config
        self.hash_engine = HashEngine()
        self.metadata_extractor = MetadataExtractor()
        self.file_filter = FileTypeFilter(config.whitelist, config.blacklist)
        self.symlink_handler = SymlinkHandler(config.symlink_mode)
        self.hardlink_tracker = HardlinkTracker() if config.track_hardlinks else None
        self.error_manager = ErrorManager(config.error_rules)
        
        # Progress tracking
        self.total_files = 0
        self.processed_files = 0
        self.total_bytes = 0
        self.processed_bytes = 0
        self.start_time = time.time()
    
    async def scan(self, root: Path, savestate: SavestateManager, 
                   telemetry_queue: asyncio.Queue) -> AsyncIterator[FileMetadata]:
        """Main scan generator yielding FileMetadata for each file."""
        # TODO: Implement full scan logic with:
        # - Async directory walk
        # - Size-based pre-filtering
        # - Two-pass: size buckets -> hash
        # - Savestate integration
        # - Telemetry updates
        # - Error handling with user rules
        # - Symlink loop detection
        # - Hardlink tracking
        # - JSONL writing with splitting
        raise NotImplementedError("Indexer.scan() - implement in Phase 1")
    
    def get_stats(self) -> Dict:
        elapsed = time.time() - self.start_time
        return {
            "files_per_sec": self.processed_files / elapsed if elapsed > 0 else 0,
            "mb_per_sec": (self.processed_bytes / 1024 / 1024) / elapsed if elapsed > 0 else 0,
            "eta": (self.total_files - self.processed_files) / (self.processed_files / elapsed) if self.processed_files > 0 and elapsed > 0 else 0,
        }