#!/usr/bin/env python3
"""
Tests for Confirmation Engine (Phase 5)
"""

from unittest.mock import AsyncMock

import pytest

from core.confirmation import (
    ConfirmationConfig,
    ConfirmationEngine,
    ConfirmationManager,
    ConfirmationProfiles,
    ConfirmationResult,
    ConfirmationStep,
)


class TestConfirmationConfig:
    """Tests for ConfirmationConfig validation."""

    def test_valid_config_default(self):
        cfg = ConfirmationConfig()
        assert cfg.validate() is True
        assert cfg.levels == 3
        assert len(cfg.hotkeys) == 3

    def test_valid_config_custom(self):
        cfg = ConfirmationConfig(
            levels=2,
            hotkeys=["F10", "J"],
            descriptions=["Step 1", "Step 2"]
        )
        assert cfg.validate() is True

    def test_invalid_config_not_enough_hotkeys(self):
        cfg = ConfirmationConfig(
            levels=3,
            hotkeys=["F10", "J"],
            descriptions=["Step 1", "Step 2", "Step 3"]
        )
        assert cfg.validate() is False

    def test_invalid_config_zero_levels(self):
        cfg = ConfirmationConfig(levels=0, hotkeys=["F10"])
        assert cfg.validate() is False

    def test_invalid_config_negative_levels(self):
        cfg = ConfirmationConfig(levels=-1, hotkeys=["F10"])
        assert cfg.validate() is False


class TestConfirmationResult:
    """Tests for ConfirmationResult."""

    def test_default_result(self):
        result = ConfirmationResult(confirmed=True, level_reached=3)
        assert result.confirmed is True
        assert result.level_reached == 3
        assert result.timed_out is False
        assert result.aborted is False
        assert isinstance(result.timestamp, float)

    def test_result_with_timeout(self):
        result = ConfirmationResult(
            confirmed=False,
            level_reached=2,
            timed_out=True
        )
        assert result.timed_out is True
        assert result.confirmed is False


class TestConfirmationEngine:
    """Tests for ConfirmationEngine."""

    @pytest.fixture
    def engine(self):
        config = ConfirmationConfig(
            levels=2,
            hotkeys=["F10", "J"],
            descriptions=["Confirm F10", "Confirm J"]
        )
        engine = ConfirmationEngine(config)
        return engine

    @pytest.mark.asyncio
    async def test_confirm_success_with_callbacks(self, engine):
        """Test successful confirmation with mocked callbacks."""
        input_sequence = ["F10", "J"]
        input_mock = AsyncMock(side_effect=input_sequence)
        display_mock = AsyncMock()

        engine.set_input_callback(input_mock)
        engine.set_display_callback(display_mock)

        result = await engine.confirm("Test Operation", "Details here")

        assert result.confirmed is True
        assert result.level_reached == 2
        assert input_mock.call_count == 2
        assert display_mock.call_count >= 3  # Initial message + 2 prompts

    @pytest.mark.asyncio
    async def test_confirm_failure_wrong_key(self, engine):
        """Test confirmation failure on wrong key."""
        input_mock = AsyncMock(return_value="WRONG")
        display_mock = AsyncMock()

        engine.set_input_callback(input_mock)
        engine.set_display_callback(display_mock)

        result = await engine.confirm("Test Operation")

        assert result.confirmed is False
        assert result.aborted is True
        assert result.level_reached == 1

    @pytest.mark.asyncio
    async def test_confirm_case_insensitive_when_not_exact(self, engine):
        """Test case insensitive matching when exact_match=False."""
        engine.config.require_exact_match = False
        input_mock = AsyncMock(side_effect=["f10", "j"])
        display_mock = AsyncMock()

        engine.set_input_callback(input_mock)
        engine.set_display_callback(display_mock)

        result = await engine.confirm("Test Operation")

        assert result.confirmed is True

    @pytest.mark.asyncio
    async def test_confirm_exact_match_required(self, engine):
        """Test exact match required."""
        engine.config.require_exact_match = True
        input_mock = AsyncMock(side_effect=["f10", "J"])  # lowercase f10
        display_mock = AsyncMock()

        engine.set_input_callback(input_mock)
        engine.set_display_callback(display_mock)

        result = await engine.confirm("Test Operation")

        assert result.confirmed is False
        assert result.aborted is True

    @pytest.mark.asyncio
    async def test_confirm_invalid_config(self, engine):
        """Test confirmation with invalid config returns aborted."""
        engine.config = ConfirmationConfig(levels=3, hotkeys=["F10"])
        input_mock = AsyncMock()
        display_mock = AsyncMock()

        engine.set_input_callback(input_mock)
        engine.set_display_callback(display_mock)

        result = await engine.confirm("Test Operation")

        assert result.confirmed is False
        assert result.aborted is True
        assert result.level_reached == 0
        input_mock.assert_not_called()

    def test_build_message(self, engine):
        """Test message building."""
        msg = engine._build_message("Delete 5 files", "Size: 100MB", engine.config)

        assert "BESTÄTIGUNG ERFORDERLICH" in msg
        assert "Delete 5 files" in msg
        assert "Size: 100MB" in msg
        assert "Bestätigungs-Stufen: 2" in msg


