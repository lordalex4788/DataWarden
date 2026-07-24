#!/usr/bin/env python3
"""
DataWarden - AI Filter Engine (STUB)
Local LLM integration via Ollama for selection assist, NL->Filter, Copilot.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import aiohttp

from core.models import DuplicateGroup, DuplicateFile


class AIMode(Enum):
    DISABLED = "disabled"
    SELECTION_ASSIST = "selection_assist"    # LLM decides ties
    NL_FILTER_BUILDER = "nl_filter_builder"  # Natural language -> filter pipeline
    COPILOT = "copilot"                      # Context-aware help panel


@dataclass
class AIConfig:
    enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    timeout_seconds: float = 30.0
    max_tokens: int = 2048
    temperature: float = 0.1
    
    # Feature flags
    selection_assist: bool = True
    nl_filter_builder: bool = True
    copilot: bool = True
    
    # Trust level (0-3)
    trust_level: int = 0


@dataclass
class SelectionContext:
    """Context for LLM selection decision."""
    group_hash: str
    file_size: int
    files: List[Dict]  # Each: path, name, mtime, is_ref, depth, hygiene_score
    
    def to_prompt(self) -> str:
        file_desc = []
        for i, f in enumerate(self.files):
            ref_marker = " [REF]" if f.get('is_ref') else ""
            file_desc.append(
                f"  {i+1}. {f['name']}\n"
                f"     Path: {f['path']}{ref_marker}\n"
                f"     Modified: {f.get('mtime', 'N/A')}\n"
                f"     Depth: {f.get('depth', 0)}\n"
                f"     Hygiene Score: {f.get('hygiene_score', 0):.2f}"
            )
        
        return f"""Duplikate gefunden (Hash: {self.group_hash[:16]}..., Größe: {self.file_size} Bytes):

{chr(10).join(file_desc)}

Entscheide: Welche Datei soll BEHALTEN werden? 
Antworte NUR mit der Nummer (1, 2, 3...) der zu behaltenden Datei.
Begründung optional in Klammern."""


@dataclass
class FilterBuildRequest:
    """Request to build filter from natural language."""
    user_text: str
    available_filters: List[str]
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_prompt(self) -> str:
        filters_desc = "\n".join(f"- {f}" for f in self.available_filters)
        return f"""Der Nutzer möchte: "{self.user_text}"

Verfügbare Filter:
{filters_desc}

Erstelle eine JSON-Pipeline-Konfiguration. Beispiel:
{{
  "pipeline": [
    {{"type": "path_priority", "params": {{"reference_prefixes": ["/mnt/data/ref"]}}}},
    {{"type": "filename_hygiene", "params": {{}}}},
    {{"type": "artifact", "params": {{}}}}
  ]
}}

