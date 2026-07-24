# DataWarden - Master Build Plan für opencode

> **Projektname:** DataWarden  
> **Version Start:** 0.05.10  
> **Ziel:** Enterprise-Grade TUI Duplikat-Finder & Data-Governance Plattform  
> **Tech Stack:** Python 3.11+, Textual (TUI), xxHash, aiofiles, watchdog, Ollama (LLM)  
> **Architektur:** Phasen-getrennt (Index → Compare → Select → Execute), Zero-Trust KI, Snapshot-Transaktionen

---

## Versionsschema
```
0.05.10 → 0.05.20 → ... → 0.05.90 → 0.10.10 → 0.10.20 ...
Major.Minor.Patch wobei Minor in 10er-Schritten, Patch in 10er-Schritten
Bei 100 → nächstes Minor, Minor zurück auf 10
```

---

## PHASE 0: Foundation & Project Setup (Woche 1)

### 0.1 Projekt-Struktur & Configs
- [ ] Verzeichnisbaum anlegen (`core/`, `ui/`, `locale/`, `indexes/`, `scripts/`)
- [ ] `requirements.txt` mit pinned Versions
- [ ] `pyproject.toml` für modernes Packaging (optional, aber empfohlen)
- [ ] `setup.sh` - interaktive venv-Erstellung (Name, Pfad abfragen)
- [ ] `start.sh` - venv aktivieren → main.py → deaktivieren
- [ ] `update.sh` - git pull + pip upgrade
- [ ] `.gitignore` (venv, indexes, __pycache__, *.log, .env)
- [ ] `CHANGELOG.md` initial mit Version 0.05.10
- [ ] `README.md` Skelett (DE/EN)

### 0.2 Locale-System (i18n)
- [ ] `locale/de_DE.lang` - Deutsche Strings mit Deskriptor-Kommentaren
- [ ] `locale/en_US.lang` - Englische Strings mit Deskriptor-Kommentaren
- [ ] `core/i18n.py` - Loader: entdeckt alle `.lang` Files, parst Key=Value + Kommentare
- [ ] Format: `# [Section]\n# Deskriptor\nkey = value`

### 0.3 Textual App-Gerüst
- [ ] `main.py` - Entry Point, `DataWardenApp` extends `App`
- [ ] `ui/app.tcss` - Base Styles, CSS Variables für Theming
- [ ] `ui/workspace.py` - `WorkspaceManager`: Grid-Layout, dynamic split/resize
- [ ] Header (Titel, Modus-Indikator), Footer (Status, Hotkeys), Body (Grid)
- [ ] Theme-Manager: Live-Reload TCSS, persist in `config/theme.json`

---

## PHASE 1: Indexer Core (Woche 2-3)

### 1.1 Hash & Scan Engine
- [ ] `core/indexer.py` - `Indexer` Klasse
- [ ] `HashEngine`: xxHash (xxh3_64), Streaming-Chunked für große Files
- [ ] `FileMetadata`: Dataclass (path, size, mtime, ctime, atime, mode, uid, gid, inode, hash, filetype, path_len, is_symlink, symlink_target, is_hardlink)
- [ ] Async Directory Walk mit `aiofiles` + `asyncio.Semaphore` für Concurrency Control
- [ ] Two-Pass: 1. Size-Bucket → 2. Hash nur bei Kollision

### 1.2 Filter & Config vor Hashing
- [ ] `ScanConfig` Dataclass: root_path, min_size, max_size, whitelist_ext, blacklist_ext, follow_symlinks (IGNORE|FOLLOW|RECORD_ONLY), track_hardlinks (bool), max_depth
- [ ] Symlink Protection: visited_paths Set pro Scan gegen Zirkel
- [ ] Hardlink Detection: Inode-Tracking, Option "als Duplikat behandeln"

### 1.3 Index Storage (JSONL + Splitting)
- [ ] `IndexWriter`: schreibt JSONL (eine Zeile = ein File Record)
- [ ] Auto-Split: ab `max_lines_per_file` (Default 50.000) oder `max_mb_per_file` (Default 100MB)
- [ ] Ordnerstruktur: `indexes/<sanitized_root_name>/part_001.jsonl`, `part_002.jsonl`...
- [ ] Manifest: `indexes/<root>/manifest.json` (parts, total_files, total_bytes, started_at, completed_at, config_hash)

