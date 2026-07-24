# DataWarden

> **Enterprise-Grade TUI Duplicate Finder & Data Governance Platform**  
> *Sichere Duplikat-Erkennung, intelligente Selektion, transaktionale Ausführung, KI-gestützte Governance*

---

## 🇩🇪 Deutsch

### Übersicht

DataWarden ist ein **Terminal-basiertes (TUI) Datenmanagement-Framework**, das weit über klassische Duplikat-Finder hinausgeht. Es wurde für **Enterprise-Anforderungen** entwickelt: maximale Datensicherheit, vollständige Nachvollziehbarkeit, lokale KI-Unterstützung und proaktive Dateisystem-Governance.

### Kern-Features

| Phase | Modul | Beschreibung |
|-------|-------|--------------|
| **1** | **High-Performance Indexer** | Asynchrones Scannen, xxHash (xxh3), Streaming-Hashes, JSONL-Split-Indizes, Savestate mit Ordner-Kompression |
| **2** | **Cross-Reference Engine** | Intra- & Inter-Ordner-Vergleich, In-Memory SQLite/Polars, Referenz-Schutz (Refs nie löschen) |
| **3** | **Smart Selector Pipeline** | Kaskadierende Filter (Pfad-Priorität, Namens-Hygiene, Artefakte, Tiefe, Zeitstempel), Presets, Builder-UI |
| **4** | **Execution & Snapshots** | Drei Modi: Audit (Dry-Run), Safe Move (Quarantäne + Undo), Hard Delete. Transaktionale Snapshots mit Retention |
| **5** | **Confirmation & AI** | N-Level Bestätigungen (Hotkeys), Ollama-Integration (Selection Assist, NL→Filter, Copilot), Zero-Trust Matrix |
| **6** | **Commander UI** | MC-Style 2-Pane (split/resize), Grep, Shell, Hex-Editor, externer Editor ($EDITOR), dynamische Layouts |
| **7** | **Metadata Notes** | Kontextsensitive Notizen an Pfade/UI-Elemente, Baum-Indikatoren `[📝 N]`, globales Archiv (F12) |
| **8** | **FileSystem Warden** | Watchdog-Daemon, 3-Säulen-Validierung (Rechte, Namenskonvention, Klassifizierung), LLM-Triage, Admin-Dashboard |

### Sicherheits-Architektur

```
┌─────────────────────────────────────────────────────────────┐
│  ZERO-TRUST DEFAULT (Level 0)                               │
│  ├─ KI darf NICHTS ändern, nur erklären                     │
│  ├─ Jede destruktive Aktion: Multi-Level Confirmation       │
│  ├─ Snapshots VOR jeder Schreib-Operation (Opt-In)          │
│  ├─ Quarantäne-Spiegelstruktur für sicheres Verschieben     │
│  └─ Audit-Log (JSONL) für JEDE Operation                    │
└─────────────────────────────────────────────────────────────┘
```

### Installation

```bash
# 1. Repository klonen
git clone https://github.com/yourorg/datawarden2
cd datawarden2

# 2. Interaktives Setup (erstellt venv, installiert deps)
./setup.sh
# → Fragt nach venv-Namen und Pfad
# → Erstellt .venv, installiert requirements.txt

# 3. Starten
./start.sh
# → Aktiviert venv, startet main.py, deaktiviert venv beim Exit

# 4. Updates
./update.sh
# → git pull + pip upgrade
```

### Anforderungen

- **Python 3.11+**
- **Linux** (primär; inotify, xattr, POSIX permissions)
- **Ollama** (optional, für lokale KI-Features)

### Quick Start

```bash
./start.sh
# 1. Menü: "Indexierung" → Ordner wählen, Filter setzen → Start
# 2. Nach Scan: "Vergleichen" → Referenz-Ordner markieren → Cross-Search
# 3. "Auto-Selektion" → Filter-Pipeline bauen → Preview
# 4. "Ausführen" → Modus wählen (Audit/Safe Move/Hard) → Bestätigen
# 5. Bei Safe Move: Quarantäne-Prüfung → bei Bedarf Undo (Snapshot)
```

### Projektstruktur

```
DataWarden/
├── main.py                 # Entry Point (Textual App)
├── requirements.txt        # Pinned dependencies
├── pyproject.toml          # Build config, tool config
├── setup.sh                # Interactive venv setup
├── start.sh                # Launcher (venv + app)
├── update.sh               # Updater (git + pip)
├── CHANGELOG.md            # Version history
├── README.md               # This file
├── locale/
│   ├── de_DE.lang          # German translations + descriptors
│   └── en_US.lang          # English translations + descriptors
├── core/                   # Backend Logic
│   ├── indexer.py          # Async scanner, hasher, JSONL writer
│   ├── ref_engine.py       # Cross-reference, duplicate groups
│   ├── selector.py         # Filter pipeline, built-in filters
│   ├── snapshot.py         # SnapshotManager, transactions
│   ├── telemetry.py        # Live metrics queue
│   ├── error_handler.py    # ErrorManager, user rules
│   ├── confirmation.py     # N-level confirmation engine
│   ├── ai_filter.py        # Ollama client, NL→Filter, Copilot
│   ├── policy.py           # DynamicPolicyManager, Zero-Trust
│   ├── notes.py            # MetadataNoteManager
│   └── warden.py           # FileSystemWarden, watchdog
└── ui/                     # Frontend (Textual)
    ├── app.tcss            # Global styles, CSS variables
    ├── workspace.py        # LayoutManager, dynamic splits
    ├── components.py       # CommanderTree, Panels, Widgets
    └── modals.py           # Confirmation, AI, Snapshot modals
```

