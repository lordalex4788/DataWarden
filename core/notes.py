#!/usr/bin/env python3
"""
DataWarden - Metadata Notes System (STUB)
Context-sensitive sticky notes attached to paths/UI elements.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class Note:
    """A single metadata note."""
    id: str
    target_path: str              # Absolute path or UI component ID
    target_type: str              # "path", "file", "ui_component", "menu_item"
    content: str
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    author: str = "user"
    color: str = "yellow"         # yellow, blue, green, red, purple
    pinned: bool = False          # Show in global archive
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Note':
        return cls(**data)


class MetadataNoteManager:
    """
    Manages notes attached to filesystem paths and UI elements.
    Notes stored in .datawarden/notes/ as JSON files.
    """
    
    def __init__(self, notes_dir: Path):
        self.notes_dir = Path(notes_dir)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.notes_dir / "index.json"
        self._index: Dict[str, List[str]] = {}  # target_path -> [note_ids]
        self._notes: Dict[str, Note] = {}       # note_id -> Note
        self._load_index()
    
    def _load_index(self) -> None:
        """Load index and all notes."""
        if not self.index_file.exists():
            return
        
        try:
            index_data = json.loads(self.index_file.read_text())
            self._index = index_data.get("index", {})
            
            # Load all note files
            for note_file in self.notes_dir.glob("note_*.json"):
                note_id = note_file.stem[5:]  # Remove "note_"
                try:
                    note = Note.from_dict(json.loads(note_file.read_text()))
                    self._notes[note_id] = note
                except Exception:
                    pass
        except Exception:
            self._index = {}
            self._notes = {}
    
    def _save_index(self) -> None:
        """Save index to disk."""
        data = {"index": self._index}
        self.index_file.write_text(json.dumps(data, indent=2))
    
    def _save_note(self, note: Note) -> None:
        """Save individual note file."""
        note_file = self.notes_dir / f"note_{note.id}.json"
        note_file.write_text(json.dumps(note.to_dict(), indent=2))
    
    # --- CRUD Operations ---
    
    def create_note(self, 
                   target_path: str,
                   content: str,
                   target_type: str = "path",
                   tags: List[str] = None,
                   color: str = "yellow") -> Note:
        """Create a new note."""
        note_id = f"{int(time.time() * 1000)}"
        note = Note(
            id=note_id,
            target_path=target_path,
            target_type=target_type,
            content=content,
            tags=tags or [],
            color=color
        )
        
        self._notes[note_id] = note
        self._index.setdefault(target_path, []).append(note_id)
        self._save_note(note)
        self._save_index()
        
        return note
    
    def get_note(self, note_id: str) -> Optional[Note]:
        """Get note by ID."""
        return self._notes.get(note_id)
    
    def get_notes_for_path(self, path: str) -> List[Note]:
        """Get all notes attached to a path."""
        note_ids = self._index.get(path, [])
        return [self._notes[nid] for nid in note_ids if nid in self._notes]
    
    def get_notes_for_prefix(self, prefix: str) -> List[Note]:
        """Get notes for path and all sub-paths."""
        results = []
        for p, note_ids in self._index.items():
            if p == prefix or p.startswith(prefix.rstrip('/') + '/'):
                for nid in note_ids:
                    if nid in self._notes:
                        results.append(self._notes[nid])
        return results
    
    def update_note(self, note_id: str, **kwargs) -> bool:
        """Update note fields."""
        note = self._notes.get(note_id)
        if not note:
            return False
        
        for key, value in kwargs.items():
            if hasattr(note, key):
                setattr(note, key, value)
        
        note.modified_at = time.time()
        self._save_note(note)
        return True
    
    def delete_note(self, note_id: str) -> bool:
        """Delete a note."""
        note = self._notes.get(note_id)
        if not note:
            return False
        
        # Remove from index
        if note.target_path in self._index:
            if note_id in self._index[note.target_path]:
                self._index[note.target_path].remove(note_id)
            if not self._index[note.target_path]:
                del self._index[note.target_path]
        
        # Delete note file
        note_file = self.notes_dir / f"note_{note_id}.json"
        if note_file.exists():
            note_file.unlink()
        
        del self._notes[note_id]
        self._save_index()
        return True
    
    def search_notes(self, query: str, tags: List[str] = None) -> List[Note]:
        """Full-text search across all notes."""
        query_lower = query.lower()
        results = []
        
        for note in self._notes.values():
            # Check content match
            if query_lower in note.content.lower():
                # Check tag filter
                if tags and not any(t in note.tags for t in tags):
                    continue
                results.append(note)
        
        # Sort by modified time, newest first
        results.sort(key=lambda n: n.modified_at, reverse=True)
        return results
    
    # --- Tree Indicators ---
    
    def get_note_count_for_path(self, path: str) -> int:
        """Get note count for tree indicator [📝 N]."""
        return len(self.get_notes_for_path(path))
    
    def get_subtree_note_count(self, path: str) -> int:
        """Get total note count for path and all children."""
        return len(self.get_notes_for_prefix(path))
    
    # --- Global Archive ---
    
    def get_all_notes(self, include_pinned_only: bool = False) -> List[Note]:
        """Get all notes for global archive (F12)."""
        notes = list(self._notes.values())
        if include_pinned_only:
            notes = [n for n in notes if n.pinned]
        notes.sort(key=lambda n: n.modified_at, reverse=True)
        return notes
    
    def get_note_statistics(self) -> Dict[str, Any]:
        """Get statistics for dashboard."""
        total = len(self._notes)
        by_type = {}
        by_color = {}
        pinned = 0
        
        for note in self._notes.values():
            by_type[note.target_type] = by_type.get(note.target_type, 0) + 1
            by_color[note.color] = by_color.get(note.color, 0) + 1
            if note.pinned:
                pinned += 1
        
        return {
            "total_notes": total,
            "pinned_notes": pinned,
            "by_target_type": by_type,
            "by_color": by_color,
            "unique_paths": len(self._index)
        }


# Path normalization for consistent targeting
def normalize_target_path(path: str) -> str:
    """Normalize path for consistent note targeting."""
    return str(Path(path).resolve())


def get_tree_indicator(note_manager: MetadataNoteManager, path: str) -> str:
    """Get tree indicator string like '[📝 3]'."""
    count = note_manager.get_subtree_note_count(path)
    if count > 0:
        return f" [📝 {count}]"
    return ""