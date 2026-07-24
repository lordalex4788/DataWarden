#!/usr/bin/env python3
"""
DataWarden - Error Handler (STUB)
User-configurable error handling with ASK/AUTO_SKIP rules.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum


class ErrorType(Enum):
    """Types of errors that can occur during indexing."""
    PERMISSION_DENIED = "permission_denied"
    FILE_LOCKED = "file_locked"
    SYMLINK_LOOP = "symlink_loop"
    CORRUPT_METADATA = "corrupt_metadata"
    IO_ERROR = "io_error"
    FILE_NOT_FOUND = "file_not_found"
    DISK_FULL = "disk_full"
    UNKNOWN = "unknown"


class ErrorAction(Enum):
    """User-defined action for error handling."""
    ASK = "ask"                    # Prompt user interactively
    AUTO_SKIP_AND_LOG = "auto_skip"  # Skip automatically, log error
    RETRY_N_TIMES = "retry"        # Retry N times then fallback to ASK
    ABORT = "abort"                # Abort entire operation


@dataclass
class ErrorContext:
    """Context information for an error."""
    error_type: ErrorType
    path: str
    detail: str
    timestamp: float = field(default_factory=time.time)
    attempt: int = 1
    max_retries: int = 3


@dataclass
class ErrorRecord:
    """Recorded error for savestate/logging."""
    error_type: str
    path: str
    action: str
    timestamp: str
    detail: str = ""


class ErrorManager:
    """
    Manages error handling with user-configurable rules.
    Supports ASK (interactive), AUTO_SKIP, and RETRY strategies.
    """

    def __init__(self):
        self.rules: dict[ErrorType, ErrorAction] = {
            ErrorType.PERMISSION_DENIED: ErrorAction.ASK,
            ErrorType.FILE_LOCKED: ErrorAction.ASK,
            ErrorType.SYMLINK_LOOP: ErrorAction.AUTO_SKIP_AND_LOG,
            ErrorType.CORRUPT_METADATA: ErrorAction.AUTO_SKIP_AND_LOG,
            ErrorType.IO_ERROR: ErrorAction.ASK,
            ErrorType.FILE_NOT_FOUND: ErrorAction.AUTO_SKIP_AND_LOG,
            ErrorType.DISK_FULL: ErrorAction.ABORT,
            ErrorType.UNKNOWN: ErrorAction.ASK,
        }

        self.retry_counts: dict[str, int] = {}
        self._ask_callback: Callable[[ErrorContext], Awaitable[ErrorAction]] | None = None

    def set_rule(self, error_type: ErrorType, action: ErrorAction) -> None:
        """Set handling rule for an error type."""
        self.rules[error_type] = action

    def set_ask_callback(self, callback: Callable[[ErrorContext], Awaitable[ErrorAction]]) -> None:
        """Set async callback for user interaction (UI modal)."""
        self._ask_callback = callback

    async def handle_error(self, context: ErrorContext) -> ErrorAction:
        """Determine and execute action for an error."""
        rule = self.rules.get(context.error_type, ErrorAction.ASK)

        if rule == ErrorAction.ASK:
            return await self._ask_user(context)

        elif rule == ErrorAction.AUTO_SKIP_AND_LOG:
            return ErrorAction.AUTO_SKIP_AND_LOG

        elif rule == ErrorAction.RETRY:
            return await self._handle_retry(context)

        elif rule == ErrorAction.ABORT:
            return ErrorAction.ABORT

        return ErrorAction.ASK

    async def _ask_user(self, context: ErrorContext) -> ErrorAction:
        """Prompt user via callback (UI modal)."""
        if self._ask_callback:
            return await self._ask_callback(context)
        # Fallback: auto-skip if no UI
        return ErrorAction.AUTO_SKIP_AND_LOG

    async def _handle_retry(self, context: ErrorContext) -> ErrorAction:
        """Handle retry logic."""
        key = f"{context.path}:{context.error_type.value}"
        attempts = self.retry_counts.get(key, 0)

        if attempts >= context.max_retries:
            # Max retries exceeded, fallback to ASK
            self.retry_counts[key] = 0
            return await self._ask_user(context)

        self.retry_counts[key] = attempts + 1
        context.attempt = attempts + 1

        # Wait a bit before retry
        await asyncio.sleep(0.5 * attempts)

        return ErrorAction.RETRY

    def record_error(self, context: ErrorContext, action: ErrorAction) -> ErrorRecord:
        """Create error record for savestate/logging."""
        return ErrorRecord(
            error_type=context.error_type.value,
            path=context.path,
            action=action.value,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(context.timestamp)),
            detail=context.detail
        )

    def clear_retry(self, path: str, error_type: ErrorType) -> None:
        """Clear retry counter for a path/error combination."""
        key = f"{path}:{error_type.value}"
        self.retry_counts.pop(key, None)


class ErrorHandler:
    """
    High-level error handler integrating with savestate.
    """

    def __init__(self, error_manager: ErrorManager, savestate=None):
        self.error_manager = error_manager
        self.savestate = savestate

    async def on_error(self, error_type: ErrorType, path: str, detail: str = "") -> ErrorAction:
        """Handle an error during indexing."""
        context = ErrorContext(
            error_type=error_type,
            path=path,
            detail=detail
        )

        action = await self.error_manager.handle_error(context)

        # Record in savestate if available
        if self.savestate:
            record = self.error_manager.record_error(context, action)
            self.savestate.errors.append(record)
            await self.savestate.save()

        return action

    def get_error_summary(self) -> dict[str, int]:
        """Get count of errors by type."""
        if not self.savestate:
            return {}

        summary = {}
        for record in self.savestate.errors:
            summary[record.error_type] = summary.get(record.error_type, 0) + 1
        return summary


# Default error handling configurations
DEFAULT_ERROR_RULES = {
    ErrorType.PERMISSION_DENIED: ErrorAction.ASK,
    ErrorType.FILE_LOCKED: ErrorAction.ASK,
    ErrorType.SYMLINK_LOOP: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.CORRUPT_METADATA: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.IO_ERROR: ErrorAction.ASK,
    ErrorType.FILE_NOT_FOUND: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.DISK_FULL: ErrorAction.ABORT,
    ErrorType.UNKNOWN: ErrorAction.ASK,
}

STRICT_ERROR_RULES = {
    ErrorType.PERMISSION_DENIED: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.FILE_LOCKED: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.SYMLINK_LOOP: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.CORRUPT_METADATA: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.IO_ERROR: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.FILE_NOT_FOUND: ErrorAction.AUTO_SKIP_AND_LOG,
    ErrorType.DISK_FULL: ErrorAction.ABORT,
    ErrorType.UNKNOWN: ErrorAction.AUTO_SKIP_AND_LOG,
}

INTERACTIVE_ERROR_RULES = {
    ErrorType.PERMISSION_DENIED: ErrorAction.ASK,
    ErrorType.FILE_LOCKED: ErrorAction.ASK,
    ErrorType.SYMLINK_LOOP: ErrorAction.ASK,
    ErrorType.CORRUPT_METADATA: ErrorAction.ASK,
    ErrorType.IO_ERROR: ErrorAction.ASK,
    ErrorType.FILE_NOT_FOUND: ErrorAction.ASK,
    ErrorType.DISK_FULL: ErrorAction.ASK,
    ErrorType.UNKNOWN: ErrorAction.ASK,
}
