"""DataWarden2 - Core Models and Data Classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import time


class SymlinkMode(Enum):
    """How to handle symbolic links during indexing."""
    IGNORE = "ignore"           # Skip symlinks entirely
    FOLLOW = "follow"           # Follow and hash target (with loop protection)
    RECORD_ONLY = "record_only" # Index link only, store target path


class ScanStatus(Enum):
    """Status of a folder/file in savestate."""
    PENDING = "pending"
    SCANNING = "scanning"
    HASHING = "hashing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorAction(Enum):
    """User-defined action for error handling."""
    ASK = "ask"                    # Prompt user interactively
    AUTO_SKIP_AND_LOG = "auto_skip"  # Skip automatically, log error
    RETRY_N_TIMES = "retry"        # Retry N times then ask


class ExecutionMode(Enum):
    """Execution mode for duplicate handling."""
    AUDIT = "audit"           # Dry-run, log only
    SAFE_MOVE = "safe_move"   # Move to quarantine with undo
    HARD_DELETE = "hard_delete"  # Permanent deletion


class TrustLevel(Enum):
    """Global AI trust level."""
    STRICT_ZERO_TRUST = 0      # AI passive only
    LAYOUT_ONLY = 1            # AI may adjust layouts
    ASSISTED_LOGIC = 2         # AI may propose filters (needs confirmation)
    COLLABORATIVE_EXECUTE = 3  # AI may activate filters (delete always human)


@dataclass(frozen=True)
class FileMetadata:
    """Complete file metadata record."""
    path: str
    size: int
    hash: str                 # xxh3_64 hex string
    mtime: float              # Modified time
    ctime: float              # Created time (or metadata change)
    atime: float              # Access time
    mode: int                 # Permissions bits
    uid: int                  # Owner UID
    gid: int                  # Group GID
    inode: int                # Inode number
    is_symlink: bool = False
    symlink_target: Optional[str] = None
    is_hardlink: bool = False
    path_len: int = 0
    file_type: str = ""       # Extension or "no_extension"
    is_ref: bool = False      # Reference folder marker


@dataclass
class ScanConfig:
    """Configuration for indexing scan."""
    root_path: str
    min_size: int = 0
    max_size: int = -1        # -1 = unlimited
    whitelist_ext: List[str] = field(default_factory=list)
    blacklist_ext: List[str] = field(default_factory=list)
    symlink_mode: SymlinkMode = SymlinkMode.IGNORE
    track_hardlinks: bool = True
    treat_hardlinks_as_dupes: bool = False
    max_depth: int = 0        # 0 = unlimited
    follow_mounts: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_path": self.root_path,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "whitelist_ext": self.whitelist_ext,
            "blacklist_ext": self.blacklist_ext,
            "symlink_mode": self.symlink_mode.value,
            "track_hardlinks": self.track_hardlinks,
            "treat_hardlinks_as_dupes": self.treat_hardlinks_as_dupes,
            "max_depth": self.max_depth,
            "follow_mounts": self.follow_mounts,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScanConfig:
        return cls(
            root_path=data["root_path"],
            min_size=data.get("min_size", 0),
            max_size=data.get("max_size", -1),
            whitelist_ext=data.get("whitelist_ext", []),
            blacklist_ext=data.get("blacklist_ext", []),
            symlink_mode=SymlinkMode(data.get("symlink_mode", "ignore")),
            track_hardlinks=data.get("track_hardlinks", True),
            treat_hardlinks_as_dupes=data.get("treat_hardlinks_as_dupes", False),
            max_depth=data.get("max_depth", 0),
            follow_mounts=data.get("follow_mounts", False),
        )


@dataclass
class FolderState:
    """Savestate for a single folder."""
    path: str
    status: ScanStatus
    file_count: int = 0
    files_done: int = 0
    files_total: int = 0
    current_file: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    error_action: Optional[ErrorAction] = None
    config_hash: str = ""


@dataclass
class Savestate:
    """Complete savestate for resume capability."""
    version: str
    root_path: str
    config_hash: str
    started_at: float
    folders: Dict[str, FolderState] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    total_files: int = 0
    completed_files: int = 0
    
    def is_folder_completed(self, path: str) -> bool:
        state = self.folders.get(path)
        return state is not None and state.status == ScanStatus.COMPLETED
    
    def get_pending_folders(self) -> List[str]:
        return [
            path for path, state in self.folders.items()
            if state.status in (ScanStatus.PENDING, ScanStatus.SCANNING, ScanStatus.HASHING)
        ]


@dataclass
class DuplicateFile:
    """A file within a duplicate group."""
    metadata: FileMetadata
    is_reference: bool = False
    decision: str = "pending"  # keep, delete, skip


@dataclass
class DuplicateGroup:
    """A group of duplicate files (same hash)."""
    hash: str
    size: int
    files: List[DuplicateFile] = field(default_factory=list)
    
    @property
    def reference_files(self) -> List[DuplicateFile]:
        return [f for f in self.files if f.is_reference]
    
    @property
    def non_reference_files(self) -> List[DuplicateFile]:
        return [f for f in self.files if not f.is_reference]
    
    @property
    def wasted_bytes(self) -> int:
        """Bytes wasted by duplicates (size * (count - 1))."""
        return self.size * (len(self.files) - 1) if len(self.files) > 1 else 0


@dataclass
class ComparisonResult:
    """Result of cross-reference comparison."""
    groups: List[DuplicateGroup] = field(default_factory=list)
    total_groups: int = 0
    total_wasted_bytes: int = 0
    reference_protected_count: int = 0
    scan_time: float = 0.0


@dataclass
class FilterDecision:
    """Result of a filter evaluation."""
    action: str  # KEEP, DELETE, SKIP
    confidence: float  # 0.0 - 1.0
    reason: str
    filter_name: str


@dataclass
class Snapshot:
    """Transaction snapshot for undo/rollback."""
    id: str
    timestamp: float
    mode: ExecutionMode
    mappings: Dict[str, str]  # quarantine_path -> original_path
    total_size: int
    filter_config_hash: str
    description: str = ""


@dataclass
class WardenZone:
    """Filesystem zone to monitor."""
    path: str
    name: str
    expected_permissions: str = "640"  # e.g., "640"
    naming_regex: str = ""
    classification_rules: Dict[str, Any] = field(default_factory=dict)
    auto_fix_permissions: bool = True
    auto_fix_naming: bool = False
    llm_triage: bool = True


@dataclass
class WardenIncident:
    """Incident detected by FileSystem Warden."""
    timestamp: float
    zone: str
    file_path: str
    incident_type: str  # permission, naming, classification
    severity: str       # info, warning, critical
    description: str
    llm_suggestion: Optional[str] = None
    status: str = "open"  # open, auto_fixed, pending_review, resolved
    resolved_at: Optional[float] = None
    resolved_by: str = ""


@dataclass
class TelemetryData:
    """Live telemetry metrics."""
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