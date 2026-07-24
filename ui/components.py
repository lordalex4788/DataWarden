#!/usr/bin/env python3
"""
DataWarden - UI Components (STUB)
Custom Textual widgets for Commander, Logs, Tables, Panels, etc.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Static, Label, Button, Input, Select, Tree, DataTable, 
    Log, RichLog, Tabs, TabPane, Collapsible, Checkbox, 
    ProgressBar, Sparkline, DirectoryTree
)
from textual.reactive import reactive
from textual.message import Message
from textual.binding import Binding
from textual.events import Key, Click, MouseEvent
from textual.css.query import NoMatches
from rich.text import Text
from rich.tree import Tree as RichTree
from rich.syntax import Syntax

from core.models import DuplicateGroup, DuplicateFile, FileMetadata


# --- Base Components ---

class DescriptionPane(Static):
    """Contextual help/description pane - shows info on hover/focus."""
    
    DEFAULT_CSS = """
    DescriptionPane {
        border: solid $primary;
        padding: 1;
        height: auto;
        min-height: 10;
        background: $surface;
    }
    """
    
    def __init__(self, i18n_manager, **kwargs):
        super().__init__(**kwargs)
        self.i18n = i18n_manager
        self.current_key = ""
    
    def show_description(self, key: str, **kwargs) -> None:
        """Show description for a localization key."""
        self.current_key = key
        desc = self.i18n.get_descriptor(key)
        text = self.i18n.t(key, **kwargs)
        self.update(f"[bold]{text}[/bold]\n\n[dim]{desc}[/dim]" if desc else text)
    
    def show_default(self) -> None:
        """Show default help text."""
        self.update(self.i18n.t("desc_default"))


class LogPanel(RichLog):
    """Tree-based log panel with expand/collapse support."""
    
    DEFAULT_CSS = """
    LogPanel {
        border: solid $primary;
        background: $surface;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.auto_scroll = True
        self.wrap = True
        self.max_lines = 10000
        self._tree_nodes: Dict[str, RichTree] = {}
    
    def write_ai_auto(self, count: int, filter_type: str, rule_date: str, details: List = None) -> None:
        """Write AI auto-execute entry with expand/collapse."""
        from rich.tree import Tree
        
        collapsed_label = f"[+] [cyan][KI-AUTO-EXECUTE][/cyan] {count} Operationen via User-Whitelist angewendet"
        expanded_label = f"[-] [cyan][KI-AUTO-EXECUTE][/cyan] {count} Operationen via User-Whitelist angewendet"
        
        tree = Tree(collapsed_label)
        tree.expanded = False
        
        if details:
            for detail in details:
                tree.add(f"[{detail['time']}] {detail['filter']} auf {detail['path']} (Grund: User-Regel vom {detail['date']})")
        
        self._tree_nodes[f"ai_auto_{time.time()}"] = tree
        self.write(tree)
    
    def write_structured(self, level: str, message: str, data: Dict = None) -> None:
        """Write structured log entry."""
        prefix = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERROR]", "success": "[OK]"}.get(level, "")
        self.write(f"{prefix} {message}")
        if data:
            self.write(f"  Data: {data}")


