#!/usr/bin/env python3
"""
DataWarden - Internationalization Manager
Loads and manages .lang localization files with descriptor comments.
"""

from __future__ import annotations

import re
from pathlib import Path


class I18nManager:
    """Manages localization files and translations."""

    def __init__(self, locale_dir: str = "locale", default_locale: str = "de_DE"):
        self.locale_dir = Path(locale_dir)
        self.default_locale = default_locale
        self.current_locale = default_locale
        self._translations: dict[str, dict[str, str]] = {}
        self._descriptors: dict[str, dict[str, str]] = {}
        self._available_locales: list[str] = []
        self._load_all()

    def _load_all(self) -> None:
        """Load all .lang files from locale directory."""
        if not self.locale_dir.exists():
            return

        for lang_file in self.locale_dir.glob("*.lang"):
            locale = lang_file.stem
            self._available_locales.append(locale)
            translations, descriptors = self._parse_lang_file(lang_file)
            self._translations[locale] = translations
            self._descriptors[locale] = descriptors

    def _parse_lang_file(self, path: Path) -> tuple[dict[str, str], dict[str, str]]:
        """Parse a .lang file into translations and descriptors."""
        translations = {}
        descriptors = {}
        current_descriptor = ""

        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n')

                # Skip empty lines
                if not line.strip():
                    continue

                # Descriptor comment
                if line.startswith('# Descriptor:'):
                    current_descriptor = line[13:].strip()
                    continue

                # Section comment (ignore for parsing)
                if line.startswith('# ['):
                    current_descriptor = ""
                    continue

                # Key = Value
                match = re.match(r'^(\w+)\s*=\s*"(.*)"$', line)
                if match:
                    key, value = match.groups()
                    translations[key] = value
                    if current_descriptor:
                        descriptors[key] = current_descriptor
                    current_descriptor = ""

        return translations, descriptors

    def set_locale(self, locale: str) -> bool:
        """Set current locale. Returns True if successful."""
        if locale in self._translations:
            self.current_locale = locale
            return True
        return False

    def get_available_locales(self) -> list[str]:
        """Get list of available locale codes."""
        return self._available_locales.copy()

    def t(self, key: str, **kwargs) -> str:
        """Translate a key with optional formatting."""
        # Try current locale
        if self.current_locale in self._translations:
            if key in self._translations[self.current_locale]:
                return self._translations[self.current_locale][key].format(**kwargs)

        # Fallback to default locale
        if self.default_locale in self._translations:
            if key in self._translations[self.default_locale]:
                return self._translations[self.default_locale][key].format(**kwargs)

        # Return key as last resort
        return key

    def get_descriptor(self, key: str, locale: str | None = None) -> str:
        """Get descriptor comment for a key."""
        target_locale = locale or self.current_locale
        if target_locale in self._descriptors:
            return self._descriptors[target_locale].get(key, "")
        return ""

    def has_key(self, key: str, locale: str | None = None) -> bool:
        """Check if a translation key exists."""
        target_locale = locale or self.current_locale
        return target_locale in self._translations and key in self._translations[target_locale]

    def get_all_keys(self) -> list[str]:
        """Get all translation keys from current locale."""
        if self.current_locale in self._translations:
            return list(self._translations[self.current_locale].keys())
        return []
