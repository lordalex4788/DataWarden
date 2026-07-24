#!/usr/bin/env python3
"""
DataWarden - Dynamic Policy Manager (STUB)
Zero-Trust Matrix with GlobalTrustLevel + BundleGatekeepers + Learning.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TrustLevel(Enum):
    STRICT_ZERO_TRUST = 0      # AI isolated, passive only
    LAYOUT_ONLY = 1            # AI may adjust layouts
    ASSISTED_LOGIC = 2         # AI may propose filters (needs confirmation)
    COLLABORATIVE_EXECUTE = 3  # AI may activate filters/sort (delete always human)


class BundleType(Enum):
    UI_LAYOUT = "ui_layout"
    FILTERS_PIPELINES = "filters_pipelines"
    FILE_METADATA_SORTING = "file_metadata_sorting"
    GOVERNANCE_WARDEN = "governance_warden"


@dataclass
class LearnedRule:
    """A rule learned from user confirmation."""
    id: str
    bundle: BundleType
    filter_type: str          # e.g., "filename_hygiene", "artifact"
    pattern: str              # e.g., ".mp3", "PROJ_*", "_copy"
    description: str          # Human-readable: "Allow AI to auto-filter MP3 artifacts"
    created_at: float
    created_by_user_action: str  # What user did: "confirmed_ai_delete_mp3"
    enabled: bool = True

    def matches(self, bundle: BundleType, filter_type: str, pattern: str) -> bool:
        return (self.bundle == bundle and
                self.filter_type == filter_type and
                (self.pattern == "*" or self.pattern == pattern) and
                self.enabled)


@dataclass
class BundleGatekeeper:
    """Per-bundle AI permission gatekeeper."""
    bundle: BundleType
    enabled: bool = False      # Master toggle for this bundle
    allowed_filter_types: set[str] = field(default_factory=set)
    max_trust_level: TrustLevel = TrustLevel.STRICT_ZERO_TRUST

    def allows(self, trust_level: TrustLevel, filter_type: str) -> bool:
        if not self.enabled:
            return False
        if trust_level.value > self.max_trust_level.value:
            return False
        if self.allowed_filter_types and filter_type not in self.allowed_filter_types:
            return False
        return True


class DynamicPolicyManager:
    """
    Manages Zero-Trust Matrix + Learned Rules.
    GlobalTrustLevel + BundleGatekeepers + LearnedRules.
    """

    CONFIG_FILE = "config/policies.json"

    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.global_trust_level = TrustLevel.STRICT_ZERO_TRUST
        self.bundle_gatekeepers: dict[BundleType, BundleGatekeeper] = {
            bt: BundleGatekeeper(bundle=bt) for bt in BundleType
        }
        self.learned_rules: list[LearnedRule] = []

        self.load()

    def load(self) -> None:
        """Load policies from disk."""
        config_file = self.config_dir / self.CONFIG_FILE
        if not config_file.exists():
            return

        try:
            data = json.loads(config_file.read_text())

            self.global_trust_level = TrustLevel(data.get("global_trust_level", 0))

            for bt_str, gk_data in data.get("bundle_gatekeepers", {}).items():
                bt = BundleType(bt_str)
                self.bundle_gatekeepers[bt] = BundleGatekeeper(
                    bundle=bt,
                    enabled=gk_data.get("enabled", False),
                    allowed_filter_types=set(gk_data.get("allowed_filter_types", [])),
                    max_trust_level=TrustLevel(gk_data.get("max_trust_level", 0))
                )

            self.learned_rules = [
                LearnedRule(**r) for r in data.get("learned_rules", [])
            ]
        except Exception:
            pass  # Keep defaults on error

    def save(self) -> None:
        """Save policies to disk."""
        config_file = self.config_dir / self.CONFIG_FILE
        config_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "global_trust_level": self.global_trust_level.value,
            "bundle_gatekeepers": {
                bt.value: {
                    "enabled": gk.enabled,
                    "allowed_filter_types": list(gk.allowed_filter_types),
                    "max_trust_level": gk.max_trust_level.value
                }
                for bt, gk in self.bundle_gatekeepers.items()
            },
            "learned_rules": [
                {
                    "id": r.id,
                    "bundle": r.bundle.value,
                    "filter_type": r.filter_type,
                    "pattern": r.pattern,
                    "description": r.description,
                    "created_at": r.created_at,
                    "created_by_user_action": r.created_by_user_action,
                    "enabled": r.enabled
                }
                for r in self.learned_rules
            ]
        }

        config_file.write_text(json.dumps(data, indent=2))

    # --- Global Trust Level ---

    def set_global_trust_level(self, level: TrustLevel) -> bool:
        """Set global trust level. Returns True if changed."""
        if level != self.global_trust_level:
            self.global_trust_level = level
            self.save()
            return True
        return False

    def get_global_trust_level(self) -> TrustLevel:
        return self.global_trust_level

    # --- Bundle Gatekeepers ---

    def set_bundle_enabled(self, bundle: BundleType, enabled: bool) -> None:
        self.bundle_gatekeepers[bundle].enabled = enabled
        self.save()

    def set_bundle_max_trust(self, bundle: BundleType, level: TrustLevel) -> None:
        self.bundle_gatekeepers[bundle].max_trust_level = level
        self.save()

    def allow_filter_type(self, bundle: BundleType, filter_type: str) -> None:
        self.bundle_gatekeepers[bundle].allowed_filter_types.add(filter_type)
        self.save()

    def revoke_filter_type(self, bundle: BundleType, filter_type: str) -> None:
        self.bundle_gatekeepers[bundle].allowed_filter_types.discard(filter_type)
        self.save()

    # --- Learned Rules (Dynamic Whitelist) ---

    def learn_from_confirmation(self,
                               bundle: BundleType,
                               filter_type: str,
                               pattern: str,
                               user_action: str,
                               description: str = "") -> LearnedRule:
        """
        Called when user checks 'Remember this decision' in confirmation modal.
        Creates a learned rule allowing future auto-execution.
        """
        rule = LearnedRule(
            id=f"learned_{int(time.time() * 1000)}",
            bundle=bundle,
            filter_type=filter_type,
            pattern=pattern,
            description=description or f"Auto-allow {filter_type} for {pattern}",
            created_at=time.time(),
            created_by_user_action=user_action
        )

        self.learned_rules.append(rule)
        self.save()
        return rule

    def check_learned_rule(self,
                          bundle: BundleType,
                          filter_type: str,
                          pattern: str) -> LearnedRule | None:
        """Check if a learned rule matches this AI action."""
        for rule in self.learned_rules:
            if rule.matches(bundle, filter_type, pattern):
                return rule
        return None

    def revoke_learned_rule(self, rule_id: str) -> bool:
        """Revoke a learned rule (user clicked 'Revoke' in settings)."""
        for i, rule in enumerate(self.learned_rules):
            if rule.id == rule_id:
                self.learned_rules.pop(i)
                self.save()
                return True
        return False

    def get_learned_rules(self, bundle: BundleType | None = None) -> list[LearnedRule]:
        if bundle:
            return [r for r in self.learned_rules if r.bundle == bundle]
        return self.learned_rules.copy()

    # --- Permission Matrix Check ---

    def can_ai_act(self,
                  bundle: BundleType,
                  filter_type: str,
                  pattern: str = "*") -> tuple[bool, str]:
        """
        Check if AI may perform an action.
        Returns (allowed, reason).
        """
        # 1. Check global trust level
        if self.global_trust_level == TrustLevel.STRICT_ZERO_TRUST:
            # Still check learned rules for auto-execute
            rule = self.check_learned_rule(bundle, filter_type, pattern)
            if rule:
                return True, f"User-authorized rule: {rule.description}"
            return False, "Global Zero-Trust active"

        # 2. Check bundle gatekeeper
        gatekeeper = self.bundle_gatekeepers[bundle]
        if not gatekeeper.allows(self.global_trust_level, filter_type):
            return False, f"Bundle {bundle.value} gatekeeper blocks (level: {gatekeeper.max_trust_level.name})"

        # 3. Check learned rule for auto-execute (bypasses confirmation)
        rule = self.check_learned_rule(bundle, filter_type, pattern)
        if rule:
            return True, f"User-authorized rule: {rule.description}"

        # 4. Allowed but needs confirmation
        return True, "Allowed by policy - requires confirmation"

    def get_status_summary(self) -> dict[str, Any]:
        """Get summary for UI display."""
        return {
            "global_trust_level": self.global_trust_level.name,
            "global_trust_value": self.global_trust_level.value,
            "bundles": {
                bt.value: {
                    "enabled": gk.enabled,
                    "max_trust": gk.max_trust_level.name,
                    "allowed_filters": list(gk.allowed_filter_types)
                }
                for bt, gk in self.bundle_gatekeepers.items()
            },
            "learned_rules_count": len(self.learned_rules),
            "active_learned_rules": sum(1 for r in self.learned_rules if r.enabled)
        }


# Predefined trust level descriptions for UI
TRUST_LEVEL_DESCRIPTIONS = {
    TrustLevel.STRICT_ZERO_TRUST: {
        "name": "STRICT_ZERO_TRUST",
        "description": "KI ist komplett isoliert. Darf nur Erklärungen geben, keine Aktionen ausführen.",
        "warning": "Maximale Sicherheit. Alle KI-Vorschläge erfordern manuelle Bestätigung.",
        "color": "green"
    },
    TrustLevel.LAYOUT_ONLY: {
        "name": "LAYOUT_ONLY",
        "description": "KI darf Layouts anpassen (Panes splitten, resizen). Keine Programmlogik.",
        "warning": "Niedriges Risiko. UI-Änderungen sind leicht rückgängig zu machen.",
        "color": "yellow"
    },
    TrustLevel.ASSISTED_LOGIC: {
        "name": "ASSISTED_LOGIC",
        "description": "KI darf Filter-Pipelines vorschlagen. Erfordert Bestätigung vor Aktivierung.",
        "warning": "Mittleres Risiko. Falsche Filter können Dateien zum Löschen markieren.",
        "color": "orange"
    },
    TrustLevel.COLLABORATIVE_EXECUTE: {
        "name": "COLLABORATIVE_EXECUTE",
        "description": "KI darf Filter direkt aktivieren und Sortierungen einspielen. Löschen bleibt menschlich.",
        "warning": "HOHES RISIKO! KI kann autonom Filter ändern. Nur für Experten.",
        "color": "red"
    }
}


BUNDLE_DESCRIPTIONS = {
    BundleType.UI_LAYOUT: {
        "name": "UI/Layout",
        "description": "Pane-Layouts, Splits, Resizing, Theming, Fenster-Anordnung"
    },
    BundleType.FILTERS_PIPELINES: {
        "name": "Filter/Pipelines",
        "description": "Auto-Select Filter, Regex, Artefakt-Erkennung, Priorisierungs-Regeln"
    },
    BundleType.FILE_METADATA_SORTING: {
        "name": "Datei-Metadaten/Sortierung",
        "description": "Umbenennen, Verschieben, Metadaten-Änderungen, KI-Sortierung"
    },
    BundleType.GOVERNANCE_WARDEN: {
        "name": "Governance/Warden",
        "description": "Dateisystem-Überwachung, Berechtigungen, Namenskonventionen, Klassifizierung"
    }
}