### 1.4 Savestate & Resume
- [ ] `SavestateManager`: `savestate.json` pro Root
- [ ] States: `PENDING`, `SCANNING`, `HASHING`, `COMPLETED`, `FAILED`, `SKIPPED`
- [ ] Compression Logic: kompletter Ordner done → nur Ordner-Record, nicht jede Datei
- [ ] Crash-Safety: write savestate **nach** erfolgreicher File-Verarbeitung (append-only)
- [ ] Resume: lädt Savestate, skippt `COMPLETED` Ordner/Files, setzt bei `PENDING` an

### 1.5 Telemetry & Logging
- [ ] `core/telemetry.py` - `TelemetryEngine` (async Queue → UI)
- [ ] Metrics: files/sec, MB/sec, ETA, current_path, hash_count, skip_count, error_count
- [ ] Live-Log Widget im UI (Tree-basiert für Expand/Collapse)

### 1.6 Error Handling
- [ ] `core/error_handler.py` - `ErrorManager`
- [ ] Error Types: `PermissionDenied`, `FileLocked`, `CorruptMetadata`, `SymlinkLoop`, `IOError`
- [ ] User Rules per Error Type: `ASK`, `AUTO_SKIP_AND_LOG`, `RETRY_N_TIMES`
- [ ] Savestate记录错误原因，文件夹不标记为 COMPLETED

---

## PHASE 2: Cross-Reference Engine (Vergleichslogik) (Woche 3-4)

### 2.1 Index Loading & Query
- [ ] `core/ref_engine.py` - `CrossReferenceEngine`
- [ ] In-Memory Index: `sqlite3` (`:memory:`) oder `polars`/`pandas` für schnelle GroupBy
- [ ] Schema: hash, size, paths[], ref_flags[], metadata...
- [ ] Lazy Loading: nur Hash-Gruppen mit Count > 1 laden

### 2.2 Such-Modi
- [ ] **Intra-Folder**: Duplikate innerhalb eines Index (self-join auf hash)
- [ ] **Inter-Folder (Cross)**: Index A vs Index B vs Index C... (Union aller Hashes)
- [ ] **Reference Logic**: `is_reference=True` Pfade NIE als "zu löschen" markieren
- [ ] Matrix: Ref-Ordner × Non-Ref-Ordner Vergleiche

### 2.3 Result Model
- [ ] `DuplicateGroup`: hash, size, files[], ref_files[], non_ref_files[]
- [ ] `ComparisonResult`: groups[], stats (total_groups, total_wasted_bytes, ref_protected_count)

---

## PHASE 3: Smart Selector / Auto-Select Pipeline (Woche 4-5)

### 3.1 Filter Interface & Pipeline
- [ ] `core/selector.py` - `Filter` Protocol/ABC, `FilterPipeline` (List[Filter])
- [ ] Kaskadierend: Filter 1 entscheidet → bei Gleichstand Filter 2 → ...
- [ ] Jeder Filter liefert `Decision`: `KEEP`, `DELETE`, `SKIP` + `confidence` + `reason`

### 3.2 Built-in Filter
- [ ] `PathPriorityFilter`: Prefix-Match gegen Referenz-Pfade (höchste Prio gewinnt)
- [ ] `FilenameHygieneFilter`: Regex-Score (keine Leerzeichen, Umlaute, Sonderzeichen = besser)
- [ ] `ArtifactFilter`: Suffixes `_copy`, `(1)`, `-Kopie`, `_v2`, `~` → DELETE
- [ ] `PathDepthFilter`: Flachere Pfade bevorzugen (Original vs Backup-Tiefe)
- [ ] `TimestampFilter`: Newest/Oldest wählbar
- [ ] `OwnerFilter`: Bevorzuge bestimmte User/UID

### 3.3 Filter Builder UI
- [ ] TUI: Drag/Drop Reorder, Enable/Disable, Parameter pro Filter
- [ ] Presets speichern/laden (`config/filters/*.json`)

---

## PHASE 4: Execution Engine & Snapshots (Woche 5-6)

