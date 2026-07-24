#!/usr/bin/env python3
"""
DataWarden - Cross-Reference Engine (STUB)
In-memory duplicate detection with intra/inter folder modes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.models import FileMetadata


@dataclass
class DuplicateFile:
    """A file within a duplicate group."""
    path: str
    size: int
    mtime: int
    mode: int
    uid: int
    gid: int
    inode: int
    is_ref: bool = False
    source_index: str = ""


@dataclass
class DuplicateGroup:
    """A group of duplicate files (same hash + size)."""
    hash: str
    size: int
    files: List[DuplicateFile]
    ref_files: List[DuplicateFile]
    non_ref_files: List[DuplicateFile]
    
    @property
    def total_wasted_bytes(self) -> int:
        """Bytes wasted by duplicates (excluding reference files)."""
        if len(self.non_ref_files) <= 1:
            return 0
        return self.size * (len(self.non_ref_files) - 1)


@dataclass
class ComparisonResult:
    """Result of a cross-reference comparison."""
    groups: List[DuplicateGroup]
    total_groups: int
    total_wasted_bytes: int
    ref_protected_count: int
    scan_time: float


class CrossReferenceEngine:
    """
    Loads JSONL indexes and finds duplicates.
    Supports intra-folder (self) and inter-folder (cross) comparisons.
    """
    
    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self.loaded_indexes: Dict[str, str] = {}  # index_name -> index_path
    
    def load_index(self, index_name: str, index_dir: Path) -> None:
        """Load a JSONL index into in-memory SQLite."""
        manifest_path = index_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"No manifest found in {index_dir}")
        
        # Create in-memory database
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE files (
                hash TEXT,
                size INTEGER,
                path TEXT,
                mtime INTEGER,
                mode INTEGER,
                uid INTEGER,
                gid INTEGER,
                inode INTEGER,
                is_ref INTEGER DEFAULT 0,
                source_index TEXT
            )
        """)
        self.conn.execute("CREATE INDEX idx_hash_size ON files(hash, size)")
        self.conn.execute("CREATE INDEX idx_source ON files(source_index)")
        
        # Load all part files
        import json
        for part_file in sorted(index_dir.glob("part_*.jsonl")):
            with open(part_file, 'r') as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        record['source_index'] = index_name
                        self.conn.execute("""
                            INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            record['hash'], record['size'], record['path'],
                            record['mtime'], record['mode'], record['uid'],
                            record['gid'], record['inode'], 
                            1 if record.get('is_ref') else 0,
                            index_name
                        ))
        
        self.conn.commit()
        self.loaded_indexes[index_name] = str(index_dir)
    
    def set_references(self, index_names: List[str]) -> None:
        """Mark all files from given indexes as references."""
        if not self.conn:
            return
        placeholders = ','.join('?' * len(index_names))
        self.conn.execute(
            f"UPDATE files SET is_ref = 1 WHERE source_index IN ({placeholders})",
            index_names
        )
        self.conn.commit()
    
    def find_duplicates_intra(self, index_name: str) -> List[DuplicateGroup]:
        """Find duplicates within a single index."""
        if not self.conn:
            return []
        
        cursor = self.conn.execute("""
            SELECT hash, size, COUNT(*) as cnt
            FROM files
            WHERE source_index = ?
            GROUP BY hash, size
            HAVING COUNT(*) > 1
        """, (index_name,))
        
        groups = []
        for hash_val, size, cnt in cursor:
            groups.append(self._build_group(hash_val, size, index_name))
        return groups
    
    def find_duplicates_inter(self, ref_indexes: List[str], target_indexes: List[str]) -> List[DuplicateGroup]:
        """Find duplicates between reference and target indexes."""
        if not self.conn:
            return []
        
        all_indexes = ref_indexes + target_indexes
        placeholders = ','.join('?' * len(all_indexes))
        
        cursor = self.conn.execute(f"""
            SELECT hash, size, COUNT(*) as cnt
            FROM files
            WHERE source_index IN ({placeholders})
            GROUP BY hash, size
            HAVING COUNT(*) > 1
        """, all_indexes)
        
        groups = []
        for hash_val, size, cnt in cursor:
            groups.append(self._build_group(hash_val, size, all_indexes))
        return groups
    
    def _build_group(self, hash_val: str, size: int, index_names: List[str]) -> DuplicateGroup:
        """Build a DuplicateGroup from database."""
        placeholders = ','.join('?' * len(index_names))
        cursor = self.conn.execute(f"""
            SELECT path, size, mtime, mode, uid, gid, inode, is_ref, source_index
            FROM files
            WHERE hash = ? AND size = ? AND source_index IN ({placeholders})
        """, [hash_val, size] + index_names)
        
        files = []
        ref_files = []
        non_ref_files = []
        
        for row in cursor:
            dup_file = DuplicateFile(
                path=row[0], size=row[1], mtime=row[2], mode=row[3],
                uid=row[4], gid=row[5], inode=row[6],
                is_ref=bool(row[7]), source_index=row[8]
            )
            files.append(dup_file)
            if dup_file.is_ref:
                ref_files.append(dup_file)
            else:
                non_ref_files.append(dup_file)
        
        return DuplicateGroup(
            hash=hash_val,
            size=size,
            files=files,
            ref_files=ref_files,
            non_ref_files=non_ref_files
        )
    
    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None


class RefEngine:
    """High-level reference engine combining loading and comparison."""
    
    def __init__(self):
        self.engine = CrossReferenceEngine()
    
    def load_indexes(self, indexes: Dict[str, Path]) -> None:
        """Load multiple indexes. indexes = {name: path}."""
        for name, path in indexes.items():
            self.engine.load_index(name, path)
    
    def compare_intra(self, index_name: str) -> ComparisonResult:
        """Compare index against itself."""
        import time
        start = time.time()
        groups = self.engine.find_duplicates_intra(index_name)
        elapsed = time.time() - start
        return self._make_result(groups, elapsed)
    
    def compare_inter(self, ref_names: List[str], target_names: List[str]) -> ComparisonResult:
        """Compare reference indexes against target indexes."""
        import time
        start = time.time()
        # Set reference flags
        self.engine.set_references(ref_names)
        groups = self.engine.find_duplicates_inter(ref_names, target_names)
        elapsed = time.time() - start
        return self._make_result(groups, elapsed)
    
    def _make_result(self, groups: List[DuplicateGroup], elapsed: float) -> ComparisonResult:
        total_wasted = sum(g.total_wasted_bytes for g in groups)
        ref_protected = sum(len(g.ref_files) for g in groups)
        return ComparisonResult(
            groups=groups,
            total_groups=len(groups),
            total_wasted_bytes=total_wasted,
            ref_protected_count=ref_protected,
            scan_time=elapsed
        )