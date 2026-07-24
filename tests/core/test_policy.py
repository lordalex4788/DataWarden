#!/usr/bin/env python3
"""
Tests for Dynamic Policy Manager (Phase 5)
"""

import time

import pytest

from core.policy import (
    BUNDLE_DESCRIPTIONS,
    TRUST_LEVEL_DESCRIPTIONS,
    BundleGatekeeper,
    BundleType,
    DynamicPolicyManager,
    LearnedRule,
    TrustLevel,
)


class TestTrustLevel:
    """Tests for TrustLevel enum."""

    def test_trust_levels_order(self):
        assert TrustLevel.STRICT_ZERO_TRUST.value == 0
        assert TrustLevel.LAYOUT_ONLY.value == 1
        assert TrustLevel.ASSISTED_LOGIC.value == 2
        assert TrustLevel.COLLABORATIVE_EXECUTE.value == 3

    def test_trust_level_comparison(self):
        assert TrustLevel.STRICT_ZERO_TRUST.value < TrustLevel.LAYOUT_ONLY.value
        assert TrustLevel.LAYOUT_ONLY.value < TrustLevel.ASSISTED_LOGIC.value
        assert TrustLevel.ASSISTED_LOGIC.value < TrustLevel.COLLABORATIVE_EXECUTE.value


class TestBundleType:
    """Tests for BundleType enum."""

    def test_all_bundles_defined(self):
        assert BundleType.UI_LAYOUT.value == "ui_layout"
        assert BundleType.FILTERS_PIPELINES.value == "filters_pipelines"
        assert BundleType.FILE_METADATA_SORTING.value == "file_metadata_sorting"
        assert BundleType.GOVERNANCE_WARDEN.value == "governance_warden"


class TestLearnedRule:
    """Tests for LearnedRule dataclass."""

    def test_rule_creation(self):
        rule = LearnedRule(
            id="test_123",
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            description="Allow auto-filtering _copy files",
            created_at=time.time(),
            created_by_user_action="confirmed_ai_delete_copy"
        )
        assert rule.id == "test_123"
        assert rule.bundle == BundleType.FILTERS_PIPELINES
        assert rule.filter_type == "artifact"
        assert rule.pattern == "_copy"
        assert rule.enabled is True

    def test_rule_matches_exact(self):
        rule = LearnedRule(
            id="test",
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            description="Test",
            created_at=time.time(),
            created_by_user_action="test"
        )
        assert rule.matches(BundleType.FILTERS_PIPELINES, "artifact", "_copy") is True

    def test_rule_matches_wildcard(self):
        rule = LearnedRule(
            id="test",
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="*",
            description="Test",
            created_at=time.time(),
            created_by_user_action="test"
        )
        assert rule.matches(BundleType.FILTERS_PIPELINES, "artifact", "_copy") is True
        assert rule.matches(BundleType.FILTERS_PIPELINES, "artifact", "anything") is True

    def test_rule_no_match_different_bundle(self):
        rule = LearnedRule(
            id="test",
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            description="Test",
            created_at=time.time(),
            created_by_user_action="test"
        )
        assert rule.matches(BundleType.UI_LAYOUT, "artifact", "_copy") is False

    def test_rule_no_match_different_filter_type(self):
        rule = LearnedRule(
            id="test",
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            description="Test",
            created_at=time.time(),
            created_by_user_action="test"
        )
        assert rule.matches(BundleType.FILTERS_PIPELINES, "filename_hygiene", "_copy") is False

    def test_rule_no_match_disabled(self):
        rule = LearnedRule(
            id="test",
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            description="Test",
            created_at=time.time(),
            created_by_user_action="test",
            enabled=False
        )
        assert rule.matches(BundleType.FILTERS_PIPELINES, "artifact", "_copy") is False


