"""Tests for core indexer module."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.indexer import (
    FileTypeFilter,
    HardlinkTracker,
    HashEngine,
    IndexWriter,
    SavestateManager,
    SymlinkHandler,
    SymlinkMode,
)


class TestHashEngine:
    """Tests for HashEngine."""

    @pytest.mark.asyncio
    async def test_hash_file_xxh3(self, tmp_path):
        """Test xxHash3 hashing of a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"Hello, World!")

        hash_result = await HashEngine.hash_file(test_file)

        assert isinstance(hash_result, str)
        assert len(hash_result) == 16  # xxh3_64 hex = 16 chars

    @pytest.mark.asyncio
    async def test_hash_empty_file(self, tmp_path):
        """Test hashing an empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")

        hash_result = await HashEngine.hash_file(test_file)

        assert hash_result == HashEngine.hash_bytes(b"")


class TestFileTypeFilter:
    """Tests for FileTypeFilter."""

    def test_whitelist_only(self):
        """Test whitelist filtering."""
        filter = FileTypeFilter(whitelist=[".txt", ".md"], blacklist=[])

        assert filter.should_process(Path("test.txt")) is True
        assert filter.should_process(Path("test.md")) is True
        assert filter.should_process(Path("test.py")) is False

    def test_blacklist_only(self):
        """Test blacklist filtering."""
        filter = FileTypeFilter(whitelist=[], blacklist=[".tmp", ".bak"])

        assert filter.should_process(Path("test.txt")) is True
        assert filter.should_process(Path("test.tmp")) is False
        assert filter.should_process(Path("test.bak")) is False

    def test_whitelist_and_blacklist(self):
        """Test both whitelist and blacklist."""
        filter = FileTypeFilter(whitelist=[".txt", ".log"], blacklist=[".tmp"])

        assert filter.should_process(Path("test.txt")) is True
        assert filter.should_process(Path("test.log")) is True
        assert filter.should_process(Path("test.tmp")) is False  # blacklisted
        assert filter.should_process(Path("test.py")) is False  # not whitelisted

    def test_case_insensitive(self):
        """Test case insensitive extension matching."""
        filter = FileTypeFilter(whitelist=[".TXT", ".Md"])

        assert filter.should_process(Path("test.txt")) is True
        assert filter.should_process(Path("test.TXT")) is True
        assert filter.should_process(Path("test.md")) is True
        assert filter.should_process(Path("test.MD")) is True

    def test_size_filter(self):
        """Test file size filtering."""
        filter = FileTypeFilter()

        assert filter.should_process_size(100, 0, 1000) is True
        assert filter.should_process_size(50, 100, 1000) is False
        assert filter.should_process_size(1500, 0, 1000) is False
        assert filter.should_process_size(1500, 0, -1) is True  # unlimited max


class TestSavestateManager:
    """Tests for SavestateManager."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        """Test savestate save/load cycle."""
        index_root = tmp_path / "indexes" / "test"
        index_root.mkdir(parents=True)
        root_path = tmp_path / "data"
        root_path.mkdir()

        manager = SavestateManager(index_root, root_path)
        manager.config_hash = "abc123"
        manager.started_at = "2024-01-01T00:00:00Z"

        # Add folder state
        from core.indexer import FolderState, ScanStatus
        manager.folders["/data/photos"] = FolderState(
            path="/data/photos",
            status=ScanStatus.COMPLETED,
            file_count=100,
            completed_at="2024-01-01T01:00:00Z"
        )

        await manager.save()

        # Load new instance
        manager2 = SavestateManager(index_root, root_path)
        loaded = manager2.load()

        assert loaded is True
        assert manager2.config_hash == "abc123"
        assert "/data/photos" in manager2.folders
        assert manager2.folders["/data/photos"].status == ScanStatus.COMPLETED

    def test_is_folder_completed(self):
        """Test folder completion check."""
        manager = SavestateManager(Path("/tmp"), Path("/tmp"))
        from core.indexer import FolderState, ScanStatus

        manager.folders["/done"] = FolderState(path="/done", status=ScanStatus.COMPLETED)
        manager.folders["/pending"] = FolderState(path="/pending", status=ScanStatus.PENDING)
        manager.folders["/failed"] = FolderState(path="/failed", status=ScanStatus.FAILED)

        assert manager.is_folder_completed("/done") is True
        assert manager.is_folder_completed("/pending") is False
        assert manager.is_folder_completed("/failed") is False
        assert manager.is_folder_completed("/nonexistent") is False


class TestSymlinkHandler:
    """Tests for SymlinkHandler."""

    def test_ignore_mode(self):
        """Test IGNORE mode skips all symlinks."""
        handler = SymlinkHandler(SymlinkMode.IGNORE)

        assert handler.should_follow(Path("/any/path")) is False
        assert handler.should_record(Path("/any/path")) is False

    def test_follow_mode(self):
        """Test FOLLOW mode follows symlinks."""
        handler = SymlinkHandler(SymlinkMode.FOLLOW)

        assert handler.should_follow(Path("/any/path")) is True
        assert handler.should_record(Path("/any/path")) is True

    def test_record_only_mode(self):
        """Test RECORD_ONLY mode."""
        handler = SymlinkHandler(SymlinkMode.RECORD_ONLY)

        assert handler.should_follow(Path("/any/path")) is False
        assert handler.should_record(Path("/any/path")) is True

    def test_loop_detection(self, tmp_path):
        """Test symlink loop detection."""
        handler = SymlinkHandler(SymlinkMode.FOLLOW)

        # Create a symlink loop: a -> b -> a
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.symlink_to(b)
        b.symlink_to(a)

        # First visit should be OK (check the symlink itself)
        assert handler.check_loop(a) is False
        # Second visit should detect loop
        assert handler.check_loop(b) is True


class TestHardlinkTracker:
    """Tests for HardlinkTracker."""

    def test_first_file_not_hardlink(self):
        """First file with an inode is not a hardlink."""
        tracker = HardlinkTracker()

        assert tracker.register(12345, "/path/a") is True
        assert tracker.is_hardlink(12345) is False

    def test_second_file_is_hardlink(self):
        """Second file with same inode is a hardlink."""
        tracker = HardlinkTracker()

        tracker.register(12345, "/path/a")
        assert tracker.register(12345, "/path/b") is False
        assert tracker.is_hardlink(12345) is True
        assert tracker.get_hardlinks(12345) == ["/path/a", "/path/b"]


class TestIndexWriter:
    """Tests for IndexWriter."""

    @pytest.mark.asyncio
    async def test_write_and_split(self, tmp_path):
        """Test JSONL writing with auto-split."""
        index_dir = tmp_path / "index"
        writer = IndexWriter(index_dir, max_lines=2, max_mb=1)

        # Write 5 records - should create 3 parts (2+2+1)
        for i in range(5):
            await writer.write_record({"id": i, "data": f"record_{i}"})

        await writer.close()

        parts = list(index_dir.glob("part_*.jsonl"))
        assert len(parts) == 3

        # Verify content
        total_lines = 0
        for part in parts:
            lines = part.read_text().strip().split('\n')
            total_lines += len(lines)
        assert total_lines == 5

    @pytest.mark.asyncio
    async def test_manifest_write(self, tmp_path):
        """Test manifest.json creation."""
        index_dir = tmp_path / "index"
        writer = IndexWriter(index_dir)

        await writer.write_record({"test": 1})
        await writer.close()
        await writer.write_manifest(1, 100, "config_hash_123")

        manifest = index_dir / "manifest.json"
        assert manifest.exists()

        import json
        data = json.loads(manifest.read_text())
        assert data["total_files"] == 1
        assert data["total_bytes"] == 100
        assert data["config_hash"] == "config_hash_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
