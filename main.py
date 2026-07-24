#!/usr/bin/env python3
"""
DataWarden - Enterprise Duplicate Finder & Data Governance Platform

Main entry point for the Textual TUI application.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure core modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
)

from core.i18n import I18nManager
from ui.components import (
    DuplicateTable,
    LogPanel,
    SettingsPane,
    WardenDashboard,
)
from ui.workspace import LayoutManager, ThemeManager


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
    current_mode: str = "AUDIT"
    trust_level: int = 0
    quarantine_usage: str = "0/0 GB"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.i18n = I18nManager()
        self.workspace = LayoutManager(self)
        self.theme_manager = ThemeManager(self)
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

            # Main content area - all screens
            with Container(id="content-area"):
                # Indexing Screen
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
                            yield Checkbox()
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("indexing_check_all_sizes"))
                            yield Checkbox()

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
                            yield Checkbox()
                            yield Label(self.i18n.t("indexing_check_hardlinks"))
                        with Vertical(classes="form-group half"):
                            yield Checkbox()
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

                # Compare Screen
                with Container(id="compare-screen", classes="screen hidden"):
                    yield Static(self.i18n.t("compare_title"), classes="screen-title")
                    yield Static(self.i18n.t("compare_description"), classes="screen-description")

                    with Horizontal(classes="form-row"):
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("compare_label_ref_folder"))
                            yield Input(placeholder=self.i18n.t("compare_placeholder_ref_folder"), id="cmp-ref-folder")

                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("compare_label_target_folder"))
                            yield Input(placeholder=self.i18n.t("compare_placeholder_target_folder"), id="cmp-target-folder")

                    with Horizontal(classes="form-row"):
                        with Vertical(classes="form-group half"):
                            yield Checkbox(label=self.i18n.t("compare_check_intra"), id="cmp-intra")
                        with Vertical(classes="form-group half"):
                            yield Checkbox(label=self.i18n.t("compare_check_inter"), id="cmp-inter")

                    with Horizontal(classes="button-row"):
                        yield Button(self.i18n.t("compare_btn_start"), id="cmp-start", variant="primary")
                        yield Button(self.i18n.t("compare_btn_load_index"), id="cmp-load")

                    with Container(id="compare-results", classes="results-area hidden"):
                        yield Static(self.i18n.t("compare_results_title"), classes="section-title")
                        yield DuplicateTable(id="cmp-duplicate-table")

                # Select Screen
                with Container(id="select-screen", classes="screen hidden"):
                    yield Static(self.i18n.t("select_title"), classes="screen-title")
                    yield Static(self.i18n.t("select_description"), classes="screen-description")

                    with Horizontal(classes="form-row"):
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("select_label_available_filters"))
                            yield DataTable(id="sel-available-filters")
                            yield Button(self.i18n.t("select_btn_add_filter"), id="sel-add-filter")

                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("select_label_active_pipeline"))
                            yield DataTable(id="sel-active-pipeline")
                            with Horizontal(classes="button-row"):
                                yield Button(self.i18n.t("select_btn_remove"), id="sel-remove-filter")
                                yield Button(self.i18n.t("select_btn_up"), id="sel-move-up")
                                yield Button(self.i18n.t("select_btn_down"), id="sel-move-down")

                    yield Container(id="sel-filter-params", classes="form-group")

                    with Horizontal(classes="button-row"):
                        yield Button(self.i18n.t("select_btn_save_preset"), id="sel-save-preset")
                        yield Button(self.i18n.t("select_btn_load_preset"), id="sel-load-preset")
                        yield Button(self.i18n.t("select_btn_run"), id="sel-run", variant="primary")

                    with Container(id="select-preview", classes="results-area hidden"):
                        yield Static(self.i18n.t("select_preview_title"), classes="section-title")
                        yield DuplicateTable(id="sel-preview-table")

                # Execute Screen
                with Container(id="execute-screen", classes="screen hidden"):
                    yield Static(self.i18n.t("execute_title"), classes="screen-title")
                    yield Static(self.i18n.t("execute_description"), classes="screen-description")

                    with Horizontal(classes="form-row"):
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("execute_label_mode"))
                            yield Select(
                                options=[
                                    (self.i18n.t("execute_mode_audit"), "audit"),
                                    (self.i18n.t("execute_mode_safe_move"), "safe_move"),
                                    (self.i18n.t("execute_mode_hard_delete"), "hard_delete"),
                                ],
                                id="exec-mode",
                                value="audit"
                            )

                    with Horizontal(classes="form-row"):
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("execute_label_quarantine"))
                            yield Input(placeholder=self.i18n.t("execute_placeholder_quarantine"), id="exec-quarantine")
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("execute_label_retention_gb"))
                            yield Input(placeholder="50", id="exec-retention-gb", type="number")

                    with Horizontal(classes="form-row"):
                        with Vertical(classes="form-group half"):
                            yield Label(self.i18n.t("execute_label_retention_count"))
                            yield Input(placeholder="10", id="exec-retention-count", type="number")

                    with Horizontal(classes="button-row"):
                        yield Button(self.i18n.t("execute_btn_preview"), id="exec-preview", variant="primary")
                        yield Button(self.i18n.t("execute_btn_confirm"), id="exec-confirm", variant="success")
                        yield Button(self.i18n.t("execute_btn_rollback"), id="exec-rollback", variant="warning")

                    with Container(id="execute-preview", classes="results-area hidden"):
                        yield Static(self.i18n.t("execute_preview_title"), classes="section-title")
                        yield LogPanel(id="exec-preview-log")

                # Settings Screen
                with Container(id="settings-screen", classes="screen hidden"):
                    yield Static(self.i18n.t("settings_title"), classes="screen-title")
                    yield SettingsPane(id="settings-pane")

                # Commander Screen
                with Container(id="commander-screen", classes="screen hidden"):
                    yield Static("Commander Workspace", id="cmd-placeholder")

                # Warden Screen
                with Container(id="warden-screen", classes="screen hidden"):
                    yield Static(self.i18n.t("warden_title"), classes="screen-title")
                    yield Static(self.i18n.t("warden_description"), classes="screen-description")

                    yield Label(self.i18n.t("warden_label_zones"))
                    yield Button(self.i18n.t("warden_btn_add_zone"), id="warden-add-zone")

                    yield Container(id="warden-zones", classes="zone-list")

                    yield Label(self.i18n.t("warden_label_incidents"))
                    yield WardenDashboard(id="warden-dashboard")

                    yield Label(self.i18n.t("warden_label_query"))
                    yield Input(placeholder=self.i18n.t("warden_placeholder_query"), id="warden-query-input")
                    yield Button("Suchen", id="warden-query-search", variant="primary")

                # Notes Screen
                with Container(id="notes-screen", classes="screen hidden"):
                    yield Static(self.i18n.t("notes_title"), classes="screen-title")
                    yield Static(self.i18n.t("notes_description"), classes="screen-description")

                    yield Button(self.i18n.t("notes_btn_new"), id="notes-new", variant="primary")
                    yield Label(self.i18n.t("notes_label_content"))
                    yield Input(id="notes-content", multiline=True)
                    yield Button(self.i18n.t("notes_btn_archive"), id="notes-archive")

        yield Footer()

    # --- App Lifecycle ---

    def on_mount(self) -> None:
        """Initialize app on mount."""
        self.switch_screen("indexing")
        self.load_config()
        self.theme_manager.apply_theme("dark")

    def load_config(self) -> None:
        """Load configuration from file."""
        # TODO: Implement config loading
        pass

    def save_config(self) -> None:
        """Save configuration to file."""
        # TODO: Implement config saving
        pass

    # --- Screen Management ---

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

        # Special handling for commander screen - initialize layout
        if screen_id == "commander":
            self._init_commander_layout()

    def _init_commander_layout(self) -> None:
        """Initialize the Commander layout using LayoutManager."""
        if not self.workspace.root:
            self.workspace.create_default_layout()

    # --- Event Handlers ---

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
        elif btn_id == "cmp-load":
            self.action_load_index()

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
        elif btn_id == "sel-save-preset":
            self.action_save_filter_preset()
        elif btn_id == "sel-load-preset":
            self.action_load_filter_preset()

        # Execute actions
        elif btn_id == "exec-preview":
            self.action_preview_execution()
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

    # --- Action Methods (Stubs to be implemented) ---

    def action_start_indexing(self) -> None:
        self.notify("Indexierung gestartet...", severity="information")

    def action_resume_indexing(self) -> None:
        self.notify("Indexierung fortgesetzt...", severity="information")

    def action_clear_index(self) -> None:
        self.notify("Index gelöscht", severity="warning")

    def action_start_comparison(self) -> None:
        self.notify("Vergleich gestartet...", severity="information")

    def action_load_index(self) -> None:
        self.notify("Index laden...", severity="information")

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

    def action_save_filter_preset(self) -> None:
        self.notify("Preset gespeichert", severity="information")

    def action_load_filter_preset(self) -> None:
        self.notify("Preset geladen", severity="information")

    def action_preview_execution(self) -> None:
        self.notify("Ausführung-Vorschau...", severity="information")

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
