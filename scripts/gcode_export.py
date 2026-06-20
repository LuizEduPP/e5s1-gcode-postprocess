"""Recent export discovery for PrusaSlicer temp files."""
from __future__ import annotations

import heapq
import os
import time
from pathlib import Path

from config import MARKER, MARKER_HEAD_BYTES
from profile import EXPORT_SEARCH_DIRS


def _recent_gcode_candidates(folder: Path, now: float, max_age_s: int, max_files: int) -> list[Path]:
    heap: list[tuple[float, int, Path]] = []
    seq = 0
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.is_file() or not entry.name.endswith(".gcode"):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue
                if now - mtime > max_age_s:
                    continue
                seq += 1
                item = (mtime, seq, Path(entry.path))
                if len(heap) < max_files:
                    heapq.heappush(heap, item)
                elif mtime > heap[0][0]:
                    heapq.heapreplace(heap, item)
    except OSError:
        return []
    return [path for _, _, path in sorted(heap, key=lambda item: (-item[0], -item[1]))]


def find_recent_export(max_age_s: int = 300, max_files: int = 5) -> Path | None:
    now = time.time()
    for folder in EXPORT_SEARCH_DIRS:
        if not folder.is_dir():
            continue
        for candidate in _recent_gcode_candidates(folder, now, max_age_s, max_files):
            try:
                with candidate.open(encoding="utf-8", errors="replace") as f:
                    if MARKER in f.read(MARKER_HEAD_BYTES):
                        return candidate
            except OSError:
                continue
    return None


def path_note(path: Path, argv: list[str] | None = None, export: Path | None = None) -> str:
    note = str(path)
    if path.suffix == ".pp" or str(path).endswith(".gcode.pp"):
        note += " (temp PrusaSlicer)"
        final = Path(str(path).removesuffix(".pp"))
        if final.is_file():
            note += f" | final={final}"
        if export:
            note += f" | export={export}"
    if argv and len(argv) > 1:
        note += f" | argv_extra={argv[1:]}"
    return note