class CommanderTree(DirectoryTree):
    """MC-style directory tree with keyboard navigation and indicators."""
    
    BINDINGS = [
        Binding("enter", "select_cursor", "Open/Enter"),
        Binding("space", "toggle_select", "Select"),
        Binding("insert", "toggle_select", "Select"),
        Binding("f3", "view_file", "View"),
        Binding("f4", "edit_file", "Edit"),
        Binding("f5", "copy_file", "Copy"),
        Binding("f6", "move_file", "Move"),
        Binding("f7", "mkdir", "Mkdir"),
        Binding("f8", "delete_file", "Delete"),
        Binding("ctrl+c", "copy_path", "Copy Path"),
        Binding("ctrl+v", "paste", "Paste"),
    ]
    
    def __init__(self, path: str, note_manager=None, **kwargs):
        super().__init__(path, **kwargs)
        self.note_manager = note_manager
        self.show_hidden = False
        self.selected_paths: set = set()
        self.reference_mode = False
    
    def action_select_cursor(self) -> None:
        """Enter directory or open file."""
        node = self.cursor_node
        if node and node.data and hasattr(node.data, 'path'):
            path = Path(node.data.path)
            if path.is_dir():
                self.toggle_node(node)
            else:
                self.post_message(self.FileSelected(path))
    
    def action_toggle_select(self) -> None:
        """Toggle file selection."""
        node = self.cursor_node
        if node and node.data and hasattr(node.data, 'path'):
            path = str(node.data.path)
            if path in self.selected_paths:
                self.selected_paths.remove(path)
            else:
                self.selected_paths.add(path)
            self.refresh_node(node)
    
    def action_edit_file(self) -> None:
        """Open file in external editor ($EDITOR)."""
        node = self.cursor_node
        if node and node.data and hasattr(node.data, 'path'):
            path = str(node.data.path)
            editor = os.environ.get('EDITOR', 'nano')
            try:
                subprocess.run([editor, path], check=False)
            except FileNotFoundError:
                self.app.notify(f"Editor '{editor}' nicht gefunden", severity="error")
    
    def action_copy_file(self) -> None:
        """Copy selected files."""
        self.post_message(self.CopyRequested(list(self.selected_paths)))
    
    def action_move_file(self) -> None:
        """Move selected files."""
        self.post_message(self.MoveRequested(list(self.selected_paths)))
    
    def action_delete_file(self) -> None:
        """Delete selected files."""
        self.post_message(self.DeleteRequested(list(self.selected_paths)))
    
    def refresh_node(self, node) -> None:
        """Refresh a single node's display."""
        self.refresh()
    
    def get_node_indicator(self, path: str) -> str:
        """Get indicator for path (notes, reference, etc.)."""
        indicators = []
        
        if self.note_manager:
            notes = self.note_manager.get_notes_for_path(path)
            if notes:
                indicators.append(f"[📝 {len(notes)}]")
        
        if self.reference_mode and path in self.reference_paths:
            indicators.append("[REF]")
        
        return " ".join(indicators) if indicators else ""
    
    class FileSelected(Message):
        def __init__(self, path: Path):
            self.path = path
            super().__init__()
    
    class CopyRequested(Message):
        def __init__(self, paths: List[str]):
            self.paths = paths
            super().__init__()
    
    class MoveRequested(Message):
        def __init__(self, paths: List[str]):
            self.paths = paths
            super().__init__()
    
    class DeleteRequested(Message):
        def __init__(self, paths: List[str]):
            self.paths = paths
            super().__init__()


