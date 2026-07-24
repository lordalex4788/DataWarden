"""Tests for Phase 3: Smart Selector Pipeline."""


import pytest

from core.models import DuplicateFile, FileMetadata
from core.selector import (
    FILTER_REGISTRY,
    ArtifactFilter,
    DuplicateGroup,
    FilenameHygieneFilter,
    FilterAction,
    FilterDecision,
    FilterPipeline,
    OwnerFilter,
    PathDepthFilter,
    PathPriorityFilter,
    SelectorEngine,
    TimestampFilter,
)


def create_test_group(
    files_data: list[dict],
    hash_val: str = "abc123",
    size: int = 1024,
) -> DuplicateGroup:
    """Create a DuplicateGroup from file data dicts."""
    files = []
    for i, data in enumerate(files_data):
        meta = FileMetadata(
            path=data.get("path", f"/test/file{i}.txt"),
            size=data.get("size", size),
            mtime=data.get("mtime", 1000000 + i),
            ctime=data.get("ctime", 1000000 + i),
            atime=data.get("atime", 1000000 + i),
            mode=data.get("mode", 0o644),
            uid=data.get("uid", 1000),
            gid=data.get("gid", 1000),
            inode=data.get("inode", 1000 + i),
            hash=hash_val,
            is_ref=data.get("is_ref", False),
            symlink_target=data.get("symlink_target"),
        )
        files.append(DuplicateFile(metadata=meta, is_reference=data.get("is_ref", False)))
    return DuplicateGroup(hash=hash_val, size=size, files=files)


class TestFilterProtocol:
    """Test Filter protocol compliance."""

    def test_filter_decision_creation(self):
        decision = FilterDecision(
            action=FilterAction.KEEP,
            confidence=0.8,
            reason="test reason",
            filter_name="test_filter",
        )
        assert decision.action == FilterAction.KEEP
        assert decision.confidence == 0.8
        assert decision.reason == "test reason"
        assert decision.filter_name == "test_filter"

    def test_filter_action_enum(self):
        assert FilterAction.KEEP.value == "keep"
        assert FilterAction.DELETE.value == "delete"
        assert FilterAction.SKIP.value == "skip"


class TestPathPriorityFilter:
    """Test PathPriorityFilter - prefers reference paths."""

    def test_prefers_reference_path(self):
        """Reference path should be KEEP, non-ref DELETE."""
        group = create_test_group([
            {"path": "/ref/file.txt", "is_ref": True},
            {"path": "/target/file.txt", "is_ref": False},
        ])
        filter = PathPriorityFilter(ref_prefixes=["/ref"])
        decisions = filter.evaluate(group)

        ref_decision = next(d for d, f in zip(decisions, group.files, strict=True) if f.is_reference)
        non_ref_decision = next(d for d, f in zip(decisions, group.files, strict=True) if not f.is_reference)

        assert ref_decision.action == FilterAction.KEEP
        assert non_ref_decision.action == FilterAction.DELETE

    def test_no_ref_prefix_match(self):
        """Non-matching paths should SKIP."""
        group = create_test_group([
            {"path": "/other/file.txt", "is_ref": False},
            {"path": "/another/file.txt", "is_ref": False},
        ])
        filter = PathPriorityFilter(ref_prefixes=["/ref"])
        decisions = filter.evaluate(group)

        for d in decisions:
            assert d.action == FilterAction.SKIP

    def test_multiple_ref_prefixes(self):
        """Should match any ref prefix."""
        group = create_test_group([
            {"path": "/backup/photos/img.jpg", "is_ref": True},
            {"path": "/data/photos/img.jpg", "is_ref": False},
        ])
        filter = PathPriorityFilter(ref_prefixes=["/backup", "/archive"])
        decisions = filter.evaluate(group)

        ref_decision = next(d for d, f in zip(decisions, group.files, strict=True) if f.is_reference)
        assert ref_decision.action == FilterAction.KEEP


class TestFilenameHygieneFilter:
    """Test FilenameHygieneFilter - scores filenames by cleanliness."""

    def test_clean_filename_preferred(self):
        """Clean filename (no spaces, special chars) should win."""
        group = create_test_group([
            {"path": "/dir/clean_file.txt"},
            {"path": "/dir/messy file (1).txt"},
        ])
        filter = FilenameHygieneFilter()
        decisions = filter.evaluate(group)

        clean_decision = decisions[0]
        messy_decision = decisions[1]

        assert clean_decision.action == FilterAction.KEEP
        assert messy_decision.action == FilterAction.DELETE

    def test_no_spaces_preferred(self):
        """Files without spaces should be preferred."""
        group = create_test_group([
            {"path": "/dir/file_name.txt"},
            {"path": "/dir/file name.txt"},
        ])
        filter = FilenameHygieneFilter()
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.DELETE

    def test_no_umlauts_preferred(self):
        """ASCII filenames preferred over umlauts."""
        group = create_test_group([
            {"path": "/dir/file.txt"},
            {"path": "/dir/datei_mit_ä.txt"},
        ])
        filter = FilenameHygieneFilter()
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.DELETE


class TestArtifactFilter:
    """Test ArtifactFilter - detects copy artifacts."""

    def test_detects_copy_suffix(self):
        """Should detect _copy suffix."""
        group = create_test_group([
            {"path": "/dir/file.txt"},
            {"path": "/dir/file_copy.txt"},
        ])
        filter = ArtifactFilter()
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.DELETE

    def test_detects_numbered_parens(self):
        """Should detect (1), (2) patterns."""
        group = create_test_group([
            {"path": "/dir/image.jpg"},
            {"path": "/dir/image (1).jpg"},
        ])
        filter = ArtifactFilter()
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.DELETE

    def test_detects_v_suffix(self):
        """Should detect _v2, _v3 patterns."""
        group = create_test_group([
            {"path": "/dir/document.pdf"},
            {"path": "/dir/document_v2.pdf"},
        ])
        filter = ArtifactFilter()
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.DELETE

    def test_detects_tilde(self):
        """Should detect ~ suffix (editor backups)."""
        group = create_test_group([
            {"path": "/dir/script.py"},
            {"path": "/dir/script.py~"},
        ])
        filter = ArtifactFilter()
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.DELETE

    def test_no_artifact_clean_files(self):
        """Clean files without artifacts should SKIP."""
        group = create_test_group([
            {"path": "/dir/file1.txt"},
            {"path": "/dir/file2.txt"},
        ])
        filter = ArtifactFilter()
        decisions = filter.evaluate(group)

        for d in decisions:
            assert d.action == FilterAction.SKIP


class TestPathDepthFilter:
    """Test PathDepthFilter - prefers shallower paths."""

    def test_shallower_path_wins(self):
        """Less deep path should be KEEP."""
        group = create_test_group([
            {"path": "/a/b/c/deep.txt"},
            {"path": "/a/shallow.txt"},
        ])
        filter = PathDepthFilter(prefer_shallower=True)
        decisions = filter.evaluate(group)

        assert decisions[1].action == FilterAction.KEEP  # shallower
        assert decisions[0].action == FilterAction.DELETE  # deeper

    def test_deeper_path_wins_when_reversed(self):
        """Deeper path wins when prefer_shallower=False."""
        group = create_test_group([
            {"path": "/a/b/c/deep.txt"},
            {"path": "/a/shallow.txt"},
        ])
        filter = PathDepthFilter(prefer_shallower=False)
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP  # deeper
        assert decisions[1].action == FilterAction.DELETE  # shallower


class TestTimestampFilter:
    """Test TimestampFilter - prefers newest or oldest."""

    def test_prefers_newest_by_default(self):
        """Newest mtime should win by default."""
        group = create_test_group([
            {"path": "/dir/old.txt", "mtime": 1000},
            {"path": "/dir/new.txt", "mtime": 2000},
        ])
        filter = TimestampFilter(prefer_newest=True)
        decisions = filter.evaluate(group)

        assert decisions[1].action == FilterAction.KEEP  # newer
        assert decisions[0].action == FilterAction.SKIP  # older

    def test_prefers_oldest_when_configured(self):
        """Oldest mtime should win when prefer_newest=False."""
        group = create_test_group([
            {"path": "/dir/old.txt", "mtime": 1000},
            {"path": "/dir/new.txt", "mtime": 2000},
        ])
        filter = TimestampFilter(prefer_newest=False)
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP  # older
        assert decisions[1].action == FilterAction.SKIP  # newer


