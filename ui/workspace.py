#!/usr/bin/env python3
"""
DataWarden - UI Workspace & Layout Manager (STUB)
Dynamic split panes, persistence, theming.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from textual.app import App
from textual.widget import Widget


class SplitDirection(Enum):
    HORIZONTAL = "horizontal"   # Side by side
    VERTICAL = "vertical"       # Top/bottom


@dataclass
class PaneConfig:
    """Configuration for a single pane."""
    widget_type: str            # e.g., "commander_tree", "duplicate_table", "log_panel"
    widget_config: dict = field(default_factory=dict)
    title: str = ""
    size_ratio: float = 1.0     # Relative size in parent split
    minimized: bool = False


@dataclass
class SplitNode:
    """Node in the binary split tree."""
    direction: SplitDirection
    children: list[SplitNode | LeafNode] = field(default_factory=list)
    sizes: list[float] = field(default_factory=list)  # Size ratios for children

    def to_dict(self) -> dict:
        return {
            "type": "split",
            "direction": self.direction.value,
            "children": [c.to_dict() for c in self.children],
            "sizes": self.sizes
        }

    @classmethod
    def from_dict(cls, data: dict) -> SplitNode:
        children = []
        for c in data["children"]:
            if c["type"] == "split":
                children.append(SplitNode.from_dict(c))
            else:
                children.append(LeafNode.from_dict(c))
        return cls(
            direction=SplitDirection(data["direction"]),
            children=children,
            sizes=data.get("sizes", [])
        )


@dataclass
class LeafNode:
    """Leaf node containing a pane."""
    pane: PaneConfig

    def to_dict(self) -> dict:
        return {
            "type": "leaf",
            "pane": asdict(self.pane)
        }

    @classmethod
    def from_dict(cls, data: dict) -> LeafNode:
        return cls(pane=PaneConfig(**data["pane"]))


class LayoutManager:
    """
    Manages dynamic split layout tree.
    Supports: horizontal/vertical splits, resize, persist/restore.
    """

    def __init__(self, app: App):
        self.app = app
        self.root: SplitNode | LeafNode | None = None
        self.layout_file = Path("config/layout.json")
        self._pane_widgets: dict[str, Widget] = {}
        self._pane_nodes: dict[str, LeafNode] = {}  # Track pane_id -> LeafNode mapping

    def create_default_layout(self) -> SplitNode:
        """Create the default 2-pane Commander layout."""
        left_pane = LeafNode(PaneConfig(
            widget_type="commander_tree",
            title="Links",
            widget_config={"side": "left"}
        ))
        right_pane = LeafNode(PaneConfig(
            widget_type="commander_tree",
            title="Rechts",
            widget_config={"side": "right"}
        ))

        root = SplitNode(
            direction=SplitDirection.HORIZONTAL,
            children=[left_pane, right_pane],
            sizes=[0.5, 0.5]
        )
        self.root = root
        return root

    def split_pane(self,
                   target_leaf: LeafNode,
                   direction: SplitDirection,
                   new_pane: PaneConfig) -> SplitNode:
        """Split an existing leaf into two."""
        new_leaf = LeafNode(new_pane)

        if direction == SplitDirection.HORIZONTAL:
            new_split = SplitNode(
                direction=SplitDirection.HORIZONTAL,
                children=[target_leaf, new_leaf],
                sizes=[0.5, 0.5]
            )
        else:
            new_split = SplitNode(
                direction=SplitDirection.VERTICAL,
                children=[target_leaf, new_leaf],
                sizes=[0.5, 0.5]
            )

        # Replace target_leaf with new_split in tree
        self._replace_leaf(self.root, target_leaf, new_split)
        return new_split

    def _replace_leaf(self, node: SplitNode | LeafNode,
                      old_leaf: LeafNode,
                      new_node: SplitNode | LeafNode) -> bool:
        """Recursively replace a leaf in the tree."""
        if isinstance(node, LeafNode):
            return False

        for i, child in enumerate(node.children):
            if child is old_leaf:
                node.children[i] = new_node
                return True
            elif isinstance(child, SplitNode):
                if self._replace_leaf(child, old_leaf, new_node):
                    return True
        return False

    def close_pane(self, target_leaf: LeafNode) -> bool:
        """Close a pane, merging with sibling if possible."""
        parent = self._find_parent(self.root, target_leaf)
        if not parent or len(parent.children) != 2:
            return False  # Can't close last pane

        # Find sibling
        sibling = parent.children[0] if parent.children[1] is target_leaf else parent.children[1]

        # Replace parent with sibling in grandparent
        grandparent = self._find_parent(self.root, parent)
        if grandparent:
            self._replace_leaf(grandparent, parent, sibling)
        else:
            # Parent was root
            self.root = sibling

        return True

    def _find_parent(self, node: SplitNode | LeafNode,
                     target: SplitNode | LeafNode) -> SplitNode | None:
        """Find parent of target node."""
        if isinstance(node, LeafNode):
            return None

        for child in node.children:
            if child is target:
                return node
            if isinstance(child, SplitNode):
                result = self._find_parent(child, target)
                if result:
                    return result
        return None

    def resize_split(self, split: SplitNode, delta: float, child_index: int) -> None:
        """Adjust size ratios of a split's children."""
        if child_index >= len(split.sizes):
            return

        # Adjust size
        new_size = split.sizes[child_index] + delta
        new_size = max(0.1, min(0.9, new_size))  # Clamp 10%-90%

        # Redistribute remaining
        remaining = 1.0 - new_size
        other_indices = [i for i in range(len(split.sizes)) if i != child_index]

        if other_indices:
            # Distribute proportionally to current sizes
            total_other = sum(split.sizes[i] for i in other_indices)
            if total_other > 0:
                for i in other_indices:
                    split.sizes[i] = (split.sizes[i] / total_other) * remaining
            else:
                # Equal distribution
                for i in other_indices:
                    split.sizes[i] = remaining / len(other_indices)

        split.sizes[child_index] = new_size

    def find_pane_at_position(self, x: int, y: int) -> LeafNode | None:
        """Find leaf node at screen coordinates (for drag-drop)."""
        # Would need widget geometry - simplified
        return None

    def get_all_leaves(self) -> list[LeafNode]:
        """Get all leaf nodes in the layout."""
        leaves = []
        self._collect_leaves(self.root, leaves)
        return leaves

    def _collect_leaves(self, node: SplitNode | LeafNode, leaves: list[LeafNode]) -> None:
        if isinstance(node, LeafNode):
            leaves.append(node)
        else:
            for child in node.children:
                self._collect_leaves(child, leaves)

    def save_layout(self) -> None:
        """Persist layout to disk."""
        if self.root:
            self.layout_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "timestamp": time.time(),
                "layout": self.root.to_dict()
            }
            self.layout_file.write_text(json.dumps(data, indent=2))

    def load_layout(self) -> bool:
        """Load layout from disk."""
        if not self.layout_file.exists():
            return False

        try:
            data = json.loads(self.layout_file.read_text())
            self.root = self._deserialize_node(data["layout"])
            return True
        except Exception:
            return False

    def _deserialize_node(self, data: dict) -> SplitNode | LeafNode:
        if data["type"] == "split":
            return SplitNode.from_dict(data)
        else:
            return LeafNode.from_dict(data)

    def resize_pane(self, direction: str, delta: int) -> None:
        """Resize a pane in the given direction.

        direction: "left", "right", "up", "down"
        delta: size change in percent (positive = grow)
        """
        if not self.root:
            return

        leaves = self.get_all_leaves()
        if not leaves:
            return

        # Find the split containing the pane to resize
        # For left/right: find horizontal split and adjust left/right child
        # For up/down: find vertical split and adjust top/bottom child

        split_node, child_index = self._find_split_for_direction(self.root, direction)
        if split_node and isinstance(split_node, SplitNode):
            delta_ratio = delta / 100.0
            self.resize_split(split_node, delta_ratio, child_index)

    def _find_split_for_direction(self, node: SplitNode | LeafNode, direction: str) -> tuple[SplitNode | None, int]:
        """Find the split node and child index for a resize direction."""
        if isinstance(node, LeafNode):
            return None, -1

        # Check if this split matches the direction
        if direction in ("left", "right") and node.direction == SplitDirection.HORIZONTAL:
            if direction == "left":
                return node, 0
            else:
                return node, 1 if len(node.children) > 1 else 0

        if direction in ("up", "down") and node.direction == SplitDirection.VERTICAL:
            if direction == "up":
                return node, 0
            else:
                return node, 1 if len(node.children) > 1 else 0

        # Recurse into children
        for child in node.children:
            if isinstance(child, SplitNode):
                result = self._find_split_for_direction(child, direction)
                if result[0]:
                    return result

        return None, -1

    def get_tree_representation(self) -> list[str]:
        """Get text representation of layout tree for debugging."""
        lines = []
        self._build_tree_repr(self.root, lines, 0)
        return lines

    def _build_tree_repr(self, node: SplitNode | LeafNode, lines: list[str], depth: int) -> None:
        indent = "  " * depth
        if isinstance(node, LeafNode):
            lines.append(f"{indent}└─ [{node.pane.widget_type}] {node.pane.title}")
        else:
            lines.append(f"{indent}├─ {node.direction.value} {node.sizes}")
            for child in node.children:
                self._build_tree_repr(child, lines, depth + 1)