class DuplicateTable(DataTable):
    """Table for displaying duplicate groups with selection."""
    
    DEFAULT_CSS = """
    DuplicateTable {
        border: solid $primary;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.show_header = True
        
        # Columns
        self.add_columns(
            "Keep", "Delete", "Hash", "Size", "File A (Ref)", "File B", "Action"
        )
    
    def populate(self, groups: List[DuplicateGroup]) -> None:
        """Populate table with duplicate groups."""
        self.clear()
        
        for group in groups:
            for i, file in enumerate(group.files):
                is_ref = "✓" if file.is_ref else ""
                keep = "☐" if not file.is_ref else "🔒"
                delete = "☐" if not file.is_ref else ""
                
                self.add_row(
                    keep, delete, 
                    group.hash[:16] + "...",
                    self._format_size(group.size),
                    file.path if i == 0 else "",
                    file.path if i > 0 else "",
                    "Auto" if file.decision != "pending" else "Manual"
                )
    
    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


class SettingsPane(Static):
    """Settings panel organized by sections."""
    
    DEFAULT_CSS = """
    SettingsPane {
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }
    .setting-section {
        margin: 1 0;
    }
    .setting-label {
        text-style: bold;
        color: $primary;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Label("Einstellungen", classes="setting-section")
        # Settings would be dynamically composed based on config
        # This is a stub - real implementation would build from config schema


class FilterPane(Static):
    """Filter pipeline builder UI."""
    
    DEFAULT_CSS = """
    FilterPane {
        border: solid $primary;
        padding: 1;
    }
    .filter-item {
        margin: 1 0;
        padding: 1;
        border: solid $secondary;
    }
    """
    
    def __init__(self, pipeline, **kwargs):
        super().__init__(**kwargs)
        self.pipeline = pipeline
    
    def compose(self) -> ComposeResult:
        yield Label("Filter-Pipeline (Reihenfolge = Priorität)")
        yield Button("Filter hinzufügen", id="add-filter")
        
        # Filter list would be dynamically built
        with Container(id="filter-list"):
            pass


class ShellPane(Static):
    """Embedded shell with command input and output."""
    
    DEFAULT_CSS = """
    ShellPane {
        border: solid $primary;
        layout: vertical;
    }
    #shell-input {
        dock: bottom;
        height: 3;
    }
    #shell-output {
        height: 1fr;
        overflow-y: auto;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield RichLog(id="shell-output", highlight=True, markup=True)
        yield Input(placeholder="Befehl eingeben (z.B. chmod +x script.sh)...", id="shell-input")
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        if not command:
            return
        
        output = self.query_one("#shell-output", RichLog)
        output.write(f"[bold green]$[/bold green] {command}")
        event.input.value = ""
        
        # Execute command
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            stdout, stderr = await proc.communicate()
            
            if stdout:
                output.write(stdout.decode())
            if stderr:
                output.write(f"[red]{stderr.decode()}[/red]")
            output.write(f"[dim]Exit code: {proc.returncode}[/dim]")
        except Exception as e:
            output.write(f"[red]Fehler: {e}[/red]")


class GrepPanel(Static):
    """Async content search panel."""
    
    DEFAULT_CSS = """
    GrepPanel {
        border: solid $primary;
        layout: vertical;
    }
    #grep-input {
        dock: top;
        height: 3;
    }
    #grep-results {
        height: 1fr;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Suchbegriff oder Regex...", id="grep-input")
        yield DataTable(id="grep-results")
    
    async def on_input_changed(self, event: Input.Changed) -> None:
        if len(event.value) < 3:
            return
        
        # Debounced search would go here
        pass
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        
        results_table = self.query_one("#grep-results", DataTable)
        results_table.clear()
        results_table.add_columns("File", "Line", "Match", "Context")
        
        # Would use ripgrep or async file search here
        self.app.notify(f"Suche nach: {query}")