Antworte NUR mit dem JSON."""


@dataclass
class CopilotContext:
    """Full context for Copilot panel."""
    current_mode: str
    trust_level: int
    active_filters: List[str]
    recent_errors: List[Dict]
    quarantine_usage_gb: float
    quarantine_limit_gb: float
    last_operation: str = ""
    selected_files: List[str] = field(default_factory=list)


class OllamaClient:
    """Async client for Ollama API."""
    
    def __init__(self, config: AIConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def generate(self, prompt: str, system: str = "", stream: bool = False) -> str:
        """Generate completion from Ollama."""
        if not self.session:
            async with self:
                return await self.generate(prompt, system, stream)
        
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "system": system,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        
        async with self.session.post(
            f"{self.config.ollama_url}/api/generate",
            json=payload
        ) as resp:
            if resp.status != 200:
                raise AIError(f"Ollama error: {resp.status}")
            
            if stream:
                result = ""
                async for line in resp.content:
                    data = json.loads(line)
                    if "response" in data:
                        result += data["response"]
                return result
            else:
                data = await resp.json()
                return data.get("response", "")
    
    async def chat(self, messages: List[Dict[str, str]], stream: bool = False) -> str:
        """Chat completion."""
        if not self.session:
            async with self:
                return await self.chat(messages, stream)
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        
        async with self.session.post(
            f"{self.config.ollama_url}/api/chat",
            json=payload
        ) as resp:
            if resp.status != 200:
                raise AIError(f"Ollama chat error: {resp.status}")
            
            if stream:
                result = ""
                async for line in resp.content:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        result += data["message"]["content"]
                return result
            else:
                data = await resp.json()
                return data.get("message", {}).get("content", "")


class AIFilterEngine:
    """
    Main AI integration engine.
    Provides three modes: Selection Assist, NL Filter Builder, Copilot.
    """
    
    def __init__(self, config: AIConfig):
        self.config = config
        self.client: Optional[OllamaClient] = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize connection to Ollama."""
        try:
            self.client = OllamaClient(self.config)
            async with self.client as client:
                await client.generate("test", stream=False)
            self._initialized = True
            return True
        except Exception:
            self._initialized = False
            return False
    
    async def selection_assist(self, context: SelectionContext) -> Optional[int]:
        """
        Let LLM decide which file to keep when filters are tied.
        Returns index (0-based) of file to keep, or None on failure.
        """
        if not self.config.selection_assist or not self._initialized:
            return None
        
        try:
            system = """Du bist ein Experte für Datei-Deduplizierung. 
Wähle die beste Datei basierend auf: Originalität (Pfad-Tiefe), Namensqualität, Zeitstempel.
Referenz-Dateien (markiert mit [REF]) haben absolute Priorität."""
            
            response = await self.client.generate(context.to_prompt(), system=system)
            
            # Parse response - expect number
            for line in response.strip().split('\n'):
                line = line.strip()
                if line.isdigit():
                    idx = int(line) - 1
                    if 0 <= idx < len(context.files):
                        return idx
        except Exception:
            pass
        
        return None
    
    async def build_filter_pipeline(self, request: FilterBuildRequest) -> Optional[Dict]:
        """
        Convert natural language to filter pipeline JSON.
        Returns pipeline dict or None on failure.
        """
        if not self.config.nl_filter_builder or not self._initialized:
            return None
        
        try:
            system = """Du übersetzt natürliche Sprache in Filter-Pipelines für Duplikat-Selektion.
Verfügbare Filter: path_priority, filename_hygiene, artifact, path_depth, timestamp, owner.
Antworte NUR mit valider JSON."""
            
            response = await self.client.generate(request.to_prompt(), system=system)
            
            # Parse JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except Exception:
            pass
        
        return None
    
    async def copilot_query(self, context: CopilotContext, question: str) -> str:
        """
        Copilot panel: Answer user questions with full context.
        """
        if not self.config.copilot or not self._initialized:
            return "KI nicht verfügbar. Prüfen Sie Ollama-Verbindung und Einstellungen."
        
        try:
            system = self._build_copilot_system_prompt(context)
            
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": question}
            ]
            
            return await self.client.chat(messages)
        except Exception as e:
            return f"KI-Fehler: {e}"
    
    def _build_copilot_system_prompt(self, ctx: CopilotContext) -> str:
        return f"""Du bist der DataWarden Copilot - Experte für Duplikat-Management und Data Governance.

AKTUELLER STATUS:
- Modus: {ctx.current_mode}
- KI-Vertrauen: Level {ctx.trust_level} ({['STRICT', 'LAYOUT', 'ASSISTED', 'COLLABORATIVE'][ctx.trust_level]})
- Aktive Filter: {', '.join(ctx.active_filters) if ctx.active_filters else 'Keine'}
- Quarantäne: {ctx.quarantine_usage_gb:.1f}/{ctx.quarantine_limit_gb:.1f} GB
- Letzte Operation: {ctx.last_operation or 'Keine'}
- Ausgewählte Dateien: {len(ctx.selected_files)}

DEINE AUFGABE:
- Erkläre Funktionen präzise (Was? Warum? Wofür?)
- Gib konkrete Empfehlungen für Einstellungen
- Biete an, Einstellungen per Button anzuwenden (nicht automatisch!)
- Warne vor Risiken (Zero-Trust, Datenverlust)
- Sprache: Deutsch

WICHTIG: Du darfst NIEMALS autonom Einstellungen ändern. Nur Vorschläge machen!"""


class AIError(Exception):
    pass