"""Dynamic, config-file-driven bundle configuration manager with auto-save."""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Callable


def _auto_convert(value: str) -> Any:
    """Convert string value to appropriate type (int, float, bool, str)."""
    value = value.strip()
    lower_val = value.lower()
    if lower_val in ("true", "yes", "1", "on"):
        return True
    if lower_val in ("false", "no", "0", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


class BundleConfig:
    """Manages configuration from bundle.ini with auto-discovery and auto-save."""

    def __init__(self, config_path: Path | str | None = None):
        self._config = configparser.ConfigParser(allow_no_value=True)
        self._config.optionxform = str
        self._config_path = self._find_config_path(config_path)

        if self._config_path and self._config_path.exists():
            self.load()

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def sections(self) -> list[str]:
        return self._config.sections()

    def _find_config_path(self, explicit: Path | str | None) -> Path | None:
        """Find bundle.ini or .bundle.ini in common locations."""
        if explicit:
            path = Path(explicit).resolve()
            if path.exists():
                return path

        search_dirs = [
            Path.cwd(),
            Path(__file__).resolve().parent.parent,
            Path.home(),
        ]

        for dir_path in search_dirs:
            for filename in ("bundle.ini", ".bundle.ini"):
                full_path = dir_path / filename
                if full_path.exists():
                    return full_path

        return None

    def load(self, config_path: Path | str | None = None) -> None:
        """Load config from disk; if no path given, uses self._config_path."""
        path = Path(config_path).resolve() if config_path else self._config_path
        if path and path.exists():
            self._config.read(path, encoding="utf-8")
            if not self._config_path:
                self._config_path = path

    def save(self, config_path: Path | str | None = None) -> None:
        """Save config to disk; auto-creates file in project root if needed."""
        path = Path(config_path).resolve() if config_path else self._config_path

        if not path:
            project_root = Path(__file__).resolve().parent.parent
            path = project_root / "bundle.ini"
            self._config_path = path

        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "w", encoding="utf-8") as f:
            self._config.write(f)

    def get(
        self,
        key: str,
        default: Any = None,
        section_priority: list[str] | None = None,
        converter: Callable[[str], Any] | None = None,
    ) -> Any:
        """
        Get config value with optional section priority list; auto-converts.
        """
        sections = section_priority or self._config.sections()
        for section in sections:
            if self._config.has_option(section, key):
                raw_value = self._config.get(section, key)
                if converter:
                    return converter(raw_value)
                return _auto_convert(raw_value)
        return default

    def set(
        self,
        key: str,
        value: Any,
        section: str,
        auto_save: bool = True,
    ) -> None:
        """Set config value; auto-creates section if needed; auto-saves."""
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, key, str(value))
        if auto_save:
            self.save()

    def has(self, key: str, section: str | None = None) -> bool:
        """Check if key exists (optionally in specific section)."""
        if section:
            return self._config.has_option(section, key)
        return any(self._config.has_option(sec, key) for sec in self._config.sections())

    def get_all_sections_for(self, key: str) -> list[str]:
        """Get all sections that contain the given key."""
        return [sec for sec in self._config.sections() if self._config.has_option(sec, key)]

    def get_section(self, section: str) -> dict[str, Any]:
        """Get all key-value pairs from a section, auto-converted."""
        if not self._config.has_section(section):
            return {}
        result = {}
        for key, value in self._config.items(section):
            result[key] = _auto_convert(value)
        return result


# Singleton instance
_bundle_instance: BundleConfig | None = None


def get_bundle_config() -> BundleConfig:
    """Get or create the singleton BundleConfig instance."""
    global _bundle_instance
    if _bundle_instance is None:
        _bundle_instance = BundleConfig()
    return _bundle_instance