### Lizenz

MIT License - siehe [LICENSE](LICENSE)

---

## 🇬🇧 English

### Overview

DataWarden is a **Terminal User Interface (TUI) data management framework** that goes far beyond traditional duplicate finders. Built for **enterprise requirements**: maximum data safety, full auditability, local AI assistance, and proactive filesystem governance.

### Core Features

| Phase | Module | Description |
|-------|--------|-------------|
| **1** | **High-Performance Indexer** | Async scanning, xxHash (xxh3), streaming hashes, JSONL split indexes, savestate with folder compression |
| **2** | **Cross-Reference Engine** | Intra- & Inter-folder comparison, In-memory SQLite/Polars, Reference protection (refs never deleted) |
| **3** | **Smart Selector Pipeline** | Cascading filters (Path Priority, Filename Hygiene, Artifacts, Depth, Timestamp), Presets, Builder UI |
| **4** | **Execution & Snapshots** | Three modes: Audit (Dry-Run), Safe Move (Quarantine + Undo), Hard Delete. Transactional snapshots with retention |
| **5** | **Confirmation & AI** | N-Level Confirmations (Hotkeys), Ollama Integration (Selection Assist, NL→Filter, Copilot), Zero-Trust Matrix |
| **6** | **Commander UI** | MC-Style 2-Pane (split/resize), Grep, Shell, Hex Editor, External Editor ($EDITOR), Dynamic Layouts |
| **7** | **Metadata Notes** | Context-sensitive notes on paths/UI elements, Tree indicators `[📝 N]`, Global Archive (F12) |
| **8** | **FileSystem Warden** | Watchdog daemon, 3-Pillar Validation (Perms, Naming, Classification), LLM Triage, Admin Dashboard |

### Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ZERO-TRUST DEFAULT (Level 0)                               │
│  ├─ AI may NOT change anything, only explain               │
│  ├─ Every destructive action: Multi-Level Confirmation      │
│  ├─ Snapshots BEFORE every write operation (Opt-In)         │
│  ├─ Quarantine mirror structure for safe moves              │
│  └─ Audit Log (JSONL) for EVERY operation                   │
└─────────────────────────────────────────────────────────────┘
```

### Installation

```bash
# 1. Clone repository
git clone https://github.com/yourorg/datawarden2
cd datawarden2

# 2. Interactive setup (creates venv, installs deps)
./setup.sh
# → Prompts for venv name and path
# → Creates .venv, installs requirements.txt

# 3. Launch
./start.sh
# → Activates venv, runs main.py, deactivates venv on exit

# 4. Updates
./update.sh
# → git pull + pip upgrade
```

### Requirements

- **Python 3.11+**
- **Linux** (primary; inotify, xattr, POSIX permissions)
- **Ollama** (optional, for local AI features)

### Quick Start

```bash
./start.sh
# 1. Menu: "Indexing" → Select folder, set filters → Start
# 2. After Scan: "Compare" → Mark Reference folders → Cross-Search
# 3. "Auto-Select" → Build Filter Pipeline → Preview
# 4. "Execute" → Choose Mode (Audit/Safe Move/Hard) → Confirm
# 5. On Safe Move: Quarantine Review → Undo via Snapshot if needed
```

### Project Structure

```
DataWarden/
├── main.py                 # Entry Point (Textual App)
├── requirements.txt        # Pinned dependencies
├── pyproject.toml          # Build config, tool config
├── setup.sh                # Interactive venv setup
├── start.sh                # Launcher (venv + app)
├── update.sh               # Updater (git + pip)
├── CHANGELOG.md            # Version history
├── README.md               # This file
├── locale/
│   ├── de_DE.lang          # German translations + descriptors
│   └── en_US.lang          # English translations + descriptors
├── core/                   # Backend Logic
│   ├── indexer.py          # Async scanner, hasher, JSONL writer
│   ├── ref_engine.py       # Cross-reference, duplicate groups
│   ├── selector.py         # Filter pipeline, built-in filters
│   ├── snapshot.py         # SnapshotManager, transactions
│   ├── telemetry.py        # Live metrics queue
│   ├── error_handler.py    # ErrorManager, user rules
│   ├── confirmation.py     # N-level confirmation engine
│   ├── ai_filter.py        # Ollama client, NL→Filter, Copilot
│   ├── policy.py           # DynamicPolicyManager, Zero-Trust
│   ├── notes.py            # MetadataNoteManager
│   └── warden.py           # FileSystemWarden, watchdog
└── ui/                     # Frontend (Textual)
    ├── app.tcss            # Global styles, CSS variables
    ├── workspace.py        # LayoutManager, dynamic splits
    ├── components.py       # CommanderTree, Panels, Widgets
    └── modals.py           # Confirmation, AI, Snapshot modals
```

### License

MIT License - see [LICENSE](LICENSE)