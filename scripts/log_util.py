"""Log e estado em logs/."""
from __future__ import annotations

import abc
import json
from datetime import datetime

from config import LOG_DIR, LOG_FILE, STATE_FILE


class IStateLogger(abc.ABC):
    @abc.abstractmethod
    def log(self, event: str, message: str = "", echo: bool = True) -> None:
        pass

    @abc.abstractmethod
    def write_state(self, data: dict) -> None:
        pass


class StateLogger(IStateLogger):
    def __init__(self):
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)

    def log(self, event: str, message: str = "", echo: bool = True) -> None:
        self._ensure_log_dir()
        line = f"{datetime.now().isoformat(timespec='seconds')} | {event} | {message}\n"
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
        if echo:
            print(line.rstrip())

    def write_state(self, data: dict) -> None:
        self._ensure_log_dir()
        STATE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class LoggerFactory:
    _instance: IStateLogger | None = None

    @classmethod
    def get_instance(cls) -> IStateLogger:
        if cls._instance is None:
            cls._instance = StateLogger()
        return cls._instance