class TestBundleGatekeeper:
    """Tests for BundleGatekeeper."""

    def test_gatekeeper_default_disabled(self):
        gk = BundleGatekeeper(bundle=BundleType.FILTERS_PIPELINES)
        assert gk.enabled is False
        assert gk.max_trust_level == TrustLevel.STRICT_ZERO_TRUST
        assert gk.allowed_filter_types == set()

    def test_gatekeeper_allows_when_enabled_and_level_ok(self):
        gk = BundleGatekeeper(
            bundle=BundleType.FILTERS_PIPELINES,
            enabled=True,
            allowed_filter_types={"artifact", "filename_hygiene"},
            max_trust_level=TrustLevel.ASSISTED_LOGIC
        )
        assert gk.allows(TrustLevel.ASSISTED_LOGIC, "artifact") is True
        assert gk.allows(TrustLevel.LAYOUT_ONLY, "artifact") is True

    def test_gatekeeper_blocks_when_disabled(self):
        gk = BundleGatekeeper(
            bundle=BundleType.FILTERS_PIPELINES,
            enabled=False,
            max_trust_level=TrustLevel.COLLABORATIVE_EXECUTE
        )
        assert gk.allows(TrustLevel.COLLABORATIVE_EXECUTE, "artifact") is False

    def test_gatekeeper_blocks_when_level_too_high(self):
        gk = BundleGatekeeper(
            bundle=BundleType.FILTERS_PIPELINES,
            enabled=True,
            max_trust_level=TrustLevel.ASSISTED_LOGIC
        )
        assert gk.allows(TrustLevel.COLLABORATIVE_EXECUTE, "artifact") is False

    def test_gatekeeper_blocks_filter_not_allowed(self):
        gk = BundleGatekeeper(
            bundle=BundleType.FILTERS_PIPELINES,
            enabled=True,
            allowed_filter_types={"artifact"},
            max_trust_level=TrustLevel.COLLABORATIVE_EXECUTE
        )
        assert gk.allows(TrustLevel.COLLABORATIVE_EXECUTE, "filename_hygiene") is False

    def test_gatekeeper_allows_when_no_filter_restriction(self):
        gk = BundleGatekeeper(
            bundle=BundleType.FILTERS_PIPELINES,
            enabled=True,
            allowed_filter_types=set(),
            max_trust_level=TrustLevel.COLLABORATIVE_EXECUTE
        )
        assert gk.allows(TrustLevel.COLLABORATIVE_EXECUTE, "any_filter") is True


