# AGENTS.md - opencode Agent Instructions for DataWarden2

## Purpose
This file defines how opencode agents MUST operate when implementing the DataWarden2 project. Every agent invocation MUST follow these rules strictly.

---

## Core Principles

### 1. Single Source of Truth
- **PLAN.md** is the authoritative specification. No deviation without explicit user approval.
- **CHANGELOG.md** must be updated with EVERY change (version bump + timestamp + description).
- Version scheme: `0.05.10` → `0.05.20` → ... → `0.05.90` → `0.10.10`

### 2. Zero Trust Development
- Every modification must be verified by tests before considering "done"
- No assumptions about existing code - always read first
- Security-first: Audit mode default, explicit confirmations for writes

### 3. Modular Phase Execution
- Implement ONE phase at a time (see PLAN.md phases)
- Each phase = separate agent task with clear deliverables
- Phase complete only when: tests pass + lint clean + changelog updated

---

## Agent Workflow

### Before Starting ANY Task
```bash
# 1. Read current state
cat PLAN.md          # Find current phase
cat CHANGELOG.md     # Verify last version
git status           # Check for uncommitted changes
```

### During Implementation
1. **Read** all relevant existing files first
2. **Write** implementation following PLAN.md specs exactly
3. **Test** - run pytest (or project test command)
4. **Lint** - run ruff/mypy (or project lint command)
5. **Update CHANGELOG.md** with new version entry
6. **Commit** if user requested

### After Completing a Phase
- Verify all phase deliverables exist
- Run full test suite
- Update CHANGELOG.md with version bump
- Report completion with summary

---

## Required Skills & Tools

### Mandatory Skills (load via `skill` tool)
- **gepeto** - For building 1-click launchers, Pinokio integration
- **pinokio** - For app discovery and management

### Required Python Dependencies (from PLAN.md)
```txt
textual>=0.47.1
rich>=13.7.0
xxhash>=3.4.1
aiofiles>=23.2.1
watchdog>=3.0.0
```

### Testing & Quality
- `pytest` for unit/integration tests
- `ruff` for linting (fast, replaces flake8+isort)
- `mypy` for type checking
- `hypothesis` for property-based tests (filters, snapshot logic)

---

## Phase Definitions & Agent Tasks

### Phase 0: Project Skeleton (Version 0.05.20)
**Agent Task**: `setup_project_skeleton`
- Create directory structure per PLAN.md
- `requirements.txt` with pinned versions
- `pyproject.toml` (build-system, tool config)
- `setup.sh` / `start.sh` / `update.sh` scripts
- `main.py` entry point (Textual App skeleton)
- `locale/de_DE.lang` + `locale/en_US.lang` with descriptor comments
- Initial `README.md` structure (DE/EN)
- `CHANGELOG.md` with 0.05.10 entry

### Phase 1: Indexer Core (Version 0.05.30)
**Agent Task**: `implement_indexer_core`
- `core/indexer.py` - Async scanner with xxHash (blake3/xxh3)
- Filetype filtering (whitelist/blacklist/glob)
- Min/max size filtering
- Metadata extraction (stat, xattrs, owner, perms)
- JSONL writer with splitting (lines + size thresholds)
- `core/savestate.py` - SavestateManager (compression logic)
- `core/telemetry.py` - TelemetryEngine (async queue → UI)
- `core/error_handler.py` - ErrorManager (ASK/AUTO_SKIP rules)
- Symlink handling (IGNORE/FOLLOW/RECORD_ONLY + loop detection)
- Hardlink detection (inode tracking)
- Unit tests for all indexer components

### Phase 2: Cross-Reference Engine (Version 0.05.40)
**Agent Task**: `implement_ref_engine`
- `core/ref_engine.py` - CrossReferenceEngine
- In-memory SQLite / Polars loading
- Intra-folder (self-join) and Inter-folder (union) modes
- Reference logic enforcement (ref paths never marked for deletion)
- DuplicateGroup model + ComparisonResult
- Performance: lazy loading, hash-group filtering

### Phase 3: Smart Selector Pipeline (Version 0.05.50)
**Agent Task**: `implement_selector_pipeline`
- `core/selector.py` - Filter protocol, FilterPipeline
- Built-in filters: PathPriority, FilenameHygiene, Artifact, PathDepth, Timestamp, Owner
- Kascade logic (tie-breaking)
- Filter Builder UI integration points
- Preset system (save/load JSON)
- Property-based tests for determinism