class ThemeManager:
    """Manages TCSS themes with live reload."""

    BUILTIN_THEMES = {
        "dark": {
            "background": "#1e1e2e",
            "surface": "#282a36",
            "primary": "#bd93f9",
            "secondary": "#6272a4",
            "accent": "#50fa7b",
            "warning": "#ffb86c",
            "error": "#ff5555",
            "text": "#f8f8f2",
            "text_muted": "#6272a4",
            "border": "#44475a",
            "reference_green": "#50fa7b",
            "warning_yellow": "#ffb86c",
            "error_red": "#ff5555"
        },
        "light": {
            "background": "#ffffff",
            "surface": "#f8f9fa",
            "primary": "#6f42c1",
            "secondary": "#6c757d",
            "accent": "#28a745",
            "warning": "#ffc107",
            "error": "#dc3545",
            "text": "#212529",
            "text_muted": "#6c757d",
            "border": "#dee2e6",
            "reference_green": "#28a745",
            "warning_yellow": "#ffc107",
            "error_red": "#dc3545"
        },
        "nord": {
            "background": "#2e3440",
            "surface": "#3b4252",
            "primary": "#88c0d0",
            "secondary": "#4c566a",
            "accent": "#a3be8c",
            "warning": "#ebcb8b",
            "error": "#bf616a",
            "text": "#eceff4",
            "text_muted": "#4c566a",
            "border": "#434c5e",
            "reference_green": "#a3be8c",
            "warning_yellow": "#ebcb8b",
            "error_red": "#bf616a"
        },
        "dracula": {
            "background": "#282a36",
            "surface": "#44475a",
            "primary": "#bd93f9",
            "secondary": "#6272a4",
            "accent": "#50fa7b",
            "warning": "#ffb86c",
            "error": "#ff5555",
            "text": "#f8f8f2",
            "text_muted": "#6272a4",
            "border": "#6272a4",
            "reference_green": "#50fa7b",
            "warning_yellow": "#ffb86c",
            "error_red": "#ff5555"
        }
    }

    def __init__(self, app: App):
        self.app = app
        self.current_theme = "dark"
        self.custom_themes: dict[str, dict] = {}
        self.custom_file = Path("config/theme.json")
        self.load_custom()

    def load_custom(self) -> None:
        if self.custom_file.exists():
            try:
                self.custom_themes = json.loads(self.custom_file.read_text())
            except Exception:
                self.custom_themes = {}

    def save_custom(self) -> None:
        self.custom_file.parent.mkdir(parents=True, exist_ok=True)
        self.custom_file.write_text(json.dumps(self.custom_themes, indent=2))

    def get_theme(self, name: str) -> dict:
        if name in self.BUILTIN_THEMES:
            return self.BUILTIN_THEMES[name]
        if name in self.custom_themes:
            return self.custom_themes[name]
        return self.BUILTIN_THEMES["dark"]

    def apply_theme(self, name: str) -> None:
        """Apply theme by generating full TCSS stylesheet."""
        self.current_theme = name
        theme = self.get_theme(name)

        # Build full TCSS stylesheet with actual property values
        css = f"""
Screen {{
    background: {theme["background"]};
    color: {theme["text"]};
}}

#main-container {{
    background: {theme["background"]};
}}

#sidebar {{
    background: {theme["surface"]};
    border-right: solid {theme["border"]};
}}

#content-area {{
    background: {theme["background"]};
}}

.screen {{
    background: {theme["background"]};
}}

#app-title {{
    color: {theme["primary"]};
}}

#app-subtitle {{
    color: {theme["text_muted"]};
}}

.nav-button {{
    background: transparent;
    border: solid {theme["border"]};
    color: {theme["text"]};
}}

.nav-button:hover {{
    background: {theme["primary"]};
    color: {theme["background"]};
}}

.nav-button.active {{
    background: {theme["primary"]};
    color: {theme["background"]};
    border: solid {theme["reference_green"]};
}}

.screen-title {{
    color: {theme["primary"]};
}}

.screen-description {{
    color: {theme["text_muted"]};
}}

.section-title {{
    color: {theme["accent"]};
}}

Label {{
    color: {theme["text"]};
}}

Input {{
    background: {theme["surface"]};
    border: solid {theme["border"]};
    color: {theme["text"]};
}}

Input:focus {{
    border: solid {theme["primary"]};
}}

Select {{
    background: {theme["surface"]};
    border: solid {theme["border"]};
    color: {theme["text"]};
}}

Select:focus {{
    border: solid {theme["primary"]};
}}

.button-row Button {{
    margin-right: 1;
}}

.progress-area {{
    background: {theme["surface"]};
    border: solid {theme["border"]};
}}

.progress-line {{
    color: {theme["text"]};
}}

.progress-line.warning {{
    color: {theme["warning_yellow"]};
}}

.progress-line.error {{
    color: {theme["error_red"]};
}}

.results-area {{
    margin-top: 2;
}}

#commander-panes {{
    background: {theme["background"]};
}}

.commander-pane {{
    border: solid {theme["border"]};
}}

.hint-bar {{
    color: {theme["text_muted"]};
    background: {theme["surface"]};
    border: solid {theme["border"]};
}}

.panel {{
    border: solid {theme["border"]};
    background: {theme["surface"]};
}}

DataTable {{
    background: {theme["surface"]};
    color: {theme["text"]};
}}

DataTable > .datatable--header {{
    background: {theme["primary"]};
    color: {theme["background"]};
    text-style: bold;
}}

DataTable > .datatable--cursor {{
    background: {theme["accent"]};
    color: {theme["background"]};
}}

DataTable > .datatable--even-row {{
    background: {theme["surface"]};
}}

DataTable > .datatable--odd-row {{
    background: {theme["background"]};
}}

RichLog {{
    background: {theme["surface"]};
    color: {theme["text"]};
    border: solid {theme["border"]};
}}

.modal-container {{
    background: {theme["surface"]};
    border: thick {theme["primary"]};
}}

.modal-title {{
    color: {theme["error_red"]};
    text-style: bold;
}}

.modal-warning {{
    color: {theme["warning_yellow"]};
    text-style: bold;
}}

.modal-text {{
    color: {theme["text"]};
}}

.modal-hotkey {{
    color: {theme["accent"]};
    text-style: bold;
}}

Footer {{
    background: {theme["surface"]};
    color: {theme["text"]};
    border-top: solid {theme["border"]};
}}

Tree {{
    background: {theme["surface"]};
    color: {theme["text"]};
}}

Tree > .tree--cursor {{
    background: {theme["primary"]};
    color: {theme["background"]};
}}

Tree > .tree--guides {{
    color: {theme["border"]};
}}

Collapsible {{
    border: solid {theme["border"]};
    background: {theme["surface"]};
}}

Collapsible > .collapsible--title {{
    background: {theme["primary"]};
    color: {theme["background"]};
    text-style: bold;
}}

TabbedContent {{
    background: {theme["surface"]};
}}

TabbedContent > .tabbed-content--tabs {{
    background: {theme["background"]};
    border-bottom: solid {theme["border"]};
}}

TabbedContent > .tabbed-content--tabs Button {{
    color: {theme["text_muted"]};
}}

TabbedContent > .tabbed-content--tabs Button.-active {{
    color: {theme["primary"]};
    text-style: bold;
    border-bottom: solid {theme["primary"]};
}}

.reference-file {{
    color: {theme["reference_green"]};
    text-style: bold;
}}

.warning-text {{
    color: {theme["warning_yellow"]};
}}

.error-text {{
    color: {theme["error_red"]};
}}

.ai-auto-text {{
    color: {theme["accent"]};
}}

ProgressBar {{
    background: {theme["surface"]};
    color: {theme["accent"]};
}}

ProgressBar > .progress-bar--bar {{
    background: {theme["primary"]};
}}

Sparkline {{
    color: {theme["accent"]};
}}

Scrollbar {{
    background: {theme["background"]};
    color: {theme["primary"]};
}}

.selected {{
    background: {theme["primary"]};
    color: {theme["background"]};
}}

*:focus {{
    border: solid {theme["primary"]};
}}
"""

        # Apply to app
        self.app.stylesheet.add_source(css)
        self.app.refresh_css()

    def create_custom_theme(self, name: str, colors: dict) -> None:
        """Create a custom theme."""
        self.custom_themes[name] = colors
        self.save_custom()

    def get_available_themes(self) -> list[str]:
        return list(self.BUILTIN_THEMES.keys()) + list(self.custom_themes.keys())