### 4.1 Execution Modes
- [ ] `core/execution.py` - `ExecutionEngine`
- [ ] **Mode 0: AUDIT** - Dry-Run, nur `audit.log` schreiben
- [ ] **Mode 1: SAFE_MOVE** - In Quarantäne verschieben (Spiegelstruktur)
- [ ] **Mode 2: HARD_DELETE** - Unwiderruflich löschen

### 4.2 Quarantäne & Mirror
- [ ] Quarantine Root: user-configurable (z.B. `~/.datawarden/quarantine/`)
- [ ] Mirror: `/quarantine/<orig_mount>/<relative_path>` → Herkunft rekonstruierbar
- [ ] Metadaten-Erhalt: mtime, atime, permissions, owner, xattrs

### 4.3 Snapshot Manager (Transaktional)
- [ ] `core/snapshot.py` - `SnapshotManager`
- [ ] `Snapshot`: id (timestamp), transaction_id, mappings[quarantine_path → original_path], size_bytes, filter_config_hash, created_at
- [ ] Storage: `indexes/snapshots/snap_<timestamp>.json` + `snap_<timestamp>.manifest`
- [ ] **Rollback**: `rollback_snapshot(sid)` → iteriert mappings rückwärts, `shutil.move` zurück
- [ ] **Retention**: Max GB oder Max Count → Pruning mit Bestätigung

### 4.4 Initial Snapshot Prompt
- [ ] Modal beim ersten Start: "Initial Snapshot erstellen? (Dauer/Speicher)..."
- [ ] Option: Überspringen (nicht empfohlen)

---

## PHASE 5: Confirmation Engine & Zero-Trust KI (Woche 6-7)

### 5.1 Multi-Level Confirmation
- [ ] `core/confirmation.py` - `ConfirmationEngine`
- [ ] Config: `levels: int` (0-5), `hotkeys_per_level: List[str]` (z.B. ["F10", "J", "Enter"])
- [ ] Sequential Modal: Stufe 1 → Hotkey 1 → Stufe 2 → Hotkey 2 → ...
- [ ] UI: Erklärtext "Mehr Stufen = weniger Undo-Speicher nötig"

### 5.2 Dynamic Policy Learning
- [ ] `DynamicPolicyManager`: Whitelist-Regeln aus User-Bestätigungen
- [ ] Modal Checkbox: "Diese Entscheidung merken für [Filter-Typ/Extension/Pfad]"
- [ ] Regel: `allow_auto:{filter_type}:{pattern}` → persist in `config/policies.json`
- [ ] Audit-Log: `[KI-AUTO-EXECUTE] ... (Grund: User-Regel vom DD.MM.YYYY)`

### 5.3 AI Filter Engine (Ollama)
- [ ] `core/ai_filter.py` - `AIFilterEngine`
- [ ] Async HTTP Client für Ollama (`/api/generate` oder `/api/chat`)
- [ ] **Selection Assist**: Bei uneindeutigen Gruppen → Prompt an LLM → JSON Decision
- [ ] **Filter Builder (NL → Pipeline)**: Freitext "Lösche Kopien mit (1) außer im Ref-Ordner" → JSON Pipeline
- [ ] **Copilot Panel**: System-Prompt mit Tool-Docs + Live-State JSON → Erklärungen + Apply-Vorschläge

### 5.4 Zero-Trust Matrix
- [ ] `GlobalTrustLevel`: 0=STRICT, 1=LAYOUT, 2=ASSISTED_LOGIC, 3=COLLABORATIVE
- [ ] `BundleGatekeepers`: pro Funktionsbündel (UI, Filter, Files, Governance) Toggle
- [ ] Matrix Check: `level >= required AND bundle_enabled`
- [ ] Deaktivierung Modal: Rotes Warn-Modal, Tippe `RELAX_TRUST` zur Bestätigung

---

## PHASE 6: TUI - Commander & Workspace (Woche 7-8)

### 6.1 Dynamic Layout System
- [ ] `ui/workspace.py` - `LayoutManager`
- [ ] Grid: `HorizontalSplit` / `VerticalSplit` Nodes (Binary Tree)
- [ ] Resize: Mouse-Drag auf Borders + Hotkeys (Ctrl+Arrows)
- [ ] Pane Types: `DirectoryTree`, `DuplicateTable`, `LogPanel`, `DescriptionPane`, `SettingsPane`, `FilterPane`, `ShellPane`, `GrepPane`, `HexPane`, `NotePane`, `WardenDashboard`