### Phase 4: Execution Engine & Snapshots (Version 0.05.60)
**Agent Task**: `implement_execution_snapshots`
- `core/execution.py` - ExecutionEngine (AUDIT/SAFE_MOVE/HARD_DELETE)
- `core/snapshot.py` - SnapshotManager (transactional, rollback, retention)
- Quarantine mirror structure preservation
- Metadata preservation (timestamps, perms, xattrs, owner)
- Initial Snapshot Prompt Modal
- Audit log format (structured JSONL)

### Phase 5: Confirmation Engine & AI Integration (Version 0.05.70)
**Agent Task**: `implement_confirmation_ai`
- `core/confirmation.py` - Multi-level ConfirmationEngine (N-level, custom hotkeys)
- `core/ai_filter.py` - AIFilterEngine (Ollama async client)
  - Selection Assist (LLM decides on tie)
  - NL → Filter Pipeline Builder
  - Copilot Panel (context-aware help)
- `core/policy.py` - DynamicPolicyManager (learned whitelists)
- Zero-Trust Matrix: GlobalTrustLevel (0-3) + BundleGatekeepers
- RELAX_TRUST modal with typed confirmation

### Phase 6: Commander UI & Workspace (Version 0.05.80)
**Agent Task**: `implement_commander_ui`
- `ui/workspace.py` - LayoutManager (binary split tree, resize, persist)
- `ui/components.py` - CommanderTree (MC keys), DuplicateTable, LogPanel (Tree), DescriptionPane, SettingsPane, FilterPane, ShellPane, GrepPanel, HexDebugPanel, NotePane, WardenDashboard
- `ui/app.tcss` - Theming system (live reload, user colors)
- `ui/modals.py` - Confirmation modals, AI suggestions, Initial Snapshot prompt
- Keybindings: F5/F6/F7/F8/F4, Ctrl+Arrows, F12 (Notes), etc.

### Phase 7: Metadata Notes System (Version 0.05.85)
**Agent Task**: `implement_notes_system`
- `core/notes.py` - MetadataNoteManager (.datawarden/notes/)
- Tree indicators `[📝 N]` in CommanderTree
- Reactive DescriptionPane/StickyNotePane
- GlobalNoteArchive (F12) with search + deep-link

### Phase 8: FileSystem Warden (Version 0.05.90)
**Agent Task**: `implement_warden`
- `core/warden.py` - FileSystemWarden (watchdog daemon)
- WardenZone config (permissions, naming regex, classification)
- Three-pillar validation (perms auto-fix, naming LLM, classification)
- WardenDashboardPanel with incident stream
- Natural Language Query Line (time + content search → jump)

### Phase 9: Polish, Tests, Release (Version 0.10.10)
**Agent Task**: `finalize_release`
- Full test coverage (≥80%)
- Integration test: full workflow (scan → compare → select → execute → rollback)
- Stress tests (100k+ files)
- Documentation complete (README, ARCHITECTURE, CONFIG, AI)
- Packaging (pip install -e .)
- CI/CD (GitHub Actions: ruff, mypy, pytest, build)

---

## Coding Standards

### Python Style
- **Type hints mandatory** - all functions, classes, methods
- **Google-style docstrings** for public APIs
- **Async-first** - use `asyncio`, `aiofiles`, `async` Textual handlers
- **Dataclasses/Pydantic** for config/models (immutable where possible)
- **Protocol/ABC** for plugin interfaces (Filters, ErrorHandlers)

### Textual UI Patterns
- Compose over inherit - small Widgets, compose in Containers
- Reactive attributes (`reactive`) for auto-refresh
- Messages for cross-widget communication (`self.post_message`)
- CSS (TCSS) for all styling - no inline styles
- `on_mount`, `on_unmount` for lifecycle
- `watch_<attr>` for reactive side-effects

### File Format: `.lang` (Localization)
```
# [Section Name]
# Descriptor: Context for translators - where this appears and what it does
key = "Translated text with {placeholders}"
```
- One file per locale: `locale/de_DE.lang`, `locale/en_US.lang`
- Keys must be identical across files
- Descriptors (comments starting with `#`) mandatory for every key

