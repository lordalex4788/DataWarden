#!/usr/bin/env python3
"""
DataWarden - Confirmation Engine (STUB)
Multi-level confirmation with custom hotkeys for destructive operations.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum


class ConfirmationLevel(Enum):
    """Strictness level for confirmations."""
    NONE = 0        # No confirmation (audit mode only)
    SINGLE = 1      # Single key press
    DOUBLE = 2      # Two different keys
    TRIPLE = 3      # Three different keys
    CUSTOM = 4      # Custom sequence


@dataclass
class ConfirmationStep:
    """A single step in the confirmation chain."""
    level: int
    hotkey: str
    description: str
    required: bool = True


@dataclass
class ConfirmationConfig:
    """Configuration for confirmation engine."""
    levels: int = 3
    hotkeys: list[str] = field(default_factory=lambda: ["F10", "J", "Enter"])
    descriptions: list[str] = field(default_factory=lambda: [
        "Bestätigen: Drücken Sie F10",
        "Sicherheit: Drücken Sie J",
        "Endgültig: Drücken Sie Enter"
    ])
    timeout_seconds: float = 30.0
    require_exact_match: bool = True  # Must press exact hotkey sequence

    def validate(self) -> bool:
        return len(self.hotkeys) >= self.levels and self.levels > 0


@dataclass
class ConfirmationResult:
    """Result of a confirmation sequence."""
    confirmed: bool
    level_reached: int
    timed_out: bool = False
    aborted: bool = False
    timestamp: float = field(default_factory=time.time)


class ConfirmationEngine:
    """
    Multi-level confirmation engine for destructive operations.
    Forces users through a sequence of distinct hotkeys.
    """

    def __init__(self, config: ConfirmationConfig = None):
        self.config = config or ConfirmationConfig()
        self._input_callback: Callable[[str], Awaitable[str]] | None = None
        self._display_callback: Callable[[str], Awaitable[None]] | None = None

    def set_input_callback(self, callback: Callable[[str], Awaitable[str]]) -> None:
        """Set async callback to get user input (e.g., Textual modal)."""
        self._input_callback = callback

    def set_display_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Set async callback to display messages (e.g., Textual notification)."""
        self._display_callback = callback

    async def confirm(self,
                     operation: str,
                     details: str = "",
                     custom_config: ConfirmationConfig | None = None) -> ConfirmationResult:
        """
        Run confirmation sequence for an operation.

        Args:
            operation: Description of operation (e.g., "Delete 1500 files")
            details: Additional details shown to user
            custom_config: Override default config

        Returns:
            ConfirmationResult with outcome
        """
        cfg = custom_config or self.config

        # Audit mode (levels=0): auto-confirm without prompting
        if cfg.levels == 0:
            return ConfirmationResult(
                confirmed=True,
                level_reached=0
            )

        if not cfg.validate():
            return ConfirmationResult(
                confirmed=False,
                level_reached=0,
                aborted=True
            )

        # Build confirmation message
        message = self._build_message(operation, details, cfg)

        if self._display_callback:
            await self._display_callback(message)

        # Execute each level
        for i in range(cfg.levels):
            level = i + 1
            hotkey = cfg.hotkeys[i] if i < len(cfg.hotkeys) else "Enter"
            desc = cfg.descriptions[i] if i < len(cfg.descriptions) else f"Level {level}"

            prompt = f"[{level}/{cfg.levels}] {desc} (Required: {hotkey})"

            if self._display_callback:
                await self._display_callback(prompt)

            # Get user input
            if self._input_callback:
                user_input = await self._input_callback(prompt)
            else:
                # Fallback for testing
                user_input = await self._get_input_fallback(prompt)

            # Validate
            if not self._validate_input(user_input, hotkey, cfg.require_exact_match):
                return ConfirmationResult(
                    confirmed=False,
                    level_reached=level,
                    aborted=True
                )

        return ConfirmationResult(
            confirmed=True,
            level_reached=cfg.levels
        )

    def _build_message(self, operation: str, details: str, cfg: ConfirmationConfig) -> str:
        """Build full confirmation message."""
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║              BESTÄTIGUNG ERFORDERLICH                    ║",
            "╠══════════════════════════════════════════════════════════╣",
            f"║  Aktion: {operation:<48} ║",
        ]

        if details:
            for line in details.split('\n'):
                lines.append(f"║  {line:<56} ║")

        lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            f"║  Bestätigungs-Stufen: {cfg.levels}                                ║",
            "║  Drücken Sie die angezeigten Tasten nacheinander.          ║",
            "╚══════════════════════════════════════════════════════════╝",
        ])

        return "\n".join(lines)

    def _validate_input(self, user_input: str, expected: str, exact: bool) -> bool:
        """Validate user input against expected hotkey."""
        user_input = user_input.strip()
        expected = expected.strip()

        if exact:
            return user_input == expected
        return expected.lower() in user_input.lower()

    async def _get_input_fallback(self, prompt: str) -> str:
        """Fallback for testing without UI."""
        # In real implementation, this would be a Textual modal
        return ""


