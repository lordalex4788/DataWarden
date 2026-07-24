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
    TextArea,
)
from textual.worker import get_current_worker

from core.i18n import I18nManager
from core.indexer import Indexer, IndexWriter, SavestateManager
from core.models import ScanConfig, SymlinkMode
from ui.components import (
    CommanderTree,
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
    is_indexing: bool = False
    indexing_current: str = ""
    indexing_files_done: int = 0
    indexing_files_total: int = 0
    indexing_bytes_done: int = 0
    indexing_bytes_total: int = 0
    indexing_speed: str = ""
    indexing_eta: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.i18n = I18nManager()
        self.workspace = LayoutManager(self)
        self.theme_manager = ThemeManager(self)
        self.current_screen = "indexing"

    # --- Watchers for reactive attributes ---

    def watch_indexing_current(self, value: str) -> None:
        try:
            self.query_one("#idx-progress-current", Static).update(f"Aktuell: {value}")
        except Exception:
            pass

    def watch_indexing_files_done(self, value: int) -> None:
        try:
            total = self.indexing_files_total
            self.query_one("#idx-progress-count", Static).update(f"Dateien: {value}/{total}")
        except Exception:
            pass

    def watch_indexing_bytes_done(self, value: int) -> None:
        try:
            total = self.indexing_bytes_total
            mb_done = value / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.query_one("#idx-progress-bytes", Static).update(f"Größe: {mb_done:.1f}/{mb_total:.1f} MB")
        except Exception:
            pass

    def watch_indexing_speed(self, value: str) -> None:
        try:
            self.query_one("#idx-progress-speed", Static).update(f"Geschwindigkeit: {value}")
        except Exception:
            pass

    def watch_indexing_eta(self, value: str) -> None:
        try:
            self.query_one("#idx-progress-eta", Static).update(f"ETA: {value}")
        except Exception:
            pass

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
                            yield Checkbox(id="idx-hardlinks-track")
                            yield Label(self.i18n.t("indexing_check_hardlinks"))
                        with Vertical(classes="form-group half"):
                            yield Checkbox(id="idx-hardlinks-as-dupes")
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
                    with Horizontal(id="commander-panes"):
                        yield CommanderTree(path=str(Path.home()), id="cmd-left", classes="commander-pane")
                        yield CommanderTree(path=str(Path.home()), id="cmd-right", classes="commander-pane")
                    # Bottom panels - will be hidden/shown based on tabs
                    with Container(id="commander-bottom", classes="hidden"):
                        with Horizontal():
                            yield DuplicateTable(id="cmd-duplicate-table")
                            yield LogPanel(id="cmd-log-panel")

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
                    yield TextArea(id="notes-content")
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

        # Update CommanderTree paths and reload
        left_tree = self.query_one("#cmd-left", CommanderTree)
        right_tree = self.query_one("#cmd-right", CommanderTree)
        if left_tree and right_tree:
            left_tree.path = str(Path.home())
            right_tree.path = str(Path.home())
            left_tree.reload()
            right_tree.reload()

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

    # --- Action Methods ---

    def action_start_indexing(self) -> None:
        """Start the indexing process with current form values."""
        if self.is_indexing:
            self.notify("Indexierung läuft bereits", severity="warning")
            return

        # Collect form values
        root_path = self.query_one("#idx-root-path", Input).value.strip()
        if not root_path:
            self.notify("Kein Hauptordner angegeben", severity="error")
            return

        root = Path(root_path).expanduser().resolve()
        if not root.exists():
            self.notify(f"Ordner existiert nicht: {root}", severity="error")
            return
        if not root.is_dir():
            self.notify(f"Kein Verzeichnis: {root}", severity="error")
            return

        # Parse min/max size
        try:
            min_size_str = self.query_one("#idx-min-size", Input).value.strip()
            min_size = int(min_size_str) if min_size_str else 0
        except ValueError:
            min_size = 0

        try:
            max_size_str = self.query_one("#idx-max-size", Input).value.strip()
            max_size = int(max_size_str) if max_size_str else 0
        except ValueError:
            max_size = 0

        # Parse whitelist/blacklist
        whitelist_str = self.query_one("#idx-whitelist", Input).value.strip()
        whitelist = [ext.strip().lower() for ext in whitelist_str.split(",") if ext.strip()]

        blacklist_str = self.query_one("#idx-blacklist", Input).value.strip()
        blacklist = [ext.strip().lower() for ext in blacklist_str.split(",") if ext.strip()]

        all_types = self.query_one("#idx-check-all-types", Checkbox).value
        all_sizes = self.query_one("#idx-check-all-sizes", Checkbox).value

        # Symlink mode
        symlink_select = self.query_one("#idx-symlinks", Select)
        symlink_mode_str = symlink_select.value or "ignore"
        symlink_mode = SymlinkMode(symlink_mode_str)

        # Hardlinks
        hardlinks_track = self.query_one("#idx-hardlinks-track", Checkbox).value
        hardlinks_as_dupes = self.query_one("#idx-hardlinks-as-dupes", Checkbox).value

        # Max depth
        try:
            max_depth_str = self.query_one("#idx-max-depth", Input).value.strip()
            max_depth = int(max_depth_str) if max_depth_str else 0
        except ValueError:
            max_depth = 0

        # Build scan config
        config = ScanConfig(
            root_path=root,
            min_size=min_size if not all_sizes else 0,
            max_size=max_size if not all_sizes and max_size > 0 else None,
            whitelist_ext=whitelist if whitelist and not all_types else None,
            blacklist_ext=blacklist if blacklist and not all_types else None,
            symlink_mode=symlink_mode,
            track_hardlinks=hardlinks_track,
            treat_hardlinks_as_dupes=hardlinks_as_dupes,
            max_depth=max_depth if max_depth > 0 else None,
        )

        # Show progress area
        progress = self.query_one("#indexing-progress", Container)
        progress.remove_class("hidden")

        # Disable start button, enable resume/clear
        self.query_one("#idx-start", Button).disabled = True
        self.query_one("#idx-resume", Button).disabled = False
        self.query_one("#idx-clear", Button).disabled = False

        # Run in background worker
        self.run_worker(
            self._run_indexing(config, root),
            exclusive=True,
            thread=False,
        )

    async def _run_indexing(self, config: ScanConfig, root: Path) -> None:
        """Background worker for indexing."""
        worker = get_current_worker()
        self.is_indexing = True

        # Setup telemetry queue for live updates from indexer
        telemetry_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # Update progress UI from telemetry queue
        async def update_ui():
            while self.is_indexing and not worker.is_cancelled:
                try:
                    data = await asyncio.wait_for(telemetry_queue.get(), timeout=0.5)
                    self.indexing_current = data.current_file
                    self.indexing_files_done = data.files_done
                    self.indexing_files_total = data.files_total
                    self.indexing_bytes_done = data.bytes_done
                    self.indexing_bytes_total = data.bytes_total
                    self.indexing_speed = f"{data.files_per_sec:.0f} files/s"
                    if data.mb_per_sec > 0:
                        self.indexing_speed += f" ({data.mb_per_sec:.1f} MB/s)"
                    if data.eta_seconds > 0:
                        self.indexing_eta = f"{int(data.eta_seconds)}s"
                except TimeoutError:
                    continue

        ui_task = asyncio.create_task(update_ui())

        try:
            # Create savestate manager and index writer
            index_dir = Path("indexes") / root.name.replace(":", "_").replace("\\", "_").replace("/", "_")
            savestate = SavestateManager(index_dir, root)
            await savestate.load()

            index_writer = IndexWriter(index_dir)

            # Create indexer with telemetry queue
            indexer = Indexer(config, telemetry_queue=telemetry_queue)

            # Run scan - the indexer yields FileMetadata
            async for file_meta in indexer.scan(root, savestate, index_writer):
                if worker.is_cancelled:
                    break

                self.indexing_files_done += 1
                self.indexing_bytes_done += file_meta.size
                self.indexing_current = str(file_meta.path)

                # Update totals from indexer
                if self.indexing_files_total == 0:
                    self.indexing_files_total = indexer.total_files
                    self.indexing_bytes_total = indexer.total_bytes

                # Yield to event loop
                await asyncio.sleep(0)

            self.notify(f"Indexierung abgeschlossen: {self.indexing_files_done} Dateien", severity="information")

        except Exception as e:
            self.notify(f"Fehler bei Indexierung: {e}", severity="error")
        finally:
            self.is_indexing = False
            ui_task.cancel()

            # Re-enable start button
            self.query_one("#idx-start", Button).disabled = False

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
