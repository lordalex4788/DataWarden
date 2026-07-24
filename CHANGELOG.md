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
* **Telemetry** (`core/telemetry.py`): Async TelemetryEngine with subscriber queues, rolling speed/ETA calculation
* **Error Handler** (`core/error_handler.py`): ErrorManager with ASK/AUTO_SKIP/RETRY rules, ErrorHandler integration with savestate

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

## [0.05.50] - 2026-07-24 18:30:00

### Core
* **Confirmation Engine** (`core/confirmation.py`): Multi-level confirmation system for destructive operations
  * `ConfirmationEngine`: Configurable N-level confirmation chains with custom hotkeys
  * `ConfirmationManager`: Mode-specific configs (audit=0, safe_move=2, hard_delete=3 levels)
  * `ConfirmationProfiles`: Pre-built profiles (minimal, standard, strict, paranoid, custom)
  * Async callbacks for Textual UI integration (input/display)
* **Dynamic Policy Manager** (`core/policy.py`): Zero-Trust Matrix with learning
  * `TrustLevel` enum: STRICT_ZERO_TRUST (0) → LAYOUT_ONLY (1) → ASSISTED_LOGIC (2) → COLLABORATIVE_EXECUTE (3)
  * `BundleGatekeeper`: Per-bundle AI permissions (UI_LAYOUT, FILTERS_PIPELINES, FILE_METADATA_SORTING, GOVERNANCE_WARDEN)
  * `LearnedRule`: Dynamic whitelist from user confirmations ("Remember this decision")
  * `DynamicPolicyManager`: Persists to `config/policies.json`, matrix check `can_ai_act()`
* **AI Filter Engine** (`core/ai_filter.py`): Local LLM via Ollama
  * `OllamaClient`: Async HTTP client for `/api/generate` and `/api/chat`
  * `AIFilterEngine`: Three modes - Selection Assist (tie-breaking), NL→Filter Builder, Copilot Panel
  * `AIConfig`: Model, timeout, temperature, feature flags per mode
  * System prompts enforce Zero-Trust: AI proposes, never executes autonomously

### Tests
* **Confirmation** (`tests/core/test_confirmation.py`): 25 tests covering config validation, engine callbacks, manager modes, profiles, fallback
* **Policy** (`tests/core/test_policy.py`): 22 tests covering trust levels, gatekeepers, learned rules, persistence, matrix checks
* **AI Filter** (`tests/core/test_ai_filter.py`): 18 tests covering config, client, selection assist, NL builder, copilot, error handling

### Fixes
* **Confirmation Engine**: Fixed audit mode (levels=0) auto-confirm without prompting
* **Policy Manager**: Fixed serialization of `LearnedRule` dataclass without `asdict`
* **AI Filter Tests**: Fixed OllamaClient async context manager mocking for pytest-asyncio

---

## [0.05.40] - 2026-07-24 17:45:00

### Core
* **Execution Engine** (`core/execution.py`): Three-mode execution engine with audit/safe-move/hard-delete
  * **Audit Mode**: Dry-run simulation, logs to audit.log only
  * **Safe Move Mode**: Moves files to quarantine preserving directory structure, with full metadata preservation (timestamps, permissions, owner, xattrs)
  * **Hard Delete Mode**: Permanent deletion
  * Mirror quarantine structure: `/quarantine/<mount_point>/<relative_path>` for traceability
* **Snapshot Manager** (`core/snapshot.py`): Transactional snapshot system
  * Unique snapshot IDs with timestamp + UUID
  * Bidirectional mapping: quarantine_path ↔ original_path
  * Rollback mechanism: restores files with original metadata
  * Retention policies: max GB and max count with auto-pruning
  * Quarantine usage tracking
* **Initial Snapshot Prompt**: First-run modal for baseline snapshot creation
* **Tests** (`tests/core/test_execution_snapshot.py`): 24 comprehensive tests covering all execution modes, snapshot operations, rollback, retention, and initial snapshot prompt

---

## [0.05.30] - 2026-07-24 16:30:00

### Core
* **Selector** (`core/selector.py`): Filter protocol + pipeline implementation with cascading logic
  * 6 built-in filters: PathPriorityFilter (reference path preference), FilenameHygieneFilter (clean filename scoring), ArtifactFilter (detects _copy, (1), _v2, ~, .bak), PathDepthFilter (shallower paths), TimestampFilter (newest/oldest), OwnerFilter (UID/GID preference)
  * FilterPipeline: cascading evaluation (first decisive wins), JSON serialization, preset save/load
  * SelectorEngine: batch processing across all duplicate groups
  * FILTER_REGISTRY for dynamic filter loading
* **Tests** (`tests/core/test_selector.py`): 36 comprehensive unit tests covering all filters, pipeline behavior, serialization, property-based determinism

### Tests
* Unit tests for all selector components passing (59 total tests across core modules)

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

## [0.05.60] - 2026-07-24 19:45:00

### UI
* **Theme System** (`ui/workspace.py`): Fixed ThemeManager.apply_theme() to generate valid TCSS with actual CSS property values instead of invalid custom properties. All 4 built-in themes (dark, light, nord, dracula) now apply correctly with live reload.
* **Main App** (`main.py`): Fixed unused imports, replaced deprecated `Input(multiline=True)` with `TextArea` widget for notes content field.
* **Linting**: Fixed all ruff violations (unused imports, import sorting, loop variable naming, trailing newline).

### Core
* **ThemeManager**: Complete rewrite of apply_theme() to generate full TCSS stylesheet with proper property mapping for all UI components (Screen, Sidebar, Forms, DataTables, Trees, Modals, Footer, Progress bars, etc.).