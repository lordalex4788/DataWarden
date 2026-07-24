#!/usr/bin/env python3
"""
DataWarden - Cross-Reference Engine
In-memory SQLite-based duplicate detection with intra/inter folder modes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from core.models import (
    ComparisonResult,
    DuplicateFile,
    DuplicateGroup,
    FileMetadata,
)


class CrossReferenceEngine:
    """
    Loads JSONL indexes and finds duplicates.
    Supports intra-folder (self) and inter-folder (cross) comparisons.
    """

    def __init__(self):
        self.conn: sqlite3.Connection | None = None
        self.loaded_indexes: dict[str, str] = {}
        self._db_initialized = False

    def _ensure_db(self) -> None:
        """Initialize the in-memory database if not already done."""
        if self._db_initialized:
            return
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        self._create_indexes()
        self._db_initialized = True

    def load_index(self, index_name: str, index_dir: Path) -> int:
        """
        Load a JSONL index into in-memory SQLite.
        Returns number of records loaded.
        """
        manifest_path = index_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"No manifest found in {index_dir}")

        self._ensure_db()

        # Load all part files
        total_records = 0
        for part_file in sorted(index_dir.glob("part_*.jsonl")):
            with open(part_file) as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        record['source_index'] = index_name
                        self._insert_record(record)
                        total_records += 1

        self.conn.commit()

        self.loaded_indexes[index_name] = str(index_dir)
        return total_records

    def _create_schema(self) -> None:
        """Create database schema."""
        self.conn.execute("""
            CREATE TABLE files (
                hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                mtime INTEGER NOT NULL,
                mode INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                gid INTEGER NOT NULL,
                inode INTEGER NOT NULL,
                is_ref INTEGER DEFAULT 0,
                source_index TEXT NOT NULL,
                symlink_target TEXT
            )
        """)

    def _create_indexes(self) -> None:
        """Create database indexes for query performance."""
        self.conn.execute("CREATE INDEX idx_hash_size ON files(hash, size)")
        self.conn.execute("CREATE INDEX idx_source ON files(source_index)")
        self.conn.execute("CREATE INDEX idx_is_ref ON files(is_ref)")
        self.conn.execute("CREATE INDEX idx_inode ON files(inode)")

    def _insert_record(self, record: dict) -> None:
        """Insert a single record into the database."""
        self.conn.execute("""
            INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record['hash'],
            record['size'],
            record['path'],
            record['mtime'],
            record['mode'],
            record['uid'],
            record['gid'],
            record['inode'],
            1 if record.get('is_ref', False) else 0,
            record.get('source_index', ''),
            record.get('symlink_target'),
        ))

    def set_references(self, index_names: list[str]) -> None:
        """Mark all files from given indexes as references."""
        if not self.conn or not index_names:
            return
        placeholders = ','.join('?' * len(index_names))
        self.conn.execute(
            f"UPDATE files SET is_ref = 1 WHERE source_index IN ({placeholders})",
            index_names
        )
        self.conn.commit()

    def find_duplicates_intra(self, index_name: str) -> list[DuplicateGroup]:
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
        for row in cursor:
            groups.append(self._build_group(row['hash'], row['size'], [index_name]))
        return groups

    def find_duplicates_inter(self, ref_indexes: list[str], target_indexes: list[str]) -> list[DuplicateGroup]:
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
        for row in cursor:
            groups.append(self._build_group(row['hash'], row['size'], all_indexes))
        return groups

    def _build_group(self, hash_val: str, size: int, index_names: list[str]) -> DuplicateGroup:
        """Build a DuplicateGroup from database."""
        placeholders = ','.join('?' * len(index_names))
        cursor = self.conn.execute(f"""
            SELECT path, size, mtime, mode, uid, gid, inode, is_ref, source_index, symlink_target
            FROM files
            WHERE hash = ? AND size = ? AND source_index IN ({placeholders})
        """, [hash_val, size] + index_names)

        files = []
        for row in cursor:
            # Create FileMetadata from database row
            metadata = FileMetadata(
                path=row['path'],
                size=row['size'],
                mtime=row['mtime'],
                ctime=row['mtime'],
                atime=row['mtime'],
                mode=row['mode'],
                uid=row['uid'],
                gid=row['gid'],
                inode=row['inode'],
                hash=hash_val,
                file_type=Path(row['path']).suffix.lower(),
                is_symlink=False,
                symlink_target=row['symlink_target'],
                is_hardlink=False,
            )
            dup_file = DuplicateFile(
                metadata=metadata,
                is_reference=bool(row['is_ref']),
            )
            files.append(dup_file)

        return DuplicateGroup(hash=hash_val, size=size, files=files)

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None


class RefEngine:
    """High-level reference engine combining loading and comparison."""

    def __init__(self):
        self.engine = CrossReferenceEngine()

    def load_indexes(self, indexes: dict[str, Path]) -> dict[str, int]:
        """Load multiple indexes. Returns {name: record_count}."""
        counts = {}
        for name, path in indexes.items():
            counts[name] = self.engine.load_index(name, path)
        return counts

    def compare_intra(self, index_name: str) -> ComparisonResult:
        """Compare index against itself."""
        start = time.time()
        groups = self.engine.find_duplicates_intra(index_name)
        elapsed = time.time() - start
        return self._make_result(groups, elapsed)

    def compare_inter(self, ref_names: list[str], target_names: list[str]) -> ComparisonResult:
        """Compare reference indexes against target indexes."""
        start = time.time()
        # Set reference flags
        self.engine.set_references(ref_names)
        groups = self.engine.find_duplicates_inter(ref_names, target_names)
        elapsed = time.time() - start
        return self._make_result(groups, elapsed)

    def _make_result(self, groups: list[DuplicateGroup], elapsed: float) -> ComparisonResult:
        total_wasted = sum(g.wasted_bytes for g in groups)
        ref_protected = sum(len(g.reference_files) for g in groups)
        return ComparisonResult(
            groups=groups,
            total_groups=len(groups),
            total_wasted_bytes=total_wasted,
            reference_protected_count=ref_protected,
            scan_time=elapsed
        )

    def close(self) -> None:
        self.engine.close()