### 6.2 File Commander (MC-Style)
- [ ] `ui/components.py` - `CommanderTree` extends `DirectoryTree`
- [ ] Keys: F5 Copy, F6 Move, F7 Mkdir, F8 Delete, F4 Edit ($EDITOR), Enter CD
- [ ] External Editor: `subprocess.run([editor, path])` → App suspend/resume
- [ ] Selection: Space/Insert, Multi-Select

### 6.3 Grep Panel
- [ ] `ui/components.py` - `GrepPanel`
- [ ] Async ripgrep (`rg`) oder Python `aiofiles` Walk + Regex
- [ ] Results: Click → öffnet File im Commander/Editor

### 6.4 Shell Input Line
- [ ] Footer-Bereich: `ShellInput` Widget
- [ ] History (Pfeil hoch/runter), Tab-Completion (Pfade)
- [ ] Execution: `asyncio.create_subprocess_shell` → Output in `CLIPanel` (Collapsible)

### 6.5 Hex Editor & Debug
- [ ] `ui/components.py` - `HexDebugPanel`
- [ ] Hex Dump + ASCII Spalte, Byte-Edit, Magic-Bytes Highlight (ELF, PE, PDF, PNG, ZIP...)
- [ ] Navigation: Offset springen, Search Hex/String

---

## PHASE 7: Metadata Notes & Sticky System (Woche 8)

### 7.1 Note Manager
- [ ] `core/notes.py` - `MetadataNoteManager`
- [ ] Storage: `.datawarden/notes/` (JSON per Note: id, target_path, target_type, content, created, modified, tags)
- [ ] Index: `notes_index.json` (path → [note_ids]) für schnelle Baum-Indikatoren

### 7.2 UI Integration
- [ ] Tree Indicator: `📁 Projekt [📝 3]` → Click/Enter → `NotePane` zeigt Inhalt
- [ ] Auto-Show: Fokus auf Pfad → NotePane aktualisiert sich reaktiv
- [ ] Global Archive: F12 → `GlobalNoteArchive` (Suchbar, Deep-Link zum Pfad)

---

## PHASE 8: FileSystem Warden (Governance Daemon) (Woche 9-10)

### 8.1 Watchdog Daemon
- [ ] `core/warden.py` - `FileSystemWarden` (läuft im Hintergrund / separater Process)
- [ ] `watchdog` Library: `on_created`, `on_moved_to` Events
- [ ] Config: `WardenZone` (path, permissions_mask, naming_regex, classification_rules)

### 8.2 Three-Pillar Validation
- [ ] **Permissions**: Auto-fix `chmod` auf Zone-Standard (z.B. 640)
- [ ] **Naming**: Regex-Mismatch → LLM Korrekturvorschlag generieren
- [ ] **Classification**: Extension/Content vs. Folder Purpose → Move-Vorschlag

### 8.3 Admin Dashboard & Triage
- [ ] `ui/components.py` - `WardenDashboardPanel`
- [ ] Incident Stream: Queue → TUI Panel (farblich: Rot=Kritisch, Orange=Warnung)
- [ ] Actions: [Auto-Fix Anwenden] [LLM-Vorschlag Prüfen] [Ignorieren] [Manuell]
- [ ] **Query Line**: Freitext "Wo ist die Tabelle mit 'Umsatz Q2' von letzter Woche?"
    - Filter: Time Range + Content Search (Index/Grep Cache) + LLM Intent Parsing
    - Result → Jump to Commander

---

## PHASE 9: Polish, Tests, Docs (Woche 10-11)

### 9.1 Testing
- [ ] Unit Tests: HashEngine, Filters, Snapshot Rollback, Savestate Resume
- [ ] Integration Tests: Full Scan → Compare → Select → Execute (Audit Mode)
- [ ] Property-based Tests (hypothesis): Filter Pipeline Determinismus
- [ ] Stress Test: 100k+ Files, Deep Nesting, Symlinks, Hardlinks

