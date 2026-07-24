#!/usr/bin/env python3
"""
DataWarden - Enterprise Duplicate Finder & Data Governance Platform

Main entry point for the Textual TUI application.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure core modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Label, Button, Input, Select, Tree, DataTable, Log, TabbedContent, TabPane
from textual.screen import Screen
from textual import events
from textual.message import Message
from textual.reactive import reactive

from ui.workspace import WorkspaceManager
from ui.components import CommanderTree, DuplicateTable, LogPanel, DescriptionPane, SettingsPane, FilterPane, ShellPane, GrepPanel, HexDebugPanel, NotePane, WardenDashboard
from core.i18n import I18nManager


class DataWardenApp(App):
    """Main DataWarden Textual Application."""

    TITLE = "DataWarden"
    SUB_TITLE = "Enterprise Duplicate Finder & Data Governance"
    
    CSS_PATH = "ui/app.tcss"
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "help", "Help"),
        Binding("f2", "menu_indexing", "Indexing"),
        Binding("f3", "menu_compare", "Compare"),
        Binding("f4", "menu_select", "Select"),
        Binding("f5", "menu_execute", "Execute"),
        Binding("f6", "menu_settings", "Settings"),
        Binding("f7", "menu_commander", "Commander"),
        Binding("f8", "menu_warden", "Warden"),
        Binding("f9", "menu_notes", "Notes"),
        Binding("f10", "toggle_theme", "Theme"),
        Binding("f12", "global_notes", "Global Notes"),
        Binding("ctrl+left", "resize_left", "Resize Left"),
        Binding("ctrl+right", "resize_right", "Resize Right"),
        Binding("ctrl+up", "resize_up", "Resize Up"),
        Binding("ctrl+down", "resize_down", "Resize Down"),
    ]

    # Reactive attributes for live updates
    current_mode: reactive[str] = reactive("AUDIT")
    trust_level: reactive[int] = reactive(0)
    quarantine_usage: reactive[str] = reactive("0/0 GB")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.i18n = I18nManager()
        self.workspace = WorkspaceManager()
        self.current_screen = "indexing"

    def compose(self) -> ComposeResult:
        """Compose the main application layout."""
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            # Left sidebar - navigation
            with Vertical(id="sidebar"):
                yield Static(self.i18n.t("app_title"), id="app-title")
                yield Static(self.i18n.t("app_subtitle"), id="app-subtitle")
                
                # Navigation buttons
                nav_buttons = [
                    ("menu_indexing", "indexing"),
                    ("menu_compare", "compare"),
                    ("menu_select", "select"),
                    ("menu_execute", "execute"),
                    ("menu_settings", "settings"),
                    ("menu_commander", "commander"),
                    ("menu_warden", "warden"),
                    ("menu_notes", "notes"),
                ]
                
                for key, screen_id in nav_buttons:
                    btn = Button(self.i18n.t(key), id=f"nav-{screen_id}", classes="nav-button")
                    btn.screen_id = screen_id
                    yield btn
            
            # Main content area - dynamic based on current screen
            with Container(id="content-area"):
                # Default: Indexing Screen
                yield self._build_indexing_screen()
        
        yield Footer()

    def _build_indexing_screen(self) -> Container:
        """Build the indexing configuration screen."""
        with Container(id="indexing-screen", classes="screen"):
            yield Static(self.i18n.t("indexing_title"), classes="screen-title")
            yield Static(self.i18n.t("indexing_description"), classes="screen-description")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("indexing_label_root_path"))
                yield Input(placeholder=self.i18n.t("indexing_placeholder_root_path"), id="idx-root-path")
            
            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("indexing_label_min_size"))
                    yield Input(placeholder="0", id="idx-min-size", type="number")
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("indexing_label_max_size"))
                    yield Input(placeholder="unlimited", id="idx-max-size", type="number")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("indexing_label_whitelist"))
                yield Input(placeholder=self.i18n.t("indexing_placeholder_whitelist"), id="idx-whitelist")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("indexing_label_blacklist"))
                yield Input(placeholder=self.i18n.t("indexing_placeholder_blacklist"), id="idx-blacklist")
            
            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("indexing_check_all_types"))
                    yield Input(type="checkbox", id="idx-all-types")
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("indexing_check_all_sizes"))
                    yield Input(type="checkbox", id="idx-all-sizes")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("indexing_label_symlinks"))
                yield Select(
                    options=[
                        (self.i18n.t("indexing_symlink_ignore"), "ignore"),
                        (self.i18n.t("indexing_symlink_follow"), "follow"),
                        (self.i18n.t("indexing_symlink_record"), "record"),
                    ],
                    id="idx-symlinks",
                    value="ignore"
                )
            
            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group half"):
                    yield Input(type="checkbox", id="idx-hardlinks")
                    yield Label(self.i18n.t("indexing_check_hardlinks"))
                with Vertical(classes="form-group half"):
                    yield Input(type="checkbox", id="idx-hardlinks-dupes")
                    yield Label(self.i18n.t("indexing_check_hardlinks_as_dupes"))
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("indexing_label_max_depth"))
                yield Input(placeholder="0", id="idx-max-depth", type="number")
            
            with Horizontal(classes="button-row"):
                yield Button(self.i18n.t("indexing_btn_start"), id="idx-start", variant="primary")
                yield Button(self.i18n.t("indexing_btn_resume"), id="idx-resume")
                yield Button(self.i18n.t("indexing_btn_clear"), id="idx-clear", variant="error")
            
            # Progress area
            with Container(id="indexing-progress", classes="progress-area hidden"):
                yield Static("", id="idx-progress-current", classes="progress-line")
                yield Static("", id="idx-progress-count", classes="progress-line")
                yield Static("", id="idx-progress-bytes", classes="progress-line")
                yield Static("", id="idx-progress-speed", classes="progress-line")
                yield Static("", id="idx-progress-eta", classes="progress-line")
                yield Static("", id="idx-progress-types", classes="progress-line")
                yield Static("", id="idx-progress-total", classes="progress-line")
                yield Static("", id="idx-progress-warnings", classes="progress-line warning")
                yield Static("", id="idx-progress-errors", classes="progress-line error")

        return Container()

    def _build_compare_screen(self) -> Container:
        """Build the comparison/duplicate search screen."""
        with Container(id="compare-screen", classes="screen hidden"):
            yield Static(self.i18n.t("compare_title"), classes="screen-title")
            yield Static(self.i18n.t("compare_description"), classes="screen-description")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("compare_mode_intra"))
                yield Input(type="radio", name="compare-mode", value="intra", id="cmp-mode-intra")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("compare_mode_inter"))
                yield Input(type="radio", name="compare-mode", value="inter", id="cmp-mode-inter")
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("compare_label_ref_folders"))
                # Tree for reference folder selection
                tree = Tree("Indexes", id="cmp-ref-tree")
                tree.show_root = False
                yield tree
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("compare_label_target_folders"))
                tree = Tree("Indexes", id="cmp-target-tree")
                tree.show_root = False
                yield tree
            
            with Horizontal(classes="button-row"):
                yield Button(self.i18n.t("compare_btn_start"), id="cmp-start", variant="primary")
            
            # Results area
            with Container(id="compare-results", classes="results-area hidden"):
                yield Static("", id="cmp-result-groups")
                yield Static("", id="cmp-result-wasted")
                yield Static("", id="cmp-result-ref-protected")
                yield DuplicateTable(id="cmp-duplicate-table")

        return Container()

    def _build_select_screen(self) -> Container:
        """Build the auto-select filter configuration screen."""
        with Container(id="select-screen", classes="screen hidden"):
            yield Static(self.i18n.t("select_title"), classes="screen-title")
            yield Static(self.i18n.t("select_description"), classes="screen-description")
            
            yield Label(self.i18n.t("select_label_pipeline"))
            
            # Filter pipeline list (reorderable)
            with Container(id="filter-pipeline", classes="filter-pipeline"):
                # Filters added dynamically
                pass
            
            with Horizontal(classes="button-row"):
                yield Button(self.i18n.t("select_btn_add_filter"), id="sel-add-filter")
                yield Button(self.i18n.t("select_btn_remove_filter"), id="sel-remove-filter")
                yield Button(self.i18n.t("select_btn_move_up"), id="sel-move-up")
                yield Button(self.i18n.t("select_btn_move_down"), id="sel-move-down")
            
            # Filter type selector
            with Vertical(classes="form-group"):
                yield Select(
                    options=[
                        (self.i18n.t("select_filter_path_priority"), "path_priority"),
                        (self.i18n.t("select_filter_filename_hygiene"), "filename_hygiene"),
                        (self.i18n.t("select_filter_artifact"), "artifact"),
                        (self.i18n.t("select_filter_path_depth"), "path_depth"),
                        (self.i18n.t("select_filter_timestamp"), "timestamp"),
                        (self.i18n.t("select_filter_owner"), "owner"),
                    ],
                    id="sel-filter-type",
                    prompt="Filter-Typ wählen..."
                )
            
            with Horizontal(classes="button-row"):
                yield Button(self.i18n.t("select_btn_run"), id="sel-run", variant="primary")
            
            # Results summary
            with Container(id="select-results", classes="results-area hidden"):
                yield Static("", id="sel-result-summary")

        return Container()

    def _build_execute_screen(self) -> Container:
        """Build the execution screen."""
        with Container(id="execute-screen", classes="screen hidden"):
            yield Static(self.i18n.t("execute_title"), classes="screen-title")
            
            with Vertical(classes="form-group"):
                yield Input(type="radio", name="exec-mode", value="audit", id="exec-mode-audit")
                yield Label(self.i18n.t("execute_mode_audit"))
            
            with Vertical(classes="form-group"):
                yield Input(type="radio", name="exec-mode", value="safe", id="exec-mode-safe")
                yield Label(self.i18n.t("execute_mode_safe"))
            
            with Vertical(classes="form-group"):
                yield Input(type="radio", name="exec-mode", value="hard", id="exec-mode-hard")
                yield Label(self.i18n.t("execute_mode_hard"))
            
            with Vertical(classes="form-group"):
                yield Label(self.i18n.t("execute_label_quarantine"))
                yield Input(placeholder="~/.datawarden/quarantine/", id="exec-quarantine-path")
            
            with Vertical(classes="form-group"):
                yield Input(type="checkbox", id="exec-initial-snapshot")
                yield Label(self.i18n.t("execute_check_initial_snapshot"))
            
            yield Static(self.i18n.t("execute_warn_initial_snapshot"), classes="warning-box")
            
            with Horizontal(classes="button-row"):
                yield Button(self.i18n.t("execute_btn_confirm"), id="exec-confirm", variant="primary")
                yield Button(self.i18n.t("execute_btn_rollback"), id="exec-rollback", variant="warning")
            
            yield Static(self.i18n.t("execute_label_retention").format(count=5, gb=10), id="exec-retention")

        return Container()

    def _build_settings_screen(self) -> Container:
        """Build the settings screen."""
        with Container(id="settings-screen", classes="screen hidden"):
            yield Static(self.i18n.t("settings_title"), classes="screen-title")
            
            # UI & Theming
            yield Static(self.i18n.t("settings_section_ui"), classes="section-title")
            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("settings_label_theme"))
                    yield Select(options=[("Dark", "dark"), ("Light", "light"), ("Nord", "nord"), ("Dracula", "dracula")], id="set-theme")
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("settings_label_language"))
                    yield Select(options=[("Deutsch", "de_DE"), ("English", "en_US")], id="set-language")
            
            # Confirmation Engine
            yield Static(self.i18n.t("settings_section_confirm"), classes="section-title")
            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("settings_label_confirm_levels"))
                    yield Input(type="number", value="3", min="0", max="5", id="set-confirm-levels")
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("settings_label_confirm_hotkeys"))
                    yield Input(placeholder="F10,J,Enter", id="set-confirm-hotkeys")
            
            yield Static(self.i18n.t("settings_explain_confirm_tradeoff"), classes="info-box")
            
            # AI Integration
            yield Static(self.i18n.t("settings_section_ai"), classes="section-title")
            with Vertical(classes="form-group"):
                yield Input(type="checkbox", id="set-ai-enabled")
                yield Label(self.i18n.t("settings_check_ai_enabled"))
            
            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("settings_label_ollama_url"))
                    yield Input(placeholder="http://localhost:11434", id="set-ollama-url")
                with Vertical(classes="form-group half"):
                    yield Label(self.i18n.t("settings_label_ai_model"))
                    yield Input(placeholder="qwen2.5-coder:7b", id="set-ai-model")
            
            # Trust Level
            yield Label(self.i18n.t("settings_label_trust_level"))
            yield Select(
                options=[
                    (self.i18n.t("settings_trust_0"), "0"),
                    (self.i18n.t("settings_trust_1"), "1"),
                    (self.i18n.t("settings_trust_2"), "2"),
                    (self.i18n.t("settings_trust_3"), "3"),
                ],
                id="set-trust-level",
                value="0"
            )
            
            # Bundle Gatekeepers
            yield Static(self.i18n.t("settings_section_bundles"), classes="section-title")
            bundles = [
                ("set-bundle-ui", self.i18n.t("settings_bundle_ui")),
                ("set-bundle-filters", self.i18n.t("settings_bundle_filters")),
                ("set-bundle-files", self.i18n.t("settings_bundle_files")),
                ("set-bundle-governance", self.i18n.t("settings_bundle_governance")),
            ]
            for bid, label in bundles:
                with Horizontal(classes="form-row"):
                    yield Input(type="checkbox", id=bid)
                    yield Label(label)
            
            yield Static(self.i18n.t("settings_warn_relax_trust"), classes="warning-box")
            
            # Error Handling
            yield Static(self.i18n.t("settings_section_errors"), classes="section-title")
            error_types = [
                ("set-err-perm", self.i18n.t("settings_label_err_perm")),
                ("set-err-locked", self.i18n.t("settings_label_err_locked")),
                ("set-err-corrupt", self.i18n.t("settings_label_err_corrupt")),
            ]
            for eid, label in error_types:
                with Horizontal(classes="form-row"):
                    yield Label(label)
                    yield Select(
                        options=[
                            (self.i18n.t("settings_err_ask"), "ask"),
                            (self.i18n.t("settings_err_auto_skip"), "auto_skip"),
                            (self.i18n.t("settings_err_retry"), "retry"),
                        ],
                        id=eid,
                        value="ask"
                    )

        return Container()

    def _build_commander_screen(self) -> Container:
        """Build the Commander/File Manager screen."""
        with Container(id="commander-screen", classes="screen hidden"):
            yield Static(self.i18n.t("commander_title"), classes="screen-title")
            yield Static(self.i18n.t("commander_hint_bar"), classes="hint-bar")
            
            with Horizontal(id="commander-panes"):
                # Left pane
                with Vertical(id="cmd-left-pane", classes="commander-pane"):
                    yield CommanderTree(id="cmd-left-tree", path=".")
                
                # Right pane
                with Vertical(id="cmd-right-pane", classes="commander-pane"):
                    yield CommanderTree(id="cmd-right-tree", path=".")
            
            # Grep panel
            with Container(id="cmd-grep", classes="panel hidden"):
                yield Label(self.i18n.t("commander_label_grep"))
                yield Input(placeholder=self.i18n.t("commander_placeholder_grep"), id="cmd-grep-input")
                yield DataTable(id="cmd-grep-results")
            
            # Shell panel
            with Container(id="cmd-shell", classes="panel hidden"):
                yield Label(self.i18n.t("commander_label_shell"))
                yield Input(placeholder=self.i18n.t("commander_placeholder_shell"), id="cmd-shell-input")
                yield Log(id="cmd-shell-output", highlight=True)
            
            # Hex panel
            with Container(id="cmd-hex", classes="panel hidden"):
                yield Label(self.i18n.t("commander_label_hex"))
                yield HexDebugPanel(id="cmd-hex-panel")

        return Container()

    def _build_warden_screen(self) -> Container:
        """Build the FileSystem Warden screen."""
        with Container(id="warden-screen", classes="screen hidden"):
            yield Static(self.i18n.t("warden_title"), classes="screen-title")
            yield Static(self.i18n.t("warden_description"), classes="screen-description")
            
            yield Label(self.i18n.t("warden_label_zones"))
            yield Button(self.i18n.t("warden_btn_add_zone"), id="warden-add-zone")
            
            # Zone list (dynamic)
            with Container(id="warden-zones", classes="zone-list"):
                pass
            
            yield Label(self.i18n.t("warden_label_incidents"))
            yield WardenDashboard(id="warden-dashboard")
            
            # Query line
            yield Label(self.i18n.t("warden_label_query"))
            yield Input(placeholder=self.i18n.t("warden_placeholder_query"), id="warden-query-input")
            yield Button("Suchen", id="warden-query-search", variant="primary")

        return Container()

    def _build_notes_screen(self) -> Container:
        """Build the Notes screen."""
        with Container(id="notes-screen", classes="screen hidden"):
            yield Static(self.i18n.t("notes_title"), classes="screen-title")
            yield Static(self.i18n.t("notes_description"), classes="screen-description")
            
            yield Button(self.i18n.t("notes_btn_new"), id="notes-new", variant="primary")
            yield Label(self.i18n.t("notes_label_content"))
            yield Input(id="notes-content", multiline=True)
            yield Button(self.i18n.t("notes_btn_archive"), id="notes-archive")

        return Container()

    def on_mount(self) -> None:
        """Initialize app on mount."""
        self.switch_screen("indexing")
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from file."""
        # TODO: Implement config loading
        pass

    def save_config(self) -> None:
        """Save configuration to file."""
        # TODO: Implement config saving
        pass

    def switch_screen(self, screen_id: str) -> None:
        """Switch to a different screen."""
        # Hide all screens
        for screen in self.query(".screen"):
            screen.add_class("hidden")
        
        # Show target screen
        target = self.query_one(f"#{screen_id}-screen")
        target.remove_class("hidden")
        
        # Update nav button states
        for btn in self.query(".nav-button"):
            btn.remove_class("active")
            if getattr(btn, "screen_id", "") == screen_id:
                btn.add_class("active")
        
        self.current_screen = screen_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        btn_id = event.button.id
        
        # Navigation buttons
        if btn_id and btn_id.startswith("nav-"):
            screen_id = btn_id[4:]
            self.switch_screen(screen_id)
            return
        
        # Indexing actions
        if btn_id == "idx-start":
            self.action_start_indexing()
        elif btn_id == "idx-resume":
            self.action_resume_indexing()
        elif btn_id == "idx-clear":
            self.action_clear_index()
        
        # Compare actions
        elif btn_id == "cmp-start":
            self.action_start_comparison()
        
        # Select actions
        elif btn_id == "sel-add-filter":
            self.action_add_filter()
        elif btn_id == "sel-remove-filter":
            self.action_remove_filter()
        elif btn_id == "sel-move-up":
            self.action_move_filter_up()
        elif btn_id == "sel-move-down":
            self.action_move_filter_down()
        elif btn_id == "sel-run":
            self.action_run_auto_select()
        
        # Execute actions
        elif btn_id == "exec-confirm":
            self.action_confirm_execution()
        elif btn_id == "exec-rollback":
            self.action_rollback_snapshot()
        
        # Warden actions
        elif btn_id == "warden-add-zone":
            self.action_add_warden_zone()
        elif btn_id == "warden-query-search":
            self.action_warden_query()
        
        # Notes actions
        elif btn_id == "notes-new":
            self.action_new_note()
        elif btn_id == "notes-archive":
            self.action_open_note_archive()

    # Action methods (to be implemented)
    def action_start_indexing(self) -> None:
        self.notify("Indexierung gestartet...", severity="information")

    def action_resume_indexing(self) -> None:
        self.notify("Indexierung fortgesetzt...", severity="information")

    def action_clear_index(self) -> None:
        self.notify("Index gelöscht", severity="warning")

    def action_start_comparison(self) -> None:
        self.notify("Vergleich gestartet...", severity="information")

    def action_add_filter(self) -> None:
        self.notify("Filter hinzugefügt", severity="information")

    def action_remove_filter(self) -> None:
        self.notify("Filter entfernt", severity="information")

    def action_move_filter_up(self) -> None:
        pass

    def action_move_filter_down(self) -> None:
        pass

    def action_run_auto_select(self) -> None:
        self.notify("Auto-Selektion ausgeführt", severity="information")

    def action_confirm_execution(self) -> None:
        self.notify("Ausführung bestätigt - Bestätigungs-Modal würde hier erscheinen", severity="information")

    def action_rollback_snapshot(self) -> None:
        self.notify("Snapshot Rollback...", severity="warning")

    def action_add_warden_zone(self) -> None:
        self.notify("Warden Zone hinzufügen...", severity="information")

    def action_warden_query(self) -> None:
        self.notify("Warden Abfrage...", severity="information")

    def action_new_note(self) -> None:
        self.notify("Neue Notiz erstellen...", severity="information")

    def action_open_note_archive(self) -> None:
        self.notify("Globales Notiz-Archiv öffnen...", severity="information")

    def action_help(self) -> None:
        self.notify("Hilfe: Drücken Sie F1-F12 für Navigation, Strg+Pfeile für Resize", severity="information")

    def action_menu_indexing(self) -> None:
        self.switch_screen("indexing")

    def action_menu_compare(self) -> None:
        self.switch_screen("compare")

    def action_menu_select(self) -> None:
        self.switch_screen("select")

    def action_menu_execute(self) -> None:
        self.switch_screen("execute")

    def action_menu_settings(self) -> None:
        self.switch_screen("settings")

    def action_menu_commander(self) -> None:
        self.switch_screen("commander")

    def action_menu_warden(self) -> None:
        self.switch_screen("warden")

    def action_menu_notes(self) -> None:
        self.switch_screen("notes")

    def action_toggle_theme(self) -> None:
        self.notify("Theme umschalten...", severity="information")

    def action_global_notes(self) -> None:
        self.action_open_note_archive()

    def action_resize_left(self) -> None:
        self.workspace.resize_pane("left", -10)

    def action_resize_right(self) -> None:
        self.workspace.resize_pane("right", 10)

    def action_resize_up(self) -> None:
        self.workspace.resize_pane("up", -10)

    def action_resize_down(self) -> None:
        self.workspace.resize_pane("down", 10)


def main() -> None:
    """Main entry point."""
    app = DataWardenApp()
    app.run()


if __name__ == "__main__":
    main()