class TestOwnerFilter:
    """Test OwnerFilter - prefers specific UID/GID."""

    def test_prefers_matching_uid(self):
        """File with matching UID should be KEEP."""
        group = create_test_group([
            {"path": "/dir/file1.txt", "uid": 1000},
            {"path": "/dir/file2.txt", "uid": 1001},
        ])
        filter = OwnerFilter(preferred_uids=[1000])
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.SKIP

    def test_prefers_matching_gid(self):
        """File with matching GID should be KEEP."""
        group = create_test_group([
            {"path": "/dir/file1.txt", "gid": 100},
            {"path": "/dir/file2.txt", "gid": 101},
        ])
        filter = OwnerFilter(preferred_gids=[100])
        decisions = filter.evaluate(group)

        assert decisions[0].action == FilterAction.KEEP
        assert decisions[1].action == FilterAction.SKIP


class TestFilterPipeline:
    """Test FilterPipeline cascading logic."""

    def test_first_decisive_filter_wins(self):
        """First filter that decides KEEP/DELETE wins."""
        group = create_test_group([
            {"path": "/ref/file.txt", "is_ref": True, "mtime": 1000},
            {"path": "/target/file.txt", "is_ref": False, "mtime": 2000},
        ])
        # PathPriority runs first, should decide
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/ref"]),
            TimestampFilter(prefer_newest=True),  # would prefer /target
        ])
        actions = pipeline.evaluate(group)

        assert actions["/ref/file.txt"] == FilterAction.KEEP
        assert actions["/target/file.txt"] == FilterAction.DELETE

    def test_cascade_to_second_filter(self):
        """Should cascade to second filter when first is undecided."""
        group = create_test_group([
            {"path": "/a/file1.txt", "mtime": 1000},
            {"path": "/a/file2.txt", "mtime": 2000},
        ])
        # First filter: no ref prefix match → SKIP
        # Second filter: timestamp decides
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/nonexistent"]),
            TimestampFilter(prefer_newest=True),
        ])
        actions = pipeline.evaluate(group)

        assert actions["/a/file2.txt"] == FilterAction.KEEP
        assert actions["/a/file1.txt"] == FilterAction.SKIP

    def test_all_skip_remains_skip(self):
        """Files undecided by all filters remain SKIP."""
        group = create_test_group([
            {"path": "/a/file1.txt"},
            {"path": "/a/file2.txt"},
        ])
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/nonexistent"]),
            ArtifactFilter(),  # no artifacts
        ])
        actions = pipeline.evaluate(group)

        assert actions["/a/file1.txt"] == FilterAction.SKIP
        assert actions["/a/file2.txt"] == FilterAction.SKIP

    def test_pipeline_serialization(self):
        """Pipeline should serialize to JSON and deserialize."""
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/ref"]),
            ArtifactFilter(),
            TimestampFilter(prefer_newest=False),
        ])
        json_str = pipeline.serialize()
        restored = FilterPipeline.deserialize(json_str)

        assert len(restored.filters) == 3
        assert isinstance(restored.filters[0], PathPriorityFilter)
        assert isinstance(restored.filters[1], ArtifactFilter)
        assert isinstance(restored.filters[2], TimestampFilter)
        assert restored.filters[0].ref_prefixes == ["/ref"]
        assert restored.filters[2].prefer_newest is False

    def test_pipeline_save_load_preset(self, tmp_path):
        """Pipeline should save and load preset files."""
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/ref"]),
            ArtifactFilter(),
        ])
        preset_path = tmp_path / "test_preset.json"
        pipeline.save_preset(preset_path)

        loaded = FilterPipeline.load_preset(preset_path)
        assert len(loaded.filters) == 2
        assert isinstance(loaded.filters[0], PathPriorityFilter)
        assert isinstance(loaded.filters[1], ArtifactFilter)

    def test_pipeline_filter_management(self):
        """Add, remove, move filters."""
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/a"]),
            ArtifactFilter(),
            TimestampFilter(),
        ])
        assert len(pipeline.filters) == 3

        pipeline.remove_filter(1)  # Remove ArtifactFilter
        assert len(pipeline.filters) == 2
        assert isinstance(pipeline.filters[1], TimestampFilter)

        pipeline.add_filter(ArtifactFilter())
        assert len(pipeline.filters) == 3

        pipeline.move_filter(2, 0)  # Move ArtifactFilter to front
        assert isinstance(pipeline.filters[0], ArtifactFilter)