### 9.2 Documentation
- [ ] `README.md` Vollständig (DE/EN): Installation, Workflow, Screenshots (ASCII), Config Reference
- [ ] `docs/architecture.md` - Modul-Diagramme, Datenflüsse
- [ ] `docs/configuration.md` - Alle Settings erklärt
- [ ] `docs/ai-integration.md` - Ollama Setup, Prompt Engineering

### 9.3 Packaging & Release
- [ ] `pip install -e .` Support
- [ ] GitHub Actions: Lint (ruff), Typecheck (mypy), Tests, Build
- [ ] Release Script: Version bump → Changelog Entry → Tag → Build

---

## Abhängigkeiten (Critical Path)

```
Phase 0
  └─ Phase 1 (Indexer)
       ├─ Phase 2 (Ref Engine) ← braucht Index Format
       │    └─ Phase 3 (Selector) ← braucht Duplicate Groups
       │         └─ Phase 4 (Execution) ← braucht Selection
       │              └─ Phase 5 (Confirmation/AI) ← wraps Execution
       ├─ Phase 6 (Commander UI) ← parallel zu 2-4, braucht Index/Selection Display
       ├─ Phase 7 (Notes) ← parallel, braucht UI Framework
       └─ Phase 8 (Warden) ← unabhängig, braucht Index + LLM + Config
```

---

## Meilensteine & Versionen

| Version | Meilenstein | Ziel-Datum |
|---------|-------------|------------|
| 0.05.10 | Plan Finalisiert | Tag 0 |
| 0.05.20 | Phase 0-1: Project Setup + Indexer Core | Woche 2 |
| 0.05.30 | Phase 2: Cross-Reference Engine | Woche 3 |
| 0.05.40 | Phase 3: Smart Selector Pipeline | Woche 4 |
| 0.05.50 | Phase 4: Execution + Snapshots | Woche 5 |
| 0.05.60 | Phase 5: Confirmation Engine + AI Filter | Woche 6 |
| 0.05.70 | Phase 6: Commander UI + Workspace | Woche 8 |
| 0.05.80 | Phase 7: Notes System | Woche 8 |
| 0.05.90 | Phase 8: FileSystem Warden | Woche 10 |
| 0.10.10 | Phase 9: Tests, Docs, Release Ready | Woche 11 |

---

## Risiken & Mitigation

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Textual Layout-Complexity (Nested Splits) | Hoch | Hoch | Early Prototype in Phase 0.3, Fallback: Fixed 2-Pane |
| LLM Latency (lokale CPU) | Mittel | Mittel | Async Queue, Token Streaming, Cache, Warnung im UI |
| Watchdog Race Conditions (chmod + rename) | Mittel | Hoch | File-Lock (fcntl/portalocker) pro Pfad, Idempotente Ops |
| JSONL Splitting Korruption bei Crash | Niedrig | Hoch | Append-Only, fsync(), Manifest mit Checksums |
| Massive Memory bei In-Memory Index | Mittel | Mittel | SQLite `:memory:` + Indizes, Chunked Loading, Polars Streaming |

---

## Offene Entscheidungen (für opencode Agent)

- [ ] **LLM Backend Default**: Ollama (HTTP) vs. llama-cpp-python (In-Process) → Empfehlung: Ollama (einfacher, Modell-Wechsel)
- [ ] **Primäre Plattform**: Linux-only (inotify, xattr, POSIX) vs. Cross-Platform (watchdog abstraction) → Empfehlung: Linux-first, watchdog für Portabilität
- [ ] **DB für Index**: sqlite3 (stdlib) vs. polars (Speed) vs. duckdb (Analytics) → Empfehlung: sqlite3 (keine Deps, ausreichend für GroupBy)
- [ ] **Config Format**: TOML vs. JSON vs. YAML → Empfehlung: TOML (human-readable, typed, Python stdlib seit 3.11)

---

## Nächster Schritt für opencode

**Starte mit Phase 0.1-0.3** - das Fundament muss stehen, bevor Logik gebaut wird. Jede Phase = ein opencode Task mit eigenem Context. Nach jeder Phase: Tests laufen lassen, Changelog updaten, Version bumpen.