class TestDynamicPolicyManager:
    """Tests for DynamicPolicyManager."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        return tmp_path / "config"

    @pytest.fixture
    def manager(self, temp_config_dir):
        return DynamicPolicyManager(temp_config_dir)

    def test_initial_state(self, manager):
        assert manager.global_trust_level == TrustLevel.STRICT_ZERO_TRUST
        assert len(manager.bundle_gatekeepers) == 4
        assert len(manager.learned_rules) == 0

        for bt in BundleType:
            gk = manager.bundle_gatekeepers[bt]
            assert gk.enabled is False
            assert gk.max_trust_level == TrustLevel.STRICT_ZERO_TRUST

    def test_set_global_trust_level(self, manager):
        assert manager.set_global_trust_level(TrustLevel.LAYOUT_ONLY) is True
        assert manager.global_trust_level == TrustLevel.LAYOUT_ONLY

        # Setting same level returns False
        assert manager.set_global_trust_level(TrustLevel.LAYOUT_ONLY) is False

    def test_get_global_trust_level(self, manager):
        assert manager.get_global_trust_level() == TrustLevel.STRICT_ZERO_TRUST
        manager.set_global_trust_level(TrustLevel.ASSISTED_LOGIC)
        assert manager.get_global_trust_level() == TrustLevel.ASSISTED_LOGIC

    def test_set_bundle_enabled(self, manager):
        manager.set_bundle_enabled(BundleType.FILTERS_PIPELINES, True)
        assert manager.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].enabled is True

        manager.set_bundle_enabled(BundleType.FILTERS_PIPELINES, False)
        assert manager.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].enabled is False

    def test_set_bundle_max_trust(self, manager):
        manager.set_bundle_max_trust(BundleType.UI_LAYOUT, TrustLevel.COLLABORATIVE_EXECUTE)
        assert manager.bundle_gatekeepers[BundleType.UI_LAYOUT].max_trust_level == TrustLevel.COLLABORATIVE_EXECUTE

    def test_allow_filter_type(self, manager):
        manager.allow_filter_type(BundleType.FILTERS_PIPELINES, "artifact")
        assert "artifact" in manager.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].allowed_filter_types

    def test_revoke_filter_type(self, manager):
        manager.allow_filter_type(BundleType.FILTERS_PIPELINES, "artifact")
        manager.revoke_filter_type(BundleType.FILTERS_PIPELINES, "artifact")
        assert "artifact" not in manager.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].allowed_filter_types

    def test_learn_from_confirmation(self, manager):
        rule = manager.learn_from_confirmation(
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            user_action="confirmed_ai_delete_copy",
            description="Allow AI to auto-delete _copy files"
        )

        assert rule.id.startswith("learned_")
        assert rule.bundle == BundleType.FILTERS_PIPELINES
        assert rule.filter_type == "artifact"
        assert rule.pattern == "_copy"
        assert rule.created_by_user_action == "confirmed_ai_delete_copy"
        assert len(manager.learned_rules) == 1

    def test_check_learned_rule_match(self, manager):
        manager.learn_from_confirmation(
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            user_action="confirmed_ai_delete_copy"
        )

        rule = manager.check_learned_rule(BundleType.FILTERS_PIPELINES, "artifact", "_copy")
        assert rule is not None
        assert rule.pattern == "_copy"

    def test_check_learned_rule_no_match(self, manager):
        manager.learn_from_confirmation(
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            user_action="confirmed_ai_delete_copy"
        )

        rule = manager.check_learned_rule(BundleType.FILTERS_PIPELINES, "artifact", "_v2")
        assert rule is None

        rule = manager.check_learned_rule(BundleType.UI_LAYOUT, "artifact", "_copy")
        assert rule is None

    def test_revoke_learned_rule(self, manager):
        rule = manager.learn_from_confirmation(
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            user_action="confirmed_ai_delete_copy"
        )

        assert manager.revoke_learned_rule(rule.id) is True
        assert len(manager.learned_rules) == 0

        # Revoking non-existent returns False
        assert manager.revoke_learned_rule("nonexistent") is False

    def test_get_learned_rules(self, manager):
        manager.learn_from_confirmation(BundleType.FILTERS_PIPELINES, "artifact", "_copy", "action1")
        manager.learn_from_confirmation(BundleType.FILTERS_PIPELINES, "filename_hygiene", "spaces", "action2")
        manager.learn_from_confirmation(BundleType.UI_LAYOUT, "layout", "split", "action3")

        all_rules = manager.get_learned_rules()
        assert len(all_rules) == 3

        filter_rules = manager.get_learned_rules(BundleType.FILTERS_PIPELINES)
        assert len(filter_rules) == 2

        ui_rules = manager.get_learned_rules(BundleType.UI_LAYOUT)
        assert len(ui_rules) == 1

    def test_can_ai_act_strict_zero_trust_no_rule(self, manager):
        allowed, reason = manager.can_ai_act(BundleType.FILTERS_PIPELINES, "artifact", "_copy")
        assert allowed is False
        assert "Zero-Trust" in reason

    def test_can_ai_act_strict_zero_trust_with_learned_rule(self, manager):
        manager.learn_from_confirmation(
            bundle=BundleType.FILTERS_PIPELINES,
            filter_type="artifact",
            pattern="_copy",
            user_action="confirmed_ai_delete_copy"
        )

        allowed, reason = manager.can_ai_act(BundleType.FILTERS_PIPELINES, "artifact", "_copy")
        assert allowed is True
        assert "User-authorized rule" in reason

    def test_can_ai_act_bundle_disabled(self, manager):
        manager.set_global_trust_level(TrustLevel.ASSISTED_LOGIC)
        # Bundle still disabled by default
        allowed, reason = manager.can_ai_act(BundleType.FILTERS_PIPELINES, "artifact", "_copy")
        assert allowed is False
        assert "gatekeeper blocks" in reason

    def test_can_ai_act_bundle_enabled_level_ok(self, manager):
        manager.set_global_trust_level(TrustLevel.ASSISTED_LOGIC)
        manager.set_bundle_enabled(BundleType.FILTERS_PIPELINES, True)
        manager.set_bundle_max_trust(BundleType.FILTERS_PIPELINES, TrustLevel.ASSISTED_LOGIC)
        manager.allow_filter_type(BundleType.FILTERS_PIPELINES, "artifact")

        allowed, reason = manager.can_ai_act(BundleType.FILTERS_PIPELINES, "artifact", "_copy")
        assert allowed is True
        assert "requires confirmation" in reason

    def test_can_ai_act_level_too_high(self, manager):
        manager.set_global_trust_level(TrustLevel.COLLABORATIVE_EXECUTE)
        manager.set_bundle_enabled(BundleType.FILTERS_PIPELINES, True)
        manager.set_bundle_max_trust(BundleType.FILTERS_PIPELINES, TrustLevel.ASSISTED_LOGIC)

        allowed, reason = manager.can_ai_act(BundleType.FILTERS_PIPELINES, "artifact", "_copy")
        assert allowed is False
        assert "gatekeeper blocks" in reason

    def test_can_ai_act_filter_not_allowed(self, manager):
        manager.set_global_trust_level(TrustLevel.COLLABORATIVE_EXECUTE)
        manager.set_bundle_enabled(BundleType.FILTERS_PIPELINES, True)
        manager.set_bundle_max_trust(BundleType.FILTERS_PIPELINES, TrustLevel.COLLABORATIVE_EXECUTE)
        manager.allow_filter_type(BundleType.FILTERS_PIPELINES, "artifact")
        # filename_hygiene not allowed

        allowed, reason = manager.can_ai_act(BundleType.FILTERS_PIPELINES, "filename_hygiene", "spaces")
        assert allowed is False
        assert "gatekeeper blocks" in reason

    def test_save_load_persistence(self, temp_config_dir):
        """Test that policies persist across save/load."""
        manager1 = DynamicPolicyManager(temp_config_dir)

        manager1.set_global_trust_level(TrustLevel.ASSISTED_LOGIC)
        manager1.set_bundle_enabled(BundleType.FILTERS_PIPELINES, True)
        manager1.set_bundle_max_trust(BundleType.FILTERS_PIPELINES, TrustLevel.ASSISTED_LOGIC)
        manager1.allow_filter_type(BundleType.FILTERS_PIPELINES, "artifact")
        manager1.learn_from_confirmation(
            BundleType.FILTERS_PIPELINES, "artifact", "_copy", "action", "desc"
        )

        # Create new manager instance (simulates restart)
        manager2 = DynamicPolicyManager(temp_config_dir)

        assert manager2.global_trust_level == TrustLevel.ASSISTED_LOGIC
        assert manager2.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].enabled is True
        assert manager2.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].max_trust_level == TrustLevel.ASSISTED_LOGIC
        assert "artifact" in manager2.bundle_gatekeepers[BundleType.FILTERS_PIPELINES].allowed_filter_types
        assert len(manager2.learned_rules) == 1

    def test_get_status_summary(self, manager):
        manager.set_global_trust_level(TrustLevel.ASSISTED_LOGIC)
        manager.set_bundle_enabled(BundleType.FILTERS_PIPELINES, True)
        manager.allow_filter_type(BundleType.FILTERS_PIPELINES, "artifact")
        manager.learn_from_confirmation(BundleType.FILTERS_PIPELINES, "artifact", "_copy", "action")

        summary = manager.get_status_summary()

        assert summary["global_trust_level"] == "ASSISTED_LOGIC"
        assert summary["global_trust_value"] == 2
        assert summary["learned_rules_count"] == 1
        assert summary["active_learned_rules"] == 1
        assert summary["bundles"]["filters_pipelines"]["enabled"] is True
        assert "artifact" in summary["bundles"]["filters_pipelines"]["allowed_filters"]


class TestTrustLevelDescriptions:
    """Tests for TRUST_LEVEL_DESCRIPTIONS dict."""

    def test_all_levels_have_descriptions(self):
        for level in TrustLevel:
            assert level in TRUST_LEVEL_DESCRIPTIONS
            desc = TRUST_LEVEL_DESCRIPTIONS[level]
            assert "name" in desc
            assert "description" in desc
            assert "warning" in desc
            assert "color" in desc

    def test_level_names_match(self):
        for level in TrustLevel:
            assert TRUST_LEVEL_DESCRIPTIONS[level]["name"] == level.name


class TestBundleDescriptions:
    """Tests for BUNDLE_DESCRIPTIONS dict."""

    def test_all_bundles_have_descriptions(self):
        for bundle in BundleType:
            assert bundle in BUNDLE_DESCRIPTIONS
            desc = BUNDLE_DESCRIPTIONS[bundle]
            assert "name" in desc
            assert "description" in desc
