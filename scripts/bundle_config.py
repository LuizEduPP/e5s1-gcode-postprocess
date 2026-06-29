"""Dynamic config loader for bundle.ini (no hardcoded sections)."""
from __future__ import annotations

import abc
import configparser
from pathlib import Path
from typing import Any


def _auto_cast(value: str) -> Any:
    """Cast string to appropriate type (int/float/bool/str)."""
    value = value.strip()
    lower = value.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


class IBundleConfig(abc.ABC):
    @property
    @abc.abstractmethod
    def sections(self) -> list[str]:
        pass

    @abc.abstractmethod
    def load(self) -> None:
        pass

    @abc.abstractmethod
    def save(self, path: Path | str | None = None) -> None:
        pass

    @abc.abstractmethod
    def get(self, key: str, default: Any = None, section_priority: list[str] | None = None, converter: Any = None) -> Any:
        pass

    @abc.abstractmethod
    def has(self, key: str, section: str | None = None) -> bool:
        pass

    @abc.abstractmethod
    def set(self, key: str, value: Any, section: str = "defaults", auto_save: bool = True) -> None:
        pass


class BundleConfig(IBundleConfig):
    def __init__(self, path: Path | str | None = None):
        self._config = configparser.ConfigParser(allow_no_value=True)
        self._config.optionxform = str  # Preserve case

        if path:
            self._config_path = Path(path).resolve()
        else:
            self._config_path = self._find_path()

        if self._config_path and self._config_path.exists():
            self.load()

    @property
    def sections(self) -> list[str]:
        return self._config.sections()

    def _find_path(self) -> Path | None:
        """Find bundle.ini or .bundle.ini in common locations."""
        search = [
            Path.cwd(),
            Path(__file__).resolve().parent.parent,
            Path.home(),
        ]
        for d in search:
            for name in ("bundle.ini", ".bundle.ini"):
                p = d / name
                if p.exists():
                    return p
        return None

    def load(self) -> None:
        if self._config_path:
            self._config.read(self._config_path, encoding="utf-8")

    def save(self, path: Path | str | None = None) -> None:
        """Save to disk (create file if missing, default to project root)."""
        p = Path(path).resolve() if path else self._config_path
        if not p:
            p = Path(__file__).resolve().parent.parent / "bundle.ini"

        p.parent.mkdir(exist_ok=True, parents=True)
        with open(p, "w", encoding="utf-8") as f:
            self._config.write(f)
        self._config_path = p

    def get(
        self,
        key: str,
        default: Any = None,
        section_priority: list[str] | None = None,
        converter: Any = None,
    ) -> Any:
        """Get config value, checking sections in priority order."""
        sections = section_priority or [
            *[s for s in self._config.sections() if s.startswith("print:")],
            *[s for s in self._config.sections() if s.startswith("filament:")],
            *[s for s in self._config.sections() if s.startswith("printer:")],
            *[s for s in self._config.sections() if not s.startswith(("print:", "filament:", "printer:"))],
            "defaults",
        ]
        for s in sections:
            if self._config.has_option(s, key):
                value = self._config.get(s, key)
                return converter(value) if converter else _auto_cast(value)
        return default

    def has(
        self,
        key: str,
        section: str | None = None,
    ) -> bool:
        """Check if key exists (optionally in a specific section)."""
        if section:
            return self._config.has_option(section, key)
        return any(self._config.has_option(s, key) for s in self._config.sections())

    def set(
        self,
        key: str,
        value: Any,
        section: str = "defaults",
        auto_save: bool = True,
    ) -> None:
        """Set config value and save automatically (default to [defaults] section)."""
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, key, str(value))
        if auto_save:
            self.save()


class BundleConfigFactory:
    _instance: IBundleConfig | None = None

    @classmethod
    def get_instance(cls) -> IBundleConfig:
        if cls._instance is None:
            cls._instance = BundleConfig()
        return cls._instance


def get_bundle_config() -> IBundleConfig:
    return BundleConfigFactory.get_instance()
