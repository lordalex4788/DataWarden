"""Tests for Cross-Reference Engine."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.ref_engine import CrossReferenceEngine, RefEngine


class TestCrossReferenceEngine:
    """Tests for CrossReferenceEngine."""

    def _create_test_index(self, index_dir: Path, index_name: str, records: list[dict]) -> None:
        """Create a test index directory with JSONL files and manifest."""
        index_dir.mkdir(parents=True, exist_ok=True)

        import json

        # Write records to part file
        part_file = index_dir / "part_001.jsonl"
        with open(part_file, 'w') as f:
            for record in records:
                f.write(json.dumps(record) + '\n')

        # Write manifest
        manifest = {
            "version": "1.0",
            "parts": 1,
            "total_files": len(records),
            "total_bytes": sum(r.get("size", 0) for r in records),
            "config_hash": "test_hash",
            "created_at": "2024-01-01T00:00:00Z",
        }
        manifest_path = index_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            f.write(json.dumps(manifest, indent=2))

    def test_load_index(self, tmp_path):
        """Test loading an index."""
        engine = CrossReferenceEngine()

        records = [
            {"hash": "abc123", "size": 100, "path": "/test/a.txt", "mtime": 1000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 1, "is_ref": False, "symlink_target": None},
            {"hash": "abc123", "size": 100, "path": "/test/b.txt", "mtime": 2000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 2, "is_ref": False, "symlink_target": None},
            {"hash": "def456", "size": 200, "path": "/test/c.txt", "mtime": 3000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 3, "is_ref": False, "symlink_target": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "test_index"
            self._create_test_index(index_dir, "test", records)

            count = engine.load_index("test", index_dir)
            assert count == 3

    def test_intra_folder_duplicates(self, tmp_path):
        """Test finding duplicates within a single index."""
        engine = CrossReferenceEngine()

        # Three files, two with same hash (duplicates)
        records = [
            {"hash": "abc123", "size": 100, "path": "/test/a.txt", "mtime": 1000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 1, "is_ref": False, "symlink_target": None},
            {"hash": "abc123", "size": 100, "path": "/test/b.txt", "mtime": 2000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 2, "is_ref": False, "symlink_target": None},
            {"hash": "def456", "size": 200, "path": "/test/c.txt", "mtime": 3000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 3, "is_ref": False, "symlink_target": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "test_index"
            self._create_test_index(index_dir, "test", records)

            engine.load_index("test", index_dir)
            groups = engine.find_duplicates_intra("test")

            assert len(groups) == 1
            group = groups[0]
            assert group.hash == "abc123"
            assert group.size == 100
            assert len(group.files) == 2
            assert group.wasted_bytes == 100  # 100 * (2-1)

    def test_intra_no_duplicates(self):
        """Test intra-folder with no duplicates."""
        engine = CrossReferenceEngine()

        records = [
            {"hash": "abc123", "size": 100, "path": "/test/a.txt", "mtime": 1000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 1, "is_ref": False, "symlink_target": None},
            {"hash": "def456", "size": 200, "path": "/test/b.txt", "mtime": 2000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 2, "is_ref": False, "symlink_target": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "test_index"
            self._create_test_index(index_dir, "test", records)

            engine.load_index("test", index_dir)
            groups = engine.find_duplicates_intra("test")

            assert len(groups) == 0

    def test_inter_folder_duplicates(self):
        """Test finding duplicates between reference and target indexes."""
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

            self._create_test_index(ref_dir, "ref", ref_records)
            self._create_test_index(target_dir, "target", target_records)

            engine.load_index("ref", ref_dir)
            engine.load_index("target", target_dir)

            # Set ref as reference
            engine.set_references(["ref"])

            groups = engine.find_duplicates_inter(["ref"], ["target"])

            assert len(groups) == 1
            group = groups[0]
            assert group.hash == "abc123"
            assert len(group.files) == 2
            # Check reference protection
            ref_files = group.reference_files
            non_ref_files = group.non_reference_files
            assert len(ref_files) == 1
            assert ref_files[0].metadata.path == "/ref/a.txt"
            assert len(non_ref_files) == 1
            assert non_ref_files[0].metadata.path == "/target/a_copy.txt"

    def test_reference_protection(self):
        """Test that reference files are never marked for deletion.
        When an index is marked as reference, ALL its files become references.
        """
        engine = CrossReferenceEngine()

        # Both files in ref index
        records = [
            {"hash": "abc123", "size": 100, "path": "/ref/a.txt", "mtime": 1000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 1, "is_ref": False, "symlink_target": None},
            {"hash": "abc123", "size": 100, "path": "/ref/b.txt", "mtime": 2000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 2, "is_ref": False, "symlink_target": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "ref_index"
            self._create_test_index(index_dir, "ref", records)

            engine.load_index("ref", index_dir)
            engine.set_references(["ref"])

            groups = engine.find_duplicates_intra("ref")

            assert len(groups) == 1
            group = groups[0]
            # Both files are now references (set_references marks all files in the index as references)
            ref_files = group.reference_files
            non_ref_files = group.non_reference_files
            assert len(ref_files) == 2
            assert len(non_ref_files) == 0
            assert ref_files[0].metadata.path == "/ref/a.txt"
            assert ref_files[1].metadata.path == "/ref/b.txt"

    def test_ref_engine_integration(self):
        """Test RefEngine high-level API."""
        ref_engine = RefEngine()

        ref_records = [
            {"hash": "abc123", "size": 100, "path": "/ref/a.txt", "mtime": 1000, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 1, "is_ref": False, "symlink_target": None},
        ]

        target_records = [
            {"hash": "abc123", "size": 100, "path": "/target/a.txt", "mtime": 1500, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 2, "is_ref": False, "symlink_target": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ref_dir = tmp_path / "ref"
            target_dir = tmp_path / "target"

            self._create_test_index(ref_dir, "ref", ref_records)
            self._create_test_index(target_dir, "target", target_records)

            counts = ref_engine.load_indexes({"ref": ref_dir, "target": target_dir})
            assert counts["ref"] == 1
            assert counts["target"] == 1

            # Compare
            result = ref_engine.compare_inter(["ref"], ["target"])

            assert result.total_groups == 1
            assert result.total_wasted_bytes == 100
            assert result.reference_protected_count == 1
            assert result.scan_time > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
