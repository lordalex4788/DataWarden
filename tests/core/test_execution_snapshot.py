#!/usr/bin/env python3
"""Tests for Phase 4: Execution Engine & Snapshots."""

import tempfile
from pathlib import Path

import pytest

from core.execution import ExecutionEngine, InitialSnapshotPrompt
from core.models import DuplicateFile, DuplicateGroup, ExecutionMode, FileMetadata
from core.snapshot import SnapshotManager


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def create_test_file_metadata(path: str, size: int = 1024) -> FileMetadata:
    """Create a test FileMetadata object."""
    return FileMetadata(
        path=path,
        size=size,
        hash="abc123",
        mtime=1000000,
        ctime=1000000,
        atime=1000000,
        mode=0o644,
        uid=1000,
        gid=1000,
        inode=1000,
        is_ref=False,
    )


def create_test_group(
    hash_val: str = "abc123",
    files_data: list[tuple[str, bool, int]] = None
) -> DuplicateGroup:
    """Create a test DuplicateGroup."""
    if files_data is None:
        files_data = [("/test/file1.txt", False, 1024), ("/test/file2.txt", False, 1024)]

    files = []
    for _i, (path, is_ref, size) in enumerate(files_data):
        meta = create_test_file_metadata(path, size)
        files.append(DuplicateFile(metadata=meta, is_reference=is_ref))

    return DuplicateGroup(hash=hash_val, size=files_data[0][2], files=files)


class TestExecutionEngine:
    """Test ExecutionEngine class."""

    @pytest.fixture
    def snapshot_manager(self, temp_dir):
        return SnapshotManager(quarantine_root=str(temp_dir / "quarantine"))

    @pytest.fixture
    def execution_engine(self, snapshot_manager):
        return ExecutionEngine(snapshot_manager=snapshot_manager)

    def test_audit_mode(self, execution_engine):
        """Test AUDIT mode - dry run only logs."""
        group = create_test_group(files_data=[
            ("/test/file1.txt", False, 1024),
            ("/test/file2.txt", True, 1024),  # reference file
        ])

        selections = {
            "abc123": {
                "/test/file1.txt": "delete",
                "/test/file2.txt": "keep",
            }
        }

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.AUDIT,
        )

        assert result["mode"] == "audit"
        assert len(result["executed"]) == 1  # only file1.txt
        assert len(result["skipped"]) == 1   # file2.txt
        assert result["snapshot_id"] is None  # no snapshot in audit mode
        assert result["dry_run"] is False

    def test_audit_mode_dry_run(self, execution_engine):
        """Test AUDIT mode with dry_run=True."""
        group = create_test_group()
        selections = {"abc123": {"/test/file1.txt": "delete"}}

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.AUDIT,
            dry_run=True,
        )

        assert result["dry_run"] is True

    def test_safe_move_mode(self, execution_engine, temp_dir):
        """Test SAFE_MOVE mode - files moved to quarantine."""
        # Create actual test files
        test_file = temp_dir / "source" / "test.txt"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        # Create group with real file
        meta = create_test_file_metadata(str(test_file))
        group = DuplicateGroup(
            hash="abc123",
            size=len("test content"),
            files=[DuplicateFile(metadata=meta, is_reference=False)]
        )

        selections = {"abc123": {str(test_file): "delete"}}

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.SAFE_MOVE,
        )

        assert result["mode"] == "safe_move"
        assert len(result["executed"]) == 1
        assert result["snapshot_id"] is not None

        # Verify file was moved to quarantine (may be under mount point subdir)
        assert not test_file.exists()
        quarantine_files = list((temp_dir / "quarantine").rglob("test.txt"))
        assert len(quarantine_files) == 1

    def test_hard_delete_mode(self, execution_engine, temp_dir):
        """Test HARD_DELETE mode - files permanently deleted."""
        test_file = temp_dir / "source" / "test.txt"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        meta = create_test_file_metadata(str(test_file))
        group = DuplicateGroup(
            hash="abc123",
            size=len("test content"),
            files=[DuplicateFile(metadata=meta, is_reference=False)]
        )

        selections = {"abc123": {str(test_file): "delete"}}

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.HARD_DELETE,
        )

        assert result["mode"] == "hard_delete"
        assert len(result["executed"]) == 1
        assert result["snapshot_id"] is not None
        assert not test_file.exists()

    def test_keep_files_skipped(self, execution_engine):
        """Test that 'keep' action skips files."""
        group = create_test_group()
        selections = {"abc123": {"/test/file1.txt": "keep"}}

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.SAFE_MOVE,
        )

        assert len(result["skipped"]) == 1
        assert len(result["executed"]) == 0

    def test_unknown_action_skipped(self, execution_engine):
        """Test that unknown actions are skipped."""
        group = create_test_group()
        selections = {"abc123": {"/test/file1.txt": "unknown_action"}}

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.SAFE_MOVE,
        )

        assert len(result["skipped"]) == 1

    def test_error_handling_missing_file(self, execution_engine):
        """Test error handling when source file doesn't exist."""
        group = create_test_group(files_data=[
            ("/nonexistent/file.txt", False, 1024),
        ])
        selections = {"abc123": {"/nonexistent/file.txt": "delete"}}

        result = execution_engine.execute(
            groups=[group],
            selections=selections,
            mode=ExecutionMode.SAFE_MOVE,
        )

        assert len(result["errors"]) == 1
        assert "Source not found" in result["errors"][0]["error"]