class HexDebugPanel(Static):
    """Hex editor / debug panel."""
    
    DEFAULT_CSS = """
    HexDebugPanel {
        border: solid $primary;
        layout: vertical;
    }
    #hex-toolbar {
        dock: top;
        height: 3;
    }
    #hex-view {
        height: 1fr;
        font-family: monospace;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="hex-toolbar"):
            yield Input(placeholder="Offset (hex)", id="hex-offset")
            yield Button("Springen", id="hex-goto")
            yield Button("Speichern", id="hex-save", variant="warning")
        yield RichLog(id="hex-view", markup=True)
    
    def load_file(self, path: Path) -> None:
        """Load file into hex view."""
        view = self.query_one("#hex-view", RichLog)
        view.clear()
        
        try:
            with open(path, 'rb') as f:
                data = f.read(8192)  # Limit to 8KB for display
            
            # Hex dump
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_part = ' '.join(f'{b:02x}' for b in chunk)
                ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                offset = f"{i:08x}"
                
                # Highlight magic bytes
                if i == 0:
                    hex_part = f"[bold yellow]{hex_part}[/bold yellow]"
                
                view.write(f"{offset}  {hex_part:<48}  {ascii_part}")
        except Exception as e:
            view.write(f"[red]Fehler: {e}[/red]")


class NotePane(Static):
    """Sticky note display for current path."""
    
    DEFAULT_CSS = """
    NotePane {
        border: solid $warning;
        background: $surface;
        padding: 1;
    }
    .note-item {
        margin: 1 0;
        padding: 1;
        border-left: thick $warning;
    }
    """
    
    def __init__(self, note_manager, **kwargs):
        super().__init__(**kwargs)
        self.note_manager = note_manager
        self.current_path = ""
    
    def set_path(self, path: str) -> None:
        """Update notes for a path."""
        self.current_path = path
        self.refresh_notes()
    
    def refresh_notes(self) -> None:
        """Refresh displayed notes."""
        if not self.current_path:
            self.update("Kein Pfad ausgewählt")
            return
        
        notes = self.note_manager.get_notes_for_path(self.current_path)
        
        if not notes:
            self.update(f"[dim]Keine Notizen für: {self.current_path}[/dim]")
            return
        
        content = []
        for note in notes:
            color = note.color
            content.append(f"[bold {color}]{note.tags}[/bold {color}] {note.content}")
            content.append(f"[dim]Erstellt: {note.created_at:.0f}[/dim]")
        
        self.update("\n\n".join(content))


class WardenDashboard(Static):
    """Real-time FileSystem Warden incident dashboard."""
    
    DEFAULT_CSS = """
    WardenDashboard {
        border: solid $error;
        background: $surface;
        layout: vertical;
    }
    .incident-critical { border-left: thick $error; }
    .incident-warning { border-left: thick $warning; }
    .incident-info { border-left: thick $primary; }
    """
    
    def compose(self) -> ComposeResult:
        yield Label("FileSystem Warden - Live Incidents", classes="section-title")
        yield DataTable(id="incident-table")
        yield Input(placeholder="Natürliche Sprache: 'Wo ist die Tabelle mit Umsatz Q2?'", id="warden-query")
    
    def on_mount(self) -> None:
        table = self.query_one("#incident-table", DataTable)
        table.add_columns("Zeit", "Zone", "Typ", "Schweregrad", "Datei", "Aktion")
    
    def add_incident(self, incident) -> None:
        """Add incident to dashboard."""
        table = self.query_one("#incident-table", DataTable)
        severity_class = f"incident-{incident.severity}"
        table.add_row(
            incident.timestamp,
            incident.zone,
            incident.incident_type,
            incident.severity,
            incident.file_path,
            "Auto-Fix" if incident.auto_fixable else "Review"
        )


# --- Modal Dialogs ---

class ConfirmationModal(Static):
    """Multi-level confirmation modal."""
    
    DEFAULT_CSS = """
    ConfirmationModal {
        layer: modal;
        align: center middle;
        width: 80;
        height: auto;
        background: $surface;
        border: thick $error;
        padding: 2;
    }
    .level-indicator {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    .hotkey-display {
        color: $accent;
        text-style: bold;
    }
    """
    
    def __init__(self, level: int, total: int, hotkey: str, message: str, on_confirm: Callable, on_cancel: Callable):
        super().__init__()
        self.level = level
        self.total = total
        self.hotkey = hotkey
        self.message = message
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
    
    def compose(self) -> ComposeResult:
        yield Label(f"[bold]Bestätigung {self.level}/{self.total}[/bold]", classes="level-indicator")
        yield Static(self.message)
        yield Label(f"Drücken Sie '[bold]{self.hotkey}[/bold]' zum Fortfahren oder [bold]ESC[/bold] zum Abbrechen", classes="hotkey-display")
    
    def on_key(self, event: Key) -> None:
        if event.key == self.hotkey.lower():
            self.on_confirm()
            self.remove()
        elif event.key == "escape":
            self.on_cancel()
            self.remove()


class AISuggestionModal(Static):
    """Modal for AI suggestions with apply/dismiss."""
    
    DEFAULT_CSS = """
    AISuggestionModal {
        layer: modal;
        align: center middle;
        width: 90;
        height: auto;
        background: $surface;
        border: thick $accent;
        padding: 2;
    }
    """
    
    def __init__(self, suggestion: Dict, on_apply: Callable, on_dismiss: Callable):
        super().__init__()
        self.suggestion = suggestion
        self.on_apply = on_apply
        self.on_dismiss = on_dismiss
    
    def compose(self) -> ComposeResult:
        yield Label("🤖 KI-Vorschlag", classes="title")
        yield Static(f"Die KI schlägt vor: {self.suggestion.get('old', '')} → {self.suggestion.get('new', '')}")
        yield Static(f"Begründung: {self.suggestion.get('reason', '')}")
        with Horizontal():
            yield Button("Anwenden", id="ai-apply", variant="primary")
            yield Button("Verwerfen", id="ai-dismiss")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ai-apply":
            self.on_apply(self.suggestion)
        else:
            self.on_dismiss()
        self.remove()


class InitialSnapshotModal(Static):
    """Initial snapshot prompt on first run."""
    
    DEFAULT_CSS = """
    InitialSnapshotModal {
        layer: modal;
        align: center middle;
        width: 80;
        height: auto;
        background: $surface;
        border: thick $warning;
        padding: 2;
    }
    """
    
    def __init__(self, on_yes: Callable, on_no: Callable):
        super().__init__()
        self.on_yes = on_yes
        self.on_no = on_no
    
    def compose(self) -> ComposeResult:
        yield Label("⚠️ Initial-Snapshot erstellen?", classes="title")
        yield Static("Ein Initial-Snapshot sichert den aktuellen Zustand ALLER überwachten Daten. "
                     "Dies garantiert absolute Wiederherstellbarkeit, beansprucht aber erheblichen "
                     "Speicherplatz und Zeit.")
        with Horizontal():
            yield Button("Ja, Snapshot erstellen", id="snap-yes", variant="primary")
            yield Button("Überspringen (nicht empfohlen)", id="snap-no")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "snap-yes":
            self.on_yes()
        else:
            self.on_no()
        self.remove()


class RelaxTrustModal(Static):
    """Zero-Trust relaxation confirmation with typed phrase."""
    
    DEFAULT_CSS = """
    RelaxTrustModal {
        layer: modal;
        align: center middle;
        width: 80;
        height: auto;
        background: $surface;
        border: thick $error;
        padding: 2;
    }
    .warning-text {
        color: $error;
        text-style: bold;
    }
    """
    
    def __init__(self, bundle_name: str, on_confirm: Callable, on_cancel: Callable):
        super().__init__()
        self.bundle_name = bundle_name
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.input_buffer = ""
    
    def compose(self) -> ComposeResult:
        yield Label("⚠️ ZERO-TRUST DEAKTIVIEREN", classes="warning-text")
        yield Static(f"Sie deaktivieren Zero-Trust für: {self.bundle_name}")
        yield Static("Die KI darf dann autonome Änderungen vornehmen. "
                     "Nur nutzen, wenn Sie dem lokalen Modell voll vertrauen.")
        yield Label("Bestätigung: Tippen Sie 'RELAX_TRUST' ein:", classes="hotkey-display")
        yield Input(placeholder="RELAX_TRUST", id="confirm-input")
        with Horizontal():
            yield Button("Bestätigen", id="relax-confirm", variant="error", disabled=True)
            yield Button("Abbrechen", id="relax-cancel")
    
    def on_input_changed(self, event: Input.Changed) -> None:
        self.input_buffer = event.value
        confirm_btn = self.query_one("#relax-confirm", Button)
        confirm_btn.disabled = event.value != "RELAX_TRUST"
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "relax-confirm":
            self.on_confirm()
        else:
            self.on_cancel()
        self.remove()