class TestFilterRegistry:
    """Test filter registry for dynamic loading."""

    def test_all_filters_registered(self):
        expected = {
            "path_priority",
            "filename_hygiene",
            "artifact",
            "path_depth",
            "timestamp",
            "owner",
        }
        assert set(FILTER_REGISTRY.keys()) == expected

    def test_from_params_creates_correct_filter(self):
        for name, cls in FILTER_REGISTRY.items():
            filter = cls.from_params({})
            assert filter.name == name


class TestSelectorEngine:
    """Test high-level SelectorEngine."""

    def test_run_on_multiple_groups(self):
        """Should process all groups and return actions per hash."""
        groups = [
            create_test_group([
                {"path": "/ref/a.txt", "is_ref": True},
                {"path": "/target/a.txt", "is_ref": False},
            ], hash_val="hash1"),
            create_test_group([
                {"path": "/ref/b.txt", "is_ref": True},
                {"path": "/target/b.txt", "is_ref": False},
            ], hash_val="hash2"),
        ]
        pipeline = FilterPipeline([PathPriorityFilter(ref_prefixes=["/ref"])])
        engine = SelectorEngine(pipeline)
        results = engine.run(groups)

        assert "hash1" in results
        assert "hash2" in results
        assert results["hash1"]["/ref/a.txt"] == FilterAction.KEEP
        assert results["hash1"]["/target/a.txt"] == FilterAction.DELETE

    def test_get_summary(self):
        """Should return summary counts."""
        groups = [
            create_test_group([
                {"path": "/ref/a.txt", "is_ref": True},
                {"path": "/target/a.txt", "is_ref": False},
            ], hash_val="hash1"),
        ]
        pipeline = FilterPipeline([PathPriorityFilter(ref_prefixes=["/ref"])])
        engine = SelectorEngine(pipeline)
        results = engine.run(groups)
        summary = engine.get_summary(groups, results)

        assert summary["keep"] == 1
        assert summary["delete"] == 1
        assert summary["skip"] == 0


class TestPropertyBasedDeterminism:
    """Property-based tests for filter determinism."""

    @pytest.mark.parametrize("filter_class", [
        PathPriorityFilter,
        FilenameHygieneFilter,
        ArtifactFilter,
        PathDepthFilter,
        TimestampFilter,
        OwnerFilter,
    ])
    def test_filter_deterministic(self, filter_class):
        """Same input should always produce same output."""
        group = create_test_group([
            {"path": "/a/file1.txt", "mtime": 1000, "uid": 1000},
            {"path": "/a/file2.txt", "mtime": 2000, "uid": 1001},
        ])
        filter = filter_class.from_params({}) if hasattr(filter_class, 'from_params') else filter_class()
        result1 = filter.evaluate(group)
        result2 = filter.evaluate(group)
        assert result1 == result2

    def test_pipeline_deterministic(self):
        """Pipeline should be deterministic."""
        group = create_test_group([
            {"path": "/ref/a.txt", "is_ref": True, "mtime": 1000},
            {"path": "/target/a.txt", "is_ref": False, "mtime": 2000},
        ])
        pipeline = FilterPipeline([
            PathPriorityFilter(ref_prefixes=["/ref"]),
            TimestampFilter(prefer_newest=True),
        ])
        result1 = pipeline.evaluate(group)
        result2 = pipeline.evaluate(group)
        assert result1 == result2