class TestSnapshotManager:
    """Test SnapshotManager class."""

    @pytest.fixture
    def snapshot_manager(self, temp_dir):
        return SnapshotManager(
            quarantine_root=str(temp_dir / "quarantine"),
            max_size_gb=1.0,
            max_count=5,
        )

    def test_create_snapshot(self, snapshot_manager, temp_dir):
        """Test creating a snapshot."""
        # Create a test file in quarantine
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        mappings = {str(test_file): "/original/path/test.txt"}

        snapshot = snapshot_manager.create_snapshot(
            mappings=mappings,
            mode=ExecutionMode.SAFE_MOVE,
            filter_config_hash="hash123",
            description="Test snapshot",
        )

        assert snapshot.id.startswith("snap_")
        assert snapshot.mode == ExecutionMode.SAFE_MOVE
        assert snapshot.total_size == len("content")
        assert snapshot.filter_config_hash == "hash123"
        assert snapshot.description == "Test snapshot"

        # Verify snapshot file exists
        snap_file = snapshot_manager.snapshots_dir / f"{snapshot.id}.json"
        assert snap_file.exists()

    def test_rollback_snapshot(self, snapshot_manager, temp_dir):
        """Test rolling back a snapshot."""
        # Create test file in quarantine
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")
        original_path = "/original/path/test.txt"

        mappings = {str(test_file): original_path}
        snapshot = snapshot_manager.create_snapshot(
            mappings=mappings,
            mode=ExecutionMode.SAFE_MOVE,
        )

        # Rollback
        results = snapshot_manager.rollback(snapshot.id)

        assert results[original_path] is True
        assert not test_file.exists()

    def test_rollback_hard_delete(self, snapshot_manager):
        """Test that hard delete snapshots cannot be rolled back."""
        mappings = {"DELETED:/path/file.txt": "/path/file.txt"}
        snapshot = snapshot_manager.create_snapshot(
            mappings=mappings,
            mode=ExecutionMode.HARD_DELETE,
        )

        results = snapshot_manager.rollback(snapshot.id)
        assert results["/path/file.txt"] is False

    def test_rollback_audit_log(self, snapshot_manager):
        """Test that audit log snapshots cannot be rolled back."""
        mappings = {"AUDIT_LOG_ONLY:/path/file.txt": "/path/file.txt"}
        snapshot = snapshot_manager.create_snapshot(
            mappings=mappings,
            mode=ExecutionMode.AUDIT,
        )

        results = snapshot_manager.rollback(snapshot.id)
        assert results["/path/file.txt"] is False

    def test_list_snapshots(self, snapshot_manager, temp_dir):
        """Test listing snapshots."""
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        for i in range(3):
            mappings = {str(test_file): f"/original{i}.txt"}
            snapshot_manager.create_snapshot(
                mappings=mappings,
                mode=ExecutionMode.SAFE_MOVE,
            )

        snapshots = snapshot_manager.list_snapshots()
        assert len(snapshots) == 3

    def test_get_snapshot(self, snapshot_manager, temp_dir):
        """Test getting a specific snapshot."""
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        mappings = {str(test_file): "/original.txt"}
        created = snapshot_manager.create_snapshot(
            mappings=mappings,
            mode=ExecutionMode.SAFE_MOVE,
        )

        retrieved = snapshot_manager.get_snapshot(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_nonexistent_snapshot(self, snapshot_manager):
        """Test getting a non-existent snapshot returns None."""
        result = snapshot_manager.get_snapshot("nonexistent")
        assert result is None

    def test_retention_count(self, snapshot_manager, temp_dir):
        """Test retention policy by count."""
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        # Create more snapshots than max_count
        for i in range(7):
            mappings = {str(test_file): f"/original{i}.txt"}
            snapshot_manager.create_snapshot(
                mappings=mappings,
                mode=ExecutionMode.SAFE_MOVE,
            )

        snapshots = snapshot_manager.list_snapshots()
        assert len(snapshots) <= 5  # max_count = 5

    def test_retention_size(self, snapshot_manager, temp_dir):
        """Test retention policy by size."""
        # Create large files
        for i in range(3):
            test_file = temp_dir / "quarantine" / f"large{i}.txt"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("x" * 500_000_000)  # 500MB each

            mappings = {str(test_file): f"/original{i}.txt"}
            snapshot_manager.create_snapshot(
                mappings=mappings,
                mode=ExecutionMode.SAFE_MOVE,
            )

        snapshots = snapshot_manager.list_snapshots()
        total_size = sum(s.total_size for s in snapshots)
        max_bytes = int(1.0 * 1024 * 1024 * 1024)  # 1GB
        assert total_size <= max_bytes

    def test_quarantine_usage(self, snapshot_manager, temp_dir):
        """Test getting quarantine usage."""
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        used, limit = snapshot_manager.get_quarantine_usage()
        assert used == len("content")
        assert limit == int(1.0 * 1024 * 1024 * 1024)

    def test_prune_empty_dirs(self, snapshot_manager, temp_dir):
        """Test pruning empty directories."""
        # Create nested empty dirs
        (temp_dir / "quarantine" / "a" / "b" / "c").mkdir(parents=True)
        (temp_dir / "quarantine" / "a" / "b" / "d").mkdir(parents=True)

        count = snapshot_manager.prune_empty_dirs()
        # Should remove empty dirs from bottom up
        assert count >= 3


class TestInitialSnapshotPrompt:
    """Test InitialSnapshotPrompt class."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_should_prompt_first_run(self, temp_dir):
        """Test prompt shows on first run."""
        prompt = InitialSnapshotPrompt(temp_dir / "config")
        assert prompt.should_prompt() is True

    def test_no_prompt_after_mark_done(self, temp_dir):
        """Test prompt doesn't show after marking done."""
        prompt = InitialSnapshotPrompt(temp_dir / "config")
        prompt.mark_done()
        assert prompt.should_prompt() is False

    def test_get_prompt_text(self, temp_dir):
        """Test prompt text content."""
        prompt = InitialSnapshotPrompt(temp_dir / "config")
        text = prompt.get_prompt_text()
        assert "initial system snapshot" in text.lower()
        assert "recommended" in text.lower()

    def test_mark_done_creates_file(self, temp_dir):
        """Test mark_done creates marker file."""
        config_dir = temp_dir / "config"
        prompt = InitialSnapshotPrompt(config_dir)
        prompt.mark_done()

        marker = config_dir / ".initial_snapshot_done"
        assert marker.exists()
        # Timestamp is float, not just digits
        assert marker.read_text().replace('.', '').isdigit()


class TestPropertyBased:
    """Property-based tests for determinism."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_snapshot_creation_deterministic(self, temp_dir):
        """Snapshot creation with same inputs should be deterministic."""
        manager = SnapshotManager(quarantine_root=str(temp_dir / "quarantine"))
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        mappings = {str(test_file): "/original.txt"}

        snap1 = manager.create_snapshot(mappings, ExecutionMode.SAFE_MOVE, "hash")
        snap2 = manager.create_snapshot(mappings, ExecutionMode.SAFE_MOVE, "hash")

        # Different IDs (time-based) but same structure
        assert snap1.mode == snap2.mode
        assert snap1.mappings == snap2.mappings
        assert snap1.total_size == snap2.total_size

    def test_rollback_idempotent(self, temp_dir):
        """Rolling back same snapshot twice - second should fail gracefully."""
        manager = SnapshotManager(quarantine_root=str(temp_dir / "quarantine"))
        test_file = temp_dir / "quarantine" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        mappings = {str(test_file): "/original.txt"}
        snap = manager.create_snapshot(mappings, ExecutionMode.SAFE_MOVE)

        # First rollback
        results1 = manager.rollback(snap.id)
        assert results1["/original.txt"] is True

        # Second rollback - file no longer in quarantine
        results2 = manager.rollback(snap.id)
        assert results2["/original.txt"] is False
