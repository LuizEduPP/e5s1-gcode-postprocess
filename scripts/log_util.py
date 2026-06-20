"""Log e estado em logs/."""
from __future__ import annotations

import json
from datetime import datetime

from config import LOG_DIR, LOG_FILE, STATE_FILE


def ensure_log_dir() -> None:
    LOG_DIR.mkdir(exist_ok=True)


def log(event: str, message: str = "", echo: bool = True) -> None:
    ensure_log_dir()
    line = f"{datetime.now().isoformat(timespec='seconds')} | {event} | {message}\n"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)
    if echo:
        print(line.rstrip())


def write_state(data: dict) -> None:
    ensure_log_dir()
    STATE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