### Savestate Format (JSON)
```json
{
  "version": "0.05.30",
  "root_path": "/mnt/data",
  "config_hash": "sha256...",
  "started_at": "2026-07-11T13:53:00Z",
  "folders": {
    "/mnt/data/photos": {"status": "COMPLETED", "file_count": 1523, "completed_at": "..."},
    "/mnt/data/docs": {"status": "SCANNING", "files_done": 45, "files_total": 100, "current_file": "..."}
  },
  "errors": [
    {"path": "...", "error": "PermissionDenied", "action": "SKIPPED", "timestamp": "..."}
  ]
}
```

### Index Format (JSONL)
```json
{"hash": "xxh3...", "size": 1024, "path": "/mnt/data/a.txt", "mtime": 1234567890, "mode": 33188, "uid": 1000, "gid": 1000, "inode": 12345, "is_ref": false, "symlink_target": null}
```
One line per file. Split files named `part_001.jsonl`, `part_002.jsonl`...

---

## Changelog Format (MANDATORY)

```markdown
# Changelog

## [0.05.20] - 2026-07-11 14:30:00
* **Project Setup:** Directory structure, requirements, scripts, locale files
* **Config:** pyproject.toml with ruff/mypy/pytest config
* **Entry:** main.py with Textual App skeleton
```

**Rules:**
- Every agent task completion = ONE changelog entry
- Version bump per PLAN.md scheme
- Timestamp: ISO 8601 (YYYY-MM-DD HH:MM:SS)
- Categories: **Setup**, **Core**, **UI**, **AI**, **Snapshot**, **Warden**, **Tests**, **Docs**, **Fix**
- One bullet per logical change

---

## Git Discipline

### Commit Message Format
```
<type>(<scope>): <short description>

<longer description if needed>

Version: 0.05.20
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`

### Branching
- `main` = stable releases only
- Feature branches: `phase-<num>-<short-desc>` (e.g., `phase-1-indexer-core`)
- PR required for merge to main

---

## Testing Requirements

### Unit Tests (per module)
- `tests/core/test_indexer.py`
- `tests/core/test_ref_engine.py`
- `tests/core/test_selector.py`
- `tests/core/test_snapshot.py`
- `tests/core/test_confirmation.py`
- `tests/core/test_ai_filter.py`
- `tests/core/test_warden.py`
- `tests/core/test_notes.py`

### Integration Tests
- `tests/integration/test_full_workflow.py` - scan → compare → select → execute → rollback

### Property Tests (Hypothesis)
- Filter pipeline determinism
- Snapshot rollback idempotency
- Savestate resume consistency

### Coverage Target
- **≥ 80%** overall
- **100%** for: SnapshotManager, ConfirmationEngine, SavestateManager

---

## Agent Invocation Template

When user asks "implement phase X", invoke agent with:

```python
Task(
    description="Implement Phase X: <Phase Name>",
    prompt=f"""
    Implement Phase X per PLAN.md and AGENTS.md.
    
    Current version: <read from CHANGELOG.md>
    Target version: <next version per scheme>
    
    Deliverables:
    - <List from PLAN.md phase section>
    - All tests passing
    - Ruff + MyPy clean
    - CHANGELOG.md updated with new version entry
    
    Constraints:
    - Follow PLAN.md specs exactly
    - Type hints everywhere
    - Google docstrings for public APIs
    - Async-first implementation
    - No hardcoded paths - use config
    - Security: Audit mode default
    """,
    subagent_type="general"
)
```

---

## Safety Checks (Agent Must Verify)

Before reporting phase complete:
- [ ] `pytest tests/ -x` passes
- [ ] `ruff check .` passes
- [ ] `mypy .` passes (or project config)
- [ ] CHANGELOG.md has new entry with correct version
- [ ] All deliverables from PLAN.md phase exist
- [ ] No `TODO`/`FIXME` in production code (only in tests)
- [ ] Locale files have all keys (de/en parity)

---

## Escalation

If agent encounters:
- **Ambiguity in PLAN.md** → STOP, ask user for clarification
- **Technical blocker** → Report with options, ask for direction
- **Scope creep request** → Defer to next phase, note in CHANGELOG as "Deferred"
- **Test failure unexplained** → Debug, if >30min → ask user