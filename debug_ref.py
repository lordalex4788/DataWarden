#!/usr/bin/env python3
"""Debug script for ref_engine."""

import json
import tempfile
from pathlib import Path

from core.ref_engine import CrossReferenceEngine

engine = CrossReferenceEngine()

ref_records = [
    {"hash": "abc123", "size": 100, "path": "/ref/a.txt", "mtime": 1000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 1, "is_ref": False, "symlink_target": None},
    {"hash": "def456", "size": 200, "path": "/ref/b.txt", "mtime": 2000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 2, "is_ref": False, "symlink_target": None},
]

target_records = [
    {"hash": "abc123", "size": 100, "path": "/target/a_copy.txt", "mtime": 1500, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 3, "is_ref": False, "symlink_target": None},
    {"hash": "ghi789", "size": 300, "path": "/target/c.txt", "mtime": 3000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 4, "is_ref": False, "symlink_target": None},
]

with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = Path(tmpdir)
    ref_dir = tmp_path / "ref_index"
    target_dir = tmp_path / "target_index"

    ref_dir.mkdir(parents=True)
    target_dir.mkdir(parents=True)

    # Write ref index
    part_file = ref_dir / "part_001.jsonl"
    with open(part_file, 'w') as f:
        for r in ref_records:
            f.write(json.dumps(r) + "\n")

    manifest = {"version": "1.0", "parts": 1, "total_files": 2, "total_bytes": 300, "config_hash": "test", "created_at": "2024-01-01T00:00:00Z"}
    with open(ref_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    # Write target index
    part_file = target_dir / "part_001.jsonl"
    with open(part_file, "w") as f:
        for r in target_records:
            f.write(json.dumps(r) + "\n")

    manifest = {"version": "1.0", "parts": 1, "total_files": 2, "total_bytes": 400, "config_hash": "test", "created_at": "2024-01-01T00:00:00Z"}
    with open(target_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    # Load and test
    engine.load_index("ref", ref_dir)
    engine.load_index("target", target_dir)

    # Check what's in the database
    cursor = engine.conn.execute("SELECT hash, size, source_index, is_ref FROM files")
    for row in cursor:
        print(f"DB: hash={row[0]}, size={row[1]}, src={row[2]}, is_ref={row[3]}")

    # Test intra
    groups = engine.find_duplicates_intra("ref")
    print(f"Intra ref groups: {len(groups)}")
    for g in groups:
        print(f"  Group: {g.hash}, files={len(g.files)}")

    # Test inter
    engine.set_references(["ref"])
    groups = engine.find_duplicates_inter(["ref"], ["target"])
    print(f"Inter groups: {len(groups)}")
    for g in groups:
        print(f"  Group: {g.hash}, files={len(g.files)}")
        for f in g.files:
            print(f"    {f.metadata.path} is_ref={f.is_reference}")
