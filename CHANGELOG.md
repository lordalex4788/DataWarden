# Changelog

All notable changes to DataWarden2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with a custom scheme: `0.05.10` → `0.05.20` → ... → `0.05.90` → `0.10.10`

## [0.05.20] - 2026-07-24 15:45:00

### Setup
* **Project Structure:** Created complete directory structure (`core/`, `ui/`, `locale/`, `scripts/`, `tests/`, `indexes/`, `config/`)
* **Requirements:** `requirements.txt` with pinned versions (textual, rich, xxhash, aiofiles, watchdog, pytest, ruff, mypy)
* **Build Config:** `pyproject.toml` with setuptools, pytest, ruff, mypy, coverage configuration
* **Scripts:** Interactive `setup.sh` (venv name/path), `start.sh` (activate venv → run → deactivate), `update.sh` (git pull + pip upgrade)
* **Git:** `.gitignore` with Python, venv, indexes, logs, IDE excludes

### Core
* **i18n Manager** (`core/i18n.py`): Loads `.lang` files, parses keys + descriptor comments, fallback to default locale
* **Models** (`core/models.py`): Complete dataclasses for FileMetadata, ScanConfig, Savestate, DuplicateGroup, Snapshot, WardenZone, WardenIncident, TelemetryData, Enums (SymlinkMode, ScanStatus, ErrorAction, ExecutionMode, TrustLevel)
* **Indexer** (`core/indexer.py`): HashEngine (xxh3_64 streaming), MetadataExtractor, FileTypeFilter, SavestateManager (folder compression), IndexWriter (JSONL splitting + manifest), SymlinkHandler (loop detection), HardlinkTracker, ErrorManager
* **Ref Engine** (`core/ref_engine.py`): CrossReferenceEngine (SQLite in-memory), intra/inter folder comparison, reference protection logic
* **Selector** (`core/selector.py`): Filter protocol + pipeline, 6 built-in filters (PathPriority, FilenameHygiene, Artifact, PathDepth, Timestamp, Owner), cascade logic, preset serialization
* **Snapshot** (`core/snapshot.py`): SnapshotManager (transactional, quarantine mirror, rollback, retention), ExecutionEngine (audit/safe_move/hard_delete + audit log)
* **Telemetry** (`core/telemetry.py`): Async TelemetryEngine with subscriber queues, rolling speed/ETA calculation
* **Error Handler** (`core/error_handler.py`): ErrorManager with ASK/AUTO_SKIP/RETRY rules, ErrorHandler integration with savestate
* **Confirmation** (`core/confirmation.py`): Multi-level ConfirmationEngine with custom hotkeys, ConfirmationManager per mode, profiles (minimal/standard/strict/paranoid)
* **AI Filter** (`core/ai_filter.py`): AIFilterEngine with OllamaClient, SelectionAssist, NL→Filter Pipeline, CopilotExplain/Suggest, WardenTriage/Query
* **Policy** (`core/policy.py`): DynamicPolicyManager with GlobalTrustLevel (0-3), BundleGatekeepers (4 bundles), LearnedRules (dynamic whitelist), RELAX_TRUST flow
* **Notes** (`core/notes.py`): MetadataNoteManager (path-attached notes, tree indicators `[📝 N]`, global archive F12, search)
* **Warden** (`core/warden.py`): FileSystemWarden (watchdog), 3-pillar validation (perms/naming/classification), LLM triage, incident dashboard, natural language query

### UI
* **Main App** (`main.py`): DataWardenApp with 9 screens (Indexing, Compare, Select, Execute, Settings, Commander, Warden, Notes), navigation, bindings
* **Components** (`ui/components.py`): CommanderTree (MC keys), DuplicateTable, LogPanel (tree expand/collapse), DescriptionPane, SettingsPane, FilterPane, ShellPane, GrepPanel, HexDebugPanel, NotePane, WardenDashboard + Modals (Confirmation, AI, InitialSnapshot, RelaxTrust)
* **Workspace** (`ui/workspace.py`): LayoutManager (binary split tree, resize, persist), ThemeManager (4 builtin + custom, live reload, CSS variables)

### Locale
* **German** (`locale/de_DE.lang`): 200+ keys with descriptor comments
* **English** (`locale/en_US.lang`): 200+ keys with descriptor comments

### Docs
* **README.md**: Bilingual (DE/EN) with overview, features table, install, quickstart, structure, license
* **PLAN.md**: Complete 9-phase build plan with dependencies, milestones, risks, open decisions
* **AGENTS.md**: opencode agent instructions (workflow, phases, coding standards, testing, safety checks, escalation)

---

## [0.05.10] - 2026-07-24 14:30:00

### Planning & Architecture
* **Initial Planning:** Complete architecture design for DataWarden2 - Enterprise-grade TUI duplicate finder & data governance platform
* **UI Concept:** Textual-based 2-Pane Commander interface with dynamic split/resize layouts
* **i18n System:** Dynamic localization via `.lang` files in `locale/` directory with descriptor comments for community translations
* **Core Logic:** Indexing parameters (size, type, metadata) defined; Savestate compression (file-level → folder-level) specified
* **Reference System:** Reference vs. Non-Reference folder logic designed
* **Infrastructure:** `setup.sh`, `start.sh`, `update.sh` scripts and `requirements.txt` specified
* **Security Model:** Zero-Trust AI (Level 0 default), Multi-Level Confirmation, Snapshot-before-write, Audit logging
* **AI Integration:** Local LLM via Ollama for Selection Assist, NL→Filter Builder, Copilot Panel
* **Governance:** FileSystem Warden with Watchdog daemon, 3-pillar validation, Admin Dashboard
* **Version Scheme:** Defined custom versioning (0.05.10 → 0.05.20 ... 0.05.90 → 0.10.10)
* **Documentation:** Bilingual README (DE/EN) structure defined

---

## Version History Template

### [X.Y.Z] - YYYY-MM-DD HH:MM:SS

#### Category
* **Description:** Details

#### Categories
- **Setup** - Project structure, configs, scripts, dependencies
- **Core** - Indexer, Ref Engine, Selector, Snapshot, Execution
- **UI** - Textual components, layouts, themes, widgets
- **AI** - LLM integration, filters, copilot, policies
- **Snapshot** - Transaction system, quarantine, rollback
- **Warden** - Filesystem monitoring, governance, validation
- **Tests** - Unit, integration, property-based, stress tests
- **Docs** - README, architecture, configuration, AI guides
- **Fix** - Bug fixes, regressions