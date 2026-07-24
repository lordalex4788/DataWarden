#!/usr/bin/env python3
"""
DataWarden - Smart Selector Pipeline (STUB)
Cascading filter system for automatic duplicate selection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from core.models import DuplicateGroup


class FilterAction(Enum):
    KEEP = "keep"
    DELETE = "delete"
    SKIP = "skip"


@dataclass
class FilterDecision:
    """Result of a single filter evaluation."""
    action: FilterAction
    confidence: float  # 0.0 - 1.0
    reason: str
    filter_name: str


class Filter(Protocol):
    """Protocol for all filters in the pipeline."""
    name: str

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        """Evaluate all files in a group. Returns decision per file."""
        ...

    def get_params(self) -> dict[str, Any]:
        """Get filter configuration for serialization."""
        ...

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> Filter:
        """Create filter from serialized params."""
        ...


class PathPriorityFilter:
    """Prefers files in reference paths."""

    name = "path_priority"

    def __init__(self, ref_prefixes: list[str] = None):
        self.ref_prefixes = ref_prefixes or []

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        decisions = []
        for f in group.files:
            is_ref_path = any(f.path.startswith(p) for p in self.ref_prefixes)
            if is_ref_path:
                decisions.append(FilterDecision(
                    action=FilterAction.KEEP,
                    confidence=0.9,
                    reason=f"In reference path: {self._matching_prefix(f.path)}",
                    filter_name=self.name
                ))
            else:
                decisions.append(FilterDecision(
                    action=FilterAction.SKIP,
                    confidence=0.0,
                    reason="Not in reference path",
                    filter_name=self.name
                ))
        return decisions

    def _matching_prefix(self, path: str) -> str:
        for p in self.ref_prefixes:
            if path.startswith(p):
                return p
        return ""

    def get_params(self) -> dict:
        return {"ref_prefixes": self.ref_prefixes}

    @classmethod
    def from_params(cls, params: dict) -> PathPriorityFilter:
        return cls(params.get("ref_prefixes", []))


class FilenameHygieneFilter:
    """Scores filenames by cleanliness (no spaces, umlauts, special chars)."""

    name = "filename_hygiene"

    # Scoring weights
    SCORE_CLEAN = 1.0
    SCORE_UNDERSCORE = 0.9
    SCORE_SPACE = 0.5
    SCORE_UMLAUT = 0.4
    SCORE_SPECIAL = 0.3
    SCORE_MULTI_DOT = 0.6
    SCORE_LONG = 0.7

    # Patterns
    UMLAUT_PATTERN = re.compile(r'[äöüÄÖÜß]')
    SPECIAL_PATTERN = re.compile(r'[^\w\s\-\.]')
    MULTI_DOT_PATTERN = re.compile(r'\..*\..*')

    def __init__(self, custom_pattern: str = ""):
        self.custom_pattern = custom_pattern
        self.custom_regex = re.compile(custom_pattern) if custom_pattern else None

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        # Score all files
        scored = []
        for f in group.files:
            score = self._score_filename(Path(f.path).name)
            scored.append((f, score))

        # Find best score
        best_score = max((s for _, s in scored), default=0)

        # Return decisions in original order
        decisions = []
        for f, score in scored:
            if score == best_score and best_score > 0.5:
                action = FilterAction.KEEP
                confidence = min(score, 0.85)
                reason = f"Cleanest filename (score: {score:.2f})"
            else:
                action = FilterAction.DELETE
                confidence = 0.7
                reason = f"Lower hygiene score: {score:.2f}"

            decisions.append(FilterDecision(
                action=action,
                confidence=confidence,
                reason=reason,
                filter_name=self.name
            ))
        return decisions

    def _score_filename(self, name: str) -> float:
        score = self.SCORE_CLEAN

        if ' ' in name:
            score = min(score, self.SCORE_SPACE)

        if self.UMLAUT_PATTERN.search(name):
            score = min(score, self.SCORE_UMLAUT)

        if self.SPECIAL_PATTERN.search(name):
            score = min(score, self.SCORE_SPECIAL)

        if self.MULTI_DOT_PATTERN.search(name):
            score = min(score, self.SCORE_MULTI_DOT)

        if len(name) > 100:
            score = min(score, self.SCORE_LONG)

        # Prefer underscores over spaces
        if '_' in name and ' ' not in name:
            score = max(score, self.SCORE_UNDERSCORE)

        # Custom pattern penalty
        if self.custom_regex and self.custom_regex.search(name):
            score *= 0.5

        return score

    def get_params(self) -> dict:
        return {"custom_pattern": self.custom_pattern}

    @classmethod
    def from_params(cls, params: dict) -> FilenameHygieneFilter:
        return cls(params.get("custom_pattern", ""))


class ArtifactFilter:
    """Detects and marks version artifacts like _copy, (1), -Kopie, _v2."""

    name = "artifact"

    ARTIFACT_PATTERNS = [
        (re.compile(r'\(\d+\)$'), "numbered_suffix"),           # file (1).txt
        (re.compile(r'[-_](copy|kopie|copy|duplicate)\d*$', re.I), "copy_suffix"),  # _copy, -Kopie
        (re.compile(r'[-_]v\d+$', re.I), "version_suffix"),    # _v2, -V3
        (re.compile(r'[-_]backup$', re.I), "backup_suffix"),   # _backup
        (re.compile(r'~\d*$'), "tilde_suffix"),                # ~, ~1
        (re.compile(r'\.bak$', re.I), "bak_extension"),        # .bak
    ]

    def __init__(self, custom_patterns: list[str] = None):
        self.custom_patterns = custom_patterns or []
        self.custom_regexes = [(re.compile(p), "custom") for p in self.custom_patterns]

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        decisions = []
        for f in group.files:
            filename = Path(f.path).name
            is_artifact = False
            match_type = ""

            for pattern, ptype in self.ARTIFACT_PATTERNS:
                if pattern.search(filename):
                    is_artifact = True
                    match_type = ptype
                    break

            if not is_artifact:
                for pattern, ptype in self.custom_regexes:
                    if pattern.search(filename):
                        is_artifact = True
                        match_type = ptype
                        break

            if is_artifact:
                decisions.append(FilterDecision(
                    action=FilterAction.DELETE,
                    confidence=0.95,
                    reason=f"Artifact detected: {match_type}",
                    filter_name=self.name
                ))
            else:
                decisions.append(FilterDecision(
                    action=FilterAction.SKIP,
                    confidence=0.0,
                    reason="No artifact pattern matched",
                    filter_name=self.name
                ))
        return decisions

    def get_params(self) -> dict:
        return {"custom_patterns": self.custom_patterns}

    @classmethod
    def from_params(cls, params: dict) -> ArtifactFilter:
        return cls(params.get("custom_patterns", []))


class PathDepthFilter:
    """Prefers shallower paths (often originals vs deep backups)."""

    name = "path_depth"

    def __init__(self, prefer_shallower: bool = True):
        self.prefer_shallower = prefer_shallower

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        depths = []
        for f in group.files:
            depth = f.path.count('/') + f.path.count('\\')
            depths.append((f, depth))

        depths.sort(key=lambda x: x[1], reverse=not self.prefer_shallower)
        best_depth = depths[0][1] if depths else 0

        decisions = []
        for _f, depth in depths:
            if depth == best_depth:
                decisions.append(FilterDecision(
                    action=FilterAction.KEEP,
                    confidence=0.7,
                    reason=f"Optimal path depth: {depth}",
                    filter_name=self.name
                ))
            else:
                decisions.append(FilterDecision(
                    action=FilterAction.DELETE,
                    confidence=0.6,
                    reason=f"Suboptimal path depth: {depth} vs {best_depth}",
                    filter_name=self.name
                ))
        return decisions

    def get_params(self) -> dict:
        return {"prefer_shallower": self.prefer_shallower}

    @classmethod
    def from_params(cls, params: dict) -> PathDepthFilter:
        return cls(params.get("prefer_shallower", True))


class TimestampFilter:
    """Prefers newest or oldest file by modification time."""

    name = "timestamp"

    def __init__(self, prefer_newest: bool = True):
        self.prefer_newest = prefer_newest

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        times = [(f, f.mtime) for f in group.files]
        times.sort(key=lambda x: x[1], reverse=self.prefer_newest)
        best_time = times[0][1] if times else 0

        decisions = []
        for _f, mtime in times:
            if mtime == best_time:
                decisions.append(FilterDecision(
                    action=FilterAction.KEEP,
                    confidence=0.75,
                    reason=f"{'Newest' if self.prefer_newest else 'Oldest'} mtime: {mtime}",
                    filter_name=self.name
                ))
            else:
                decisions.append(FilterDecision(
                    action=FilterAction.DELETE,
                    confidence=0.6,
                    reason=f"Older mtime: {mtime}",
                    filter_name=self.name
                ))
        return decisions

    def get_params(self) -> dict:
        return {"prefer_newest": self.prefer_newest}

    @classmethod
    def from_params(cls, params: dict) -> TimestampFilter:
        return cls(params.get("prefer_newest", True))


class OwnerFilter:
    """Prefers files owned by specific UID/GID."""

    name = "owner"

    def __init__(self, preferred_uids: list[int] = None, preferred_gids: list[int] = None):
        self.preferred_uids = set(preferred_uids or [])
        self.preferred_gids = set(preferred_gids or [])

    def evaluate(self, group: DuplicateGroup) -> list[FilterDecision]:
        decisions = []
        for f in group.files:
            uid_match = f.uid in self.preferred_uids
            gid_match = f.gid in self.preferred_gids

            if uid_match or gid_match:
                decisions.append(FilterDecision(
                    action=FilterAction.KEEP,
                    confidence=0.8,
                    reason=f"Preferred owner (uid={f.uid}, gid={f.gid})",
                    filter_name=self.name
                ))
            else:
                decisions.append(FilterDecision(
                    action=FilterAction.SKIP,
                    confidence=0.0,
                    reason="Non-preferred owner",
                    filter_name=self.name
                ))
        return decisions

    def get_params(self) -> dict:
        return {
            "preferred_uids": list(self.preferred_uids),
            "preferred_gids": list(self.preferred_gids),
        }

    @classmethod
    def from_params(cls, params: dict) -> OwnerFilter:
        return cls(
            params.get("preferred_uids", []),
            params.get("preferred_gids", [])
        )


class FilterPipeline:
    """Cascading filter pipeline - first decisive filter wins."""

    def __init__(self, filters: list[Filter] = None):
        self.filters = filters or []

    def add_filter(self, filter: Filter) -> None:
        self.filters.append(filter)

    def remove_filter(self, index: int) -> None:
        if 0 <= index < len(self.filters):
            self.filters.pop(index)

    def move_filter(self, from_idx: int, to_idx: int) -> None:
        if 0 <= from_idx < len(self.filters) and 0 <= to_idx < len(self.filters):
            f = self.filters.pop(from_idx)
            self.filters.insert(to_idx, f)

    def evaluate(self, group: DuplicateGroup) -> dict[str, FilterAction]:
        """
        Run all filters in order. Return final action per file.
        First filter with KEEP/DELETE wins for that file.
        """
        # Track undecided files
        undecided = {f.path: f for f in group.files}
        final_actions = {}

        for filter in self.filters:
            decisions = filter.evaluate(group)
            for i, decision in enumerate(decisions):
                f = group.files[i]
                if f.path in undecided:
                    if decision.action in (FilterAction.KEEP, FilterAction.DELETE):
                        final_actions[f.path] = decision.action
                        del undecided[f.path]

        # Remaining undecided = SKIP
        for path in undecided:
            final_actions[path] = FilterAction.SKIP

        return final_actions

    def serialize(self) -> str:
        """Serialize pipeline to JSON."""
        data = []
        for f in self.filters:
            data.append({
                "type": f.name,
                "params": f.get_params()
            })
        return json.dumps(data, indent=2)

    @classmethod
    def deserialize(cls, json_str: str) -> FilterPipeline:
        """Create pipeline from JSON."""
        pipeline = cls()
        data = json.loads(json_str)
        for item in data:
            filter_type = item["type"]
            params = item.get("params", {})
            f = FILTER_REGISTRY[filter_type].from_params(params)
            pipeline.add_filter(f)
        return pipeline

    def save_preset(self, path: Path) -> None:
        path.write_text(self.serialize())

    @classmethod
    def load_preset(cls, path: Path) -> FilterPipeline:
        return cls.deserialize(path.read_text())


# Registry for dynamic filter loading
FILTER_REGISTRY = {
    "path_priority": PathPriorityFilter,
    "filename_hygiene": FilenameHygieneFilter,
    "artifact": ArtifactFilter,
    "path_depth": PathDepthFilter,
    "timestamp": TimestampFilter,
    "owner": OwnerFilter,
}


class SelectorEngine:
    """High-level selector applying pipeline to all groups."""

    def __init__(self, pipeline: FilterPipeline):
        self.pipeline = pipeline

    def run(self, groups: list[DuplicateGroup]) -> dict[str, dict]:
        """Run selection on all groups. Returns {hash: {file_path: action}}."""
        results = {}
        for group in groups:
            actions = self.pipeline.evaluate(group)
            results[group.hash] = actions
        return results

    def get_summary(self, groups: list[DuplicateGroup], results: dict) -> dict:
        keep = sum(1 for g in groups for p, a in results[g.hash].items() if a == FilterAction.KEEP)
        delete = sum(1 for g in groups for p, a in results[g.hash].items() if a == FilterAction.DELETE)
        skip = sum(1 for g in groups for p, a in results[g.hash].items() if a == FilterAction.SKIP)
        return {"keep": keep, "delete": delete, "skip": skip}