class TestConfirmationManager:
    """Tests for ConfirmationManager."""

    @pytest.fixture
    def manager(self):
        return ConfirmationManager()

    def test_mode_configs_exist(self, manager):
        assert "audit" in manager.mode_configs
        assert "safe_move" in manager.mode_configs
        assert "hard_delete" in manager.mode_configs

    def test_audit_mode_no_confirmation(self, manager):
        cfg = manager.mode_configs["audit"]
        assert cfg.levels == 0

    def test_safe_move_mode_two_levels(self, manager):
        cfg = manager.mode_configs["safe_move"]
        assert cfg.levels == 2
        assert cfg.hotkeys == ["F10", "J"]

    def test_hard_delete_mode_three_levels(self, manager):
        cfg = manager.mode_configs["hard_delete"]
        assert cfg.levels == 3
        assert cfg.hotkeys == ["F10", "J", "Enter"]

    def test_set_mode(self, manager):
        manager.set_mode("safe_move")
        assert manager.engine.config.levels == 2

        manager.set_mode("hard_delete")
        assert manager.engine.config.levels == 3

    def test_set_mode_invalid(self, manager):
        # Should not crash, just ignore
        manager.set_mode("invalid_mode")
        # Config unchanged
        assert manager.engine.config.levels == 3  # Default is hard_delete

    def test_format_size(self):
        assert ConfirmationManager._format_size(500) == "500.0 B"
        assert ConfirmationManager._format_size(1024) == "1.0 KB"
        assert ConfirmationManager._format_size(1024 * 1024) == "1.0 MB"
        assert ConfirmationManager._format_size(1024 * 1024 * 1024) == "1.0 GB"

    @pytest.mark.asyncio
    async def test_confirm_execution_audit_mode(self, manager):
        """Audit mode should not require confirmation (levels=0)."""
        input_mock = AsyncMock()
        display_mock = AsyncMock()

        manager.engine.set_input_callback(input_mock)
        manager.engine.set_display_callback(display_mock)

        result = await manager.confirm_execution("audit", 100, 1024 * 1024)

        assert result.confirmed is True
        assert result.level_reached == 0
        input_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_execution_safe_move(self, manager):
        """Safe move mode requires 2 confirmations."""
        input_mock = AsyncMock(side_effect=["F10", "J"])
        display_mock = AsyncMock()

        manager.engine.set_input_callback(input_mock)
        manager.engine.set_display_callback(display_mock)

        result = await manager.confirm_execution("safe_move", 10, 1024 * 1024)

        assert result.confirmed is True
        assert result.level_reached == 2

    @pytest.mark.asyncio
    async def test_confirm_execution_hard_delete(self, manager):
        """Hard delete requires 3 confirmations."""
        input_mock = AsyncMock(side_effect=["F10", "J", "Enter"])
        display_mock = AsyncMock()

        manager.engine.set_input_callback(input_mock)
        manager.engine.set_display_callback(display_mock)

        result = await manager.confirm_execution("hard_delete", 5, 1024)

        assert result.confirmed is True
        assert result.level_reached == 3


class TestConfirmationProfiles:
    """Tests for pre-built confirmation profiles."""

    def test_minimal_profile(self):
        cfg = ConfirmationProfiles.minimal()
        assert cfg.levels == 1
        assert cfg.hotkeys == ["F10"]
        assert cfg.descriptions == ["Bestätigen mit F10"]

    def test_standard_profile(self):
        cfg = ConfirmationProfiles.standard()
        assert cfg.levels == 2
        assert cfg.hotkeys == ["F10", "J"]

    def test_strict_profile(self):
        cfg = ConfirmationProfiles.strict()
        assert cfg.levels == 3
        assert cfg.hotkeys == ["F10", "J", "DELETE"]

    def test_paranoid_profile(self):
        cfg = ConfirmationProfiles.paranoid()
        assert cfg.levels == 4
        assert cfg.hotkeys == ["F10", "J", "DELETE", "I_CONFIRM"]

    def test_custom_profile(self):
        cfg = ConfirmationProfiles.custom(
            hotkeys=["A", "B", "C"],
            descriptions=["Step A", "Step B", "Step C"]
        )
        assert cfg.levels == 3
        assert cfg.hotkeys == ["A", "B", "C"]


class TestConfirmationStep:
    """Tests for ConfirmationStep dataclass."""

    def test_step_creation(self):
        step = ConfirmationStep(level=1, hotkey="F10", description="Press F10")
        assert step.level == 1
        assert step.hotkey == "F10"
        assert step.description == "Press F10"
        assert step.required is True

    def test_step_optional(self):
        step = ConfirmationStep(level=1, hotkey="F10", description="Press F10", required=False)
        assert step.required is False