class ConfirmationManager:
    """High-level manager integrating with execution modes."""

    def __init__(self):
        self.engine = ConfirmationEngine()
        self.mode_configs: dict[str, ConfirmationConfig] = {
            "audit": ConfirmationConfig(levels=0),  # No confirmation
            "safe_move": ConfirmationConfig(levels=2, hotkeys=["F10", "J"]),
            "hard_delete": ConfirmationConfig(
                levels=3,
                hotkeys=["F10", "J", "Enter"],
                descriptions=[
                    "WARNUNG: Dateien werden in Quarantäne verschoben (F10)",
                    "Sicherheit: Diese Aktion ist rückgängig machbar (J)",
                    "Endgültige Bestätigung für Hard-Delete (Enter)"
                ]
            ),
        }

    def set_mode(self, mode: str) -> None:
        """Set confirmation mode."""
        if mode in self.mode_configs:
            self.engine.config = self.mode_configs[mode]

    async def confirm_execution(self,
                              mode: str,
                              file_count: int,
                              total_size: int,
                              details: str = "") -> ConfirmationResult:
        """Confirm an execution operation."""
        self.set_mode(mode)

        op_desc = f"{mode.replace('_', ' ').title()}: {file_count} Dateien ({self._format_size(total_size)})"

        return await self.engine.confirm(operation=op_desc, details=details)

    @staticmethod
    def _format_size(bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} PB"


# Pre-configured confirmation profiles
class ConfirmationProfiles:
    """Pre-built confirmation profiles for different risk levels."""

    @staticmethod
    def minimal() -> ConfirmationConfig:
        """Minimal: Single confirmation for any write."""
        return ConfirmationConfig(
            levels=1,
            hotkeys=["F10"],
            descriptions=["Bestätigen mit F10"]
        )

    @staticmethod
    def standard() -> ConfirmationConfig:
        """Standard: Double confirmation for writes."""
        return ConfirmationConfig(
            levels=2,
            hotkeys=["F10", "J"],
            descriptions=[
                "Aktion bestätigen (F10)",
                "Sicherheitsabfrage (J)"
            ]
        )

    @staticmethod
    def strict() -> ConfirmationConfig:
        """Strict: Triple confirmation for deletes."""
        return ConfirmationConfig(
            levels=3,
            hotkeys=["F10", "J", "DELETE"],
            descriptions=[
                "Operation bestätigen (F10)",
                "Sicherheitsabfrage (J)",
                "Endgültig löschen (DELETE)"
            ]
        )

    @staticmethod
    def paranoid() -> ConfirmationConfig:
        """Paranoid: 5-level with typed phrase."""
        return ConfirmationConfig(
            levels=4,
            hotkeys=["F10", "J", "DELETE", "I_CONFIRM"],
            descriptions=[
                "Schritt 1: F10 drücken",
                "Schritt 2: J drücken",
                "Schritt 3: ENTF drücken",
                "Schritt 4: 'I_CONFIRM' eintippen"
            ]
        )

    @staticmethod
    def custom(hotkeys: list[str], descriptions: list[str]) -> ConfirmationConfig:
        """Custom confirmation sequence."""
        return ConfirmationConfig(
            levels=len(hotkeys),
            hotkeys=hotkeys,
            descriptions=descriptions
        )
