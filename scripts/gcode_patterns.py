"""Shared G-code regex patterns and layer/skirt parsing helpers."""
from __future__ import annotations

import re

from config import (
    AFTER_LAYER_MARKER,
    LAYER_BEFORE_MARKER,
    LAYER_CHANGE_MARKER,
    LAYER_N_MARKER,
    MARKER,
    TYPE_BRIM,
    TYPE_OUTER_BRIM,
    TYPE_SKIRT,
    TYPE_SKIRT_BRIM,
)

F_RE = re.compile(r"F(\d+)", re.IGNORECASE)
FAN_ON_RE = re.compile(r"^M106\s+S(\d+)", re.IGNORECASE)
PP_FAN_RE = re.compile(r"^M106\s+S\d+\s*;.*postprocess", re.IGNORECASE | re.MULTILINE)
G1_EXTRUDE_RE = re.compile(r"^G1\b.*\bE[-+]?\d", re.IGNORECASE | re.MULTILINE)
RETRACT_RE = re.compile(r"^G1\b.*\bE-", re.IGNORECASE)
MOTION_RE = re.compile(r"^[GM]\d", re.IGNORECASE)
M104_RE = re.compile(r"^M104\s+S(\d+)", re.IGNORECASE)
M109_RE = re.compile(r"^M109\b", re.IGNORECASE | re.MULTILINE)
M204_S_RE = re.compile(r"^M204\s+S(\d+)", re.IGNORECASE)
M420_RE = re.compile(r"^M420\b", re.IGNORECASE)
M900_RE = re.compile(r"^M900\b", re.IGNORECASE | re.MULTILINE)
PA_KLIPPER_RE = re.compile(r"SET_PRESSURE_ADVANCE", re.IGNORECASE)
G28_RE = re.compile(r"^G28\b", re.MULTILINE)
G29_RE = re.compile(r"^G29\b", re.IGNORECASE)
Z_MOVE_RE = re.compile(r"^G0?1\b.*\bZ([\d.]+)", re.MULTILINE | re.I)
LAYER_H_RE = re.compile(r";\s*layer_height\s*[=:]\s*([\d.,]+)", re.IGNORECASE)
LAYER_H_PATH_RE = re.compile(r"_(\d+[,.]\d+)mm_", re.IGNORECASE)
SLICER_TIME_RE = re.compile(r"; estimated printing time[^=\n]*=\s*(.+)", re.IGNORECASE)
PP_SUFFIX_RE = re.compile(
    r"; (?:(?:postprocess(?: cap (?:F|accel)| flow (?:L\d+|normal|bridge|seam)| accel))|"
    r"fan (?:postprocess layer \d+|bridge postprocess|overhang postprocess|"
    r"top postprocess|ironing postprocess|interface postprocess|support postprocess|"
    r"seam postprocess|adhesion postprocess|restore postprocess|"
    r"OFF startup postprocess|capped postprocess)|"
    r"linear advance postprocess|"
    r"postprocess (?:homing|wait hotend|purge|z fix|layer sync|mesh|skirt|layer retract|z hop|"
    r"seam retract|seam end))$",
    re.IGNORECASE,
)


def count_layers(text: str, prusa_cfg: dict[str, str] | None = None) -> int:
    before = text.count(LAYER_BEFORE_MARKER)
    if before:
        lc, bf = text.find(LAYER_CHANGE_MARKER), text.find(LAYER_BEFORE_MARKER)
        return before + (1 if lc >= 0 and bf > lc else 0)
    after = text.count(AFTER_LAYER_MARKER)
    if after:
        return after
    layer_n = text.count(LAYER_N_MARKER)
    if layer_n:
        return layer_n
    lc = text.count(LAYER_CHANGE_MARKER)
    if lc:
        return lc
    if prusa_cfg is None:
        from profile import parse_prusa_config

        prusa_cfg = parse_prusa_config(text)
    for key in ("total_layer_count", "num_layers"):
        if key in prusa_cfg and prusa_cfg[key].isdigit():
            return int(prusa_cfg[key])
    return 0


def has_skirt_or_brim(text: str) -> tuple[bool, bool]:
    low = text[:120000]
    has_skirt = any(
        tag in low
        for tag in (TYPE_SKIRT, TYPE_SKIRT_BRIM, "; SKIRT", ";SKIRT", "; type:skirt")
    )
    has_brim = TYPE_BRIM in low or TYPE_OUTER_BRIM in low
    return has_skirt, has_brim


def is_pp_line(line: str, *, pa_only: bool = False) -> bool:
    stripped = line.strip()
    is_pa = bool(
        "postprocess" in line and (M900_RE.match(stripped) or PA_KLIPPER_RE.search(stripped))
    )
    if pa_only:
        return is_pa
    if is_pa or MARKER in line or stripped.startswith("; postprocessed:"):
        return True
    return bool(PP_SUFFIX_RE.search(stripped))


def strip_pp_lines(lines: list[str], full: bool = False) -> list[str]:
    return [ln for ln in lines if not is_pp_line(ln, pa_only=not full)]
