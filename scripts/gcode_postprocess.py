#!/usr/bin/env python3
"""E5S1 G-code post-processor — constants, profile, transform pipeline, and CLI."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast
import heapq
import json
import math
import os
import re
import sys
import time

PROJECT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT / "logs"
STATE_FILE = LOG_DIR / "e5s1_state.json"
LOG_FILE = LOG_DIR / "e5s1_events.log"

MARKER = "; --- E5S1 postprocess ---"
PP_SKIRT = "postprocess skirt"
LAYER_BEFORE_MARKER = ";BEFORE_LAYER_CHANGE"
LAYER_CHANGE_MARKER = ";LAYER_CHANGE"
AFTER_LAYER_MARKER = ";AFTER_LAYER_CHANGE"
LAYER_N_MARKER = ";LAYER:"
LAYER_MARKERS = (LAYER_BEFORE_MARKER, LAYER_CHANGE_MARKER, AFTER_LAYER_MARKER)
LAYER_START_MARKERS = (LAYER_BEFORE_MARKER, AFTER_LAYER_MARKER)

FEAT_SEAM = frozenset({"external", "perimeter"})
FEAT_FAN_TUNE = frozenset({"external", "perimeter", "top", "ironing", "interface", "support", "bottom", "brim"})
FEAT_FAN_BOOST = frozenset({"top", "ironing", "interface", "support", "bottom", "external", "perimeter", "brim", "bridge", "overhang"})
FEAT_COOL = frozenset({"bridge", "overhang"})
FEAT_WALL = frozenset({"external", "perimeter", "gap_fill", "brim"})
FEAT_WALL_CAP = frozenset({"external", "perimeter", "gap_fill"})
FEAT_INFILL = frozenset({"internal", "solid", "support"})
FEAT_PERIMETER = frozenset({"external", "perimeter"})

AXIS_NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"

HEAD_SCAN_BYTES = 8000
SLICER_META_SCAN_BYTES = 32000
MARKER_HEAD_MIN_BYTES = 4096
MARKER_HEAD_BYTES = max(MARKER_HEAD_MIN_BYTES, len(MARKER) + 64)
PA_PROBE_LINES = 800
LARGE_GCODE_BYTES = 2 * 1024 * 1024
METADATA_SCAN_BYTES = 8 * 1024 * 1024
METADATA_MAX_COMMENT_LINES = 100_000
SKIRT_BRIM_SCAN_CHARS = 120_000
BBOX_SCAN_LIMIT = 100_000
PRUSA_CONFIG_SCAN_BYTES = 512 * 1024

PRUSA_CONFIG_BEGIN = "; prusaslicer_config = begin"
PRUSA_CONFIG_END = "; prusaslicer_config = end"
_PRINT_BODY_END_MARKERS = (
    "; filament-specific end gcode",
    ";end gcode for filament",
    PRUSA_CONFIG_BEGIN,
    "; objects_info =",
    "; filament used ",
)
PRUSA_KEY_IRONING = "ironing"
PRUSA_KEY_TOP_SOLID_INFILL_PATTERN = "top_solid_infill_pattern"
PRUSA_KEY_LAYER_HEIGHT = "layer_height"
PRUSA_KEY_FIRST_LAYER_HEIGHT = "first_layer_height"
PRUSA_LAYER_COUNT_KEYS = ("total_layer_count", "num_layers")
PRUSA_CUSTOM_PARAM_KEYS = (
    "custom_parameters_print",
    "custom_parameters_filament",
    "custom_parameters_printer",
)

THUMBNAIL_BEGIN = "; thumbnail begin"
THUMBNAIL_END = "; thumbnail end"
INVALID_MACRO_SNIPPET = "first_layer_height[0]"

ENABLE_MESH_ON_START = "M420 S1 ; postprocess mesh enable\nM420 Z10 ; postprocess mesh fade"
Z_MIN_WARN = 0.35
Z_VALIDATION_LOW_MM = 0.5
LAYER_RETRACT = True
SUPPORT_OVERHANG_MIN = 1

TYPE_TOP_SOLID = ";TYPE:Top solid infill"
TYPE_IRONING = ";TYPE:Ironing"
TYPE_INTERFACE = ";TYPE:Support interface"
TYPE_BOTTOM_SOLID = ";TYPE:Bottom solid infill"
TYPE_EXTERNAL = ";TYPE:External perimeter"
TYPE_PERIMETER = ";TYPE:Perimeter"
TYPE_INTERNAL = ";TYPE:Internal infill"
TYPE_SOLID = ";TYPE:Solid infill"
TYPE_GAP_FILL = ";TYPE:Gap fill"
TYPE_SUPPORT = ";TYPE:Support"
TYPE_SUPPORT_MAT = ";TYPE:Support material"
TYPE_BRIM = ";TYPE:Brim"
TYPE_OUTER_BRIM = ";TYPE:Outer brim"
TYPE_OVERHANG = ";TYPE:Overhang"
TYPE_OVERHANG_BRIDGE = ";TYPE:Overhang bridge"
TYPE_BRIDGE = ";TYPE:Bridge"
TYPE_SKIRT = ";TYPE:Skirt"
TYPE_SKIRT_BRIM = ";TYPE:Skirt/Brim"

BED_X_MIN = 2.0
BED_X_MAX = 218.0
BED_Y_MIN = 2.0
BED_Y_MAX = 218.0
SKIRT_OFFSET_MM = 5.0
SKIRT_OFFSET_SMALL_MM = 2.5
SKIRT_MIN_SIDE_MM = 0.1
STARTUP_SAFE_Z_MM = 10.0
COAST_MIN_REMAIN_E_MM = 0.02
COAST_LAYER_GUARD_LINES = 8

PEEK_SLICER_FAN_WINDOW = 24
PEEK_FAN_GRACE_MOTION = 2
PEEK_RETRACT_WINDOW = 8
OVERHANG_FAN_SKIP_THRESHOLD = 40
LARGE_EXTRUDE_LINE_ESTIMATE_MULT = 50

SMALL_PERIMETER_THRESHOLD_MM = 20.0
SMALL_PERIMETER_SPEED_CAP_F = 900
LOOP_CLOSE_TOL_MM = 0.05
SEAM_JOIN_FLOW_MM = 1.5

SKIRT_OFFSET_SMALL_BBOX_MM = 45.0

COAST_E_MM = 0.35
LAYER_RETRACT_WIPE_MM = 2.0
LAYER_RETRACT_WIPE_E_MM = 0.15
TRAVEL_COAST_MIN_MM = 5.0
TRAVEL_RETRACT_MM = 0.8
TRAVEL_START_BOOST_PCT = 108
TRAVEL_START_BOOST_MM = 2.5
DERETRACT_F = 700
DERETRACT_MAX_E_MM = 0.35
SLICER_DERETRACT_MAX_E_MM = 1.2
FIRST_LAYER_INTERNAL_WALL_FACTOR = 1.15
FIRST_LAYER_INFILL_FACTOR = 1.2

PA_FIRMWARE = "marlin"
PA_K = 0.03
PA_INFILL_SCALE = 1.2
PA_PERIMETER_SCALE = 0.9
PA_BRIDGE_SCALE = 0.5
PA_IRONING_SCALE = 0.2

FAN_PWM_MAX = 255
FLOW_NORMAL_PCT = 100
MM_S_TO_F = 60

NOZZLE_DIAMETER_MM = 0.8
LAYER_HEIGHT_FIRST_MM = 0.24
TEMP_FIRST_LAYER_C = "215"
MAX_VOLUMETRIC_FLOW_MM3_S = 24.0

RETRACT_LENGTH_MM = 1.2
RETRACT_SPEED_MM_S = 45.0
RETRACT_LIFT_MM = 0.4

FAN_OFF_LAYERS = 2
FAN_RAMP_LAYERS = 2
FAN_FULL_LAYER = FAN_OFF_LAYERS + FAN_RAMP_LAYERS + 1
FAN_MIN_PCT = 80
FAN_MAX_PCT = 100
FAN_BRIDGE_PCT = 100
FAN_OVERHANG_PCT = 86
FAN_TOP_PCT = 71
FAN_IRONING_PCT = 35
FAN_INTERFACE_PCT = 78
FAN_SUPPORT_PCT = 78

FLOW_RAMP = (100, 93, 92, 96)
FLOW_BRIDGE_PCT = 95
NOZZLE_WALL_MM_S = 38
NOZZLE_INFILL_MM_S = 75
NOZZLE_CAP_MM_S = 25
NOZZLE_TRAVEL_MM_S = 40
SPEED_FIRST_LAYER_MM_S = 20.0
SPEED_MAX_PRINT_MM_S = 250.0

ACCEL_FIRST_LAYER = 500
ACCEL_DEFAULT = 2000
LAYER_CAP_EXTRUSION = 3
LAYER_FIRST_MOTION = 3

SEAM_EXTRA_RETRACT_MM = 0.4
SEAM_FLOW_PCT = 96
SEAM_FAN_PCT = 85
SEAM_JOIN_SPEED_MM_S = 18.0

SKIRT_LOOPS = 3
SKIRT_SIDE_MM = 40.0
SKIRT_ORIGIN_X_MM = 3.0
SKIRT_ORIGIN_Y_MM = 3.0
SKIRT_LOOP_OFFSET_MM = 2.0
SKIRT_EXTRUSION_MM_PER_MM = 0.1

PURGE_X_START = 2.0
PURGE_X_SECOND = 2.3
PURGE_Y_START = 20.0
PURGE_Y_END = 145.0
PURGE_TRAVEL_F = 5000
PURGE_Z_F = 1500
PURGE_EXTRUDE_F = 1500
PURGE_E_FACTOR = 125.0
PURGE_NOZZLE_MULT = 1.25
PURGE_E_DIVISOR = 2.405
PURGE_E_SECOND_MULT = 2.0

Z_HOP_F = 600
SKIRT_Z_F = 600
SKIRT_TRAVEL_F = 6000
SKIRT_EXTRUDE_F = 600

ENV_E5S1_EXPORT_DIR = "E5S1_EXPORT_DIR"
EXPORT_FOLDER_NAMES = ("Downloads", "Documentos", "Documents")
EXPORT_MAX_AGE_S = 300
EXPORT_MAX_FILES = 5

F_RE = re.compile(r"F(\d+)", re.IGNORECASE)
FAN_ON_RE = re.compile(r"^M106\s+S(\d+)", re.IGNORECASE)
PP_FAN_RE = re.compile(r"^M106\s+S\d+\s*;.*postprocess", re.IGNORECASE | re.MULTILINE)
G1_EXTRUDE_RE = re.compile(r"^G[0-3]\b.*\bE[-+]?\d", re.IGNORECASE | re.MULTILINE)
RETRACT_RE = re.compile(r"^G1\b.*\bE-", re.IGNORECASE)
MOTION_RE = re.compile(r"^[GM]\d", re.IGNORECASE)
M104_RE = re.compile(r"^M104\s+S(\d+)", re.IGNORECASE)
M109_RE = re.compile(r"^M109\b", re.IGNORECASE | re.MULTILINE)
M140_RE = re.compile(r"^M140\b", re.IGNORECASE)
M140_S_RE = re.compile(r"^M140\s+S(\d+)", re.IGNORECASE)
M190_RE = re.compile(r"^M190\b", re.IGNORECASE)
M204_P_RE = re.compile(r"^M204\b.*\bP(\d+)", re.IGNORECASE)
M204_S_RE = re.compile(r"^M204\b.*\bS(\d+)", re.IGNORECASE)
M420_RE = re.compile(r"^M420\b", re.IGNORECASE)
M900_RE = re.compile(r"^M900\b", re.IGNORECASE | re.MULTILINE)
G28_RE = re.compile(r"^G28\b", re.MULTILINE)
G29_RE = re.compile(r"^G29\b", re.IGNORECASE)
G01_LINE_RE = re.compile(r"^G0?1\b", re.I)
G91_RE = re.compile(r"^G91\b", re.I)
G90_RE = re.compile(r"^G90\b", re.I)
Z_VAL_RE = re.compile(rf"\bZ({AXIS_NUM})", re.I)
LAYER_H_RE = re.compile(r";\s*layer_height\s*[=:]\s*([\d.,]+)", re.IGNORECASE)
LAYER_H_PATH_RE = re.compile(r"_(\d+[,.]\d+)mm_", re.IGNORECASE)
SLICER_TIME_RE = re.compile(r"; estimated printing time[^=\n]*=\s*(.+)", re.IGNORECASE)
BED_MESH_RE = re.compile(r"BED_MESH", re.I)
X_VAL_RE = re.compile(rf"\b[Xx]({AXIS_NUM})")
Y_VAL_RE = re.compile(rf"\b[Yy]({AXIS_NUM})")
E_VAL_RE = re.compile(rf"\b[Ee]({AXIS_NUM})")
I_VAL_RE = re.compile(rf"\b[Ii]({AXIS_NUM})")
J_VAL_RE = re.compile(rf"\b[Jj]({AXIS_NUM})")

class E5S1Profile(TypedDict):
    retract_mm: float
    retract_f: int
    retract_lift: float
    fan_off_layers: int
    full_fan_layer: int
    min_fan_pwm: int
    max_fan_pwm: int
    bridge_fan_pwm: int
    bridge_flow_pct: int
    overhang_fan_pwm: int
    top_fan_pwm: int
    ironing_fan_pwm: int
    interface_fan_pwm: int
    support_fan_pwm: int
    seam_extra_retract: float
    seam_flow_pct: int
    seam_fan_pwm: int
    seam_join_f: int
    first_layer_f: int
    wall_early_f: int
    max_infill_f: int
    cap_extrusion_f: int
    max_print_f: int
    default_motion_f: int
    first_layer_accel: int
    default_accel: int
    pa_k: float
    flow_ramp: list[int]
    cap_extrusion_layers: int
    first_layer_motion_layers: int
    skirt_loops: int
    skirt_side_mm: float
    skirt_origin_x_mm: float
    skirt_origin_y_mm: float
    skirt_loop_offset_mm: float
    skirt_extrusion_mm_per_mm: float
    first_layer_height_mm: float
    first_layer_temperature_c: str
    nozzle_diameter_mm: float
    max_volumetric_flow: float

class GcodeAnalysis(TypedDict):
    overhang_markers: int
    has_support: bool
    has_skirt: bool
    has_brim: bool
    needs_support: bool
    layers: int
    top_lines: int
    ironing_lines: int
    interface_lines: int
    has_ironing: bool
    top_pattern: str | None
    extrude_lines: int
    layer_h: float | None
    est_seconds: int | None
    slicer_time: str | None
    lines: int
    large: bool

_ANALYSIS_STAT_KEYS = (
    "layers",
    "lines",
    "overhang_markers",
    "has_support",
    "has_skirt",
    "has_brim",
    "needs_support",
    "top_lines",
    "ironing_lines",
    "interface_lines",
    "has_ironing",
    "top_pattern",
    "extrude_lines",
    "layer_h",
    "est_seconds",
)

class GcodeStats(TypedDict):
    layers: int
    lines: int
    fan_pp: int
    postprocessed: bool
    pressure_advance: bool
    overhang_markers: int
    has_support: bool
    has_skirt: bool
    has_brim: bool
    needs_support: bool
    top_lines: int
    ironing_lines: int
    interface_lines: int
    has_ironing: bool
    top_pattern: str | None
    extrude_lines: int
    layer_h: float | None
    est_seconds: int | None

FAN_PROFILE_KEYS: dict[str, str] = {
    "top": "top_fan_pwm",
    "ironing": "ironing_fan_pwm",
    "interface": "interface_fan_pwm",
    "support": "support_fan_pwm",
}

def pct_to_pwm(pct: int) -> int:
    return max(0, min(FAN_PWM_MAX, int(FAN_PWM_MAX * pct / 100)))

def mm_s_to_f(mm_s: float) -> int:
    """Linear feedrate mm/s → G-code F (mm/min)."""
    return int(mm_s * MM_S_TO_F)

def _parse_custom_parameters(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not raw or raw.strip() in ("", '""', "''"):
        return out
    for line in raw.splitlines():
        for part in line.split(";"):
            part = part.strip().strip('"')
            if " = " in part:
                key, val = part.split(" = ", 1)
                out[key.strip()] = val.strip()
    return out

def _merge_custom_parameters(cfg: dict[str, str]) -> dict[str, str]:
    merged = dict(cfg)
    for key in PRUSA_CUSTOM_PARAM_KEYS:
        merged.update(_parse_custom_parameters(cfg.get(key, "")))
    return merged

def parse_prusa_config(text: str) -> dict[str, str]:
    tail = text[-PRUSA_CONFIG_SCAN_BYTES:] if len(text) > PRUSA_CONFIG_SCAN_BYTES else text
    begin = tail.rfind(PRUSA_CONFIG_BEGIN)
    if begin == -1:
        return {}
    block = tail[begin:]
    end = block.find(PRUSA_CONFIG_END)
    if end != -1:
        block = block[:end]
    out: dict[str, str] = {}
    for line in block.splitlines()[1:]:
        stripped = line.strip()
        if not stripped.startswith(";"):
            break
        body = stripped[1:].strip()
        if " = " not in body:
            continue
        key, val = body.split(" = ", 1)
        out[key.strip()] = val.strip()
    return _merge_custom_parameters(out)

def build_e5s1_profile() -> E5S1Profile:
    """Perfil E5S1 calibrado — sempre hardcoded; ignora bundle e config do slicer."""
    return {
        "retract_mm": RETRACT_LENGTH_MM,
        "retract_f": mm_s_to_f(RETRACT_SPEED_MM_S),
        "retract_lift": RETRACT_LIFT_MM,
        "fan_off_layers": FAN_OFF_LAYERS,
        "full_fan_layer": FAN_FULL_LAYER,
        "min_fan_pwm": pct_to_pwm(FAN_MIN_PCT),
        "max_fan_pwm": pct_to_pwm(FAN_MAX_PCT),
        "bridge_fan_pwm": pct_to_pwm(FAN_BRIDGE_PCT),
        "bridge_flow_pct": FLOW_BRIDGE_PCT,
        "overhang_fan_pwm": pct_to_pwm(FAN_OVERHANG_PCT),
        "top_fan_pwm": pct_to_pwm(FAN_TOP_PCT),
        "ironing_fan_pwm": pct_to_pwm(FAN_IRONING_PCT),
        "interface_fan_pwm": pct_to_pwm(FAN_INTERFACE_PCT),
        "support_fan_pwm": pct_to_pwm(FAN_SUPPORT_PCT),
        "seam_extra_retract": SEAM_EXTRA_RETRACT_MM,
        "seam_flow_pct": SEAM_FLOW_PCT,
        "seam_fan_pwm": pct_to_pwm(SEAM_FAN_PCT),
        "seam_join_f": mm_s_to_f(SEAM_JOIN_SPEED_MM_S),
        "first_layer_f": mm_s_to_f(SPEED_FIRST_LAYER_MM_S),
        "wall_early_f": mm_s_to_f(NOZZLE_WALL_MM_S),
        "max_infill_f": mm_s_to_f(NOZZLE_INFILL_MM_S),
        "cap_extrusion_f": mm_s_to_f(NOZZLE_CAP_MM_S),
        "max_print_f": mm_s_to_f(SPEED_MAX_PRINT_MM_S),
        "default_motion_f": mm_s_to_f(NOZZLE_TRAVEL_MM_S),
        "first_layer_accel": ACCEL_FIRST_LAYER,
        "default_accel": ACCEL_DEFAULT,
        "pa_k": PA_K,
        "flow_ramp": list(FLOW_RAMP),
        "cap_extrusion_layers": LAYER_CAP_EXTRUSION,
        "first_layer_motion_layers": LAYER_FIRST_MOTION,
        "skirt_loops": SKIRT_LOOPS,
        "skirt_side_mm": SKIRT_SIDE_MM,
        "skirt_origin_x_mm": SKIRT_ORIGIN_X_MM,
        "skirt_origin_y_mm": SKIRT_ORIGIN_Y_MM,
        "skirt_loop_offset_mm": SKIRT_LOOP_OFFSET_MM,
        "skirt_extrusion_mm_per_mm": SKIRT_EXTRUSION_MM_PER_MM,
        "first_layer_height_mm": LAYER_HEIGHT_FIRST_MM,
        "first_layer_temperature_c": TEMP_FIRST_LAYER_C,
        "nozzle_diameter_mm": NOZZLE_DIAMETER_MM,
        "max_volumetric_flow": MAX_VOLUMETRIC_FLOW_MM3_S,
    }

def _axis_float(match: re.Match[str] | None) -> float | None:
    if not match:
        return None
    return float(match.group(1))

def _motion_step_mm(line: str, x0: float | None, y0: float | None) -> tuple[float, float | None, float | None]:
    upper = line.strip().upper()
    m_x, m_y = X_VAL_RE.search(upper), Y_VAL_RE.search(upper)
    x1 = _axis_float(m_x) if m_x else x0
    y1 = _axis_float(m_y) if m_y else y0
    if x0 is None or y0 is None or x1 is None or y1 is None:
        return 0.0, x1, y1
    if upper.startswith("G2") or upper.startswith("G3"):
        m_i, m_j = I_VAL_RE.search(upper), J_VAL_RE.search(upper)
        if m_i and m_j:
            i, j = float(m_i.group(1)), float(m_j.group(1))
            cx, cy = x0 + i, y0 + j
            r = math.hypot(i, j)
            if r > 1e-6:
                a0 = math.atan2(y0 - cy, x0 - cx)
                a1 = math.atan2(y1 - cy, x1 - cx)
                da = a1 - a0
                if upper.startswith("G2"):
                    if da > 0:
                        da -= 2 * math.pi
                elif da < 0:
                    da += 2 * math.pi
                return abs(r * da), x1, y1
    return math.hypot(x1 - x0, y1 - y0), x1, y1

def _coast_e_on_line(line: str, coast_e: float, *, min_remain: float = COAST_MIN_REMAIN_E_MM) -> str | None:
    m = E_VAL_RE.search(line)
    if not m:
        return None
    e_val = float(m.group(1))
    if e_val <= 0:
        return None
    if e_val - coast_e < min_remain:
        return None
    new_e = e_val - coast_e
    return E_VAL_RE.sub(f"E{new_e:.5f}", line, count=1)

def _coast_blocked_before_travel(lines: list[str], ext_i: int, travel_i: int) -> bool:
    for j in range(ext_i + 1, travel_i):
        low = lines[j].lower()
        if "wipe_start" in low or "wipe_end" in low:
            return True
        stripped = lines[j].strip()
        if RETRACT_RE.match(stripped):
            return True
        if G91_RE.match(stripped):
            return True
        if "postprocess layer retract" in low or "postprocess retract wipe" in low:
            return True
        if "postprocess travel retract" in low:
            return True
        if any(m in lines[j] for m in LAYER_MARKERS):
            return True
    return False

def uses_before_after_markers(lines: list[str]) -> bool:
    return any(LAYER_BEFORE_MARKER in line or AFTER_LAYER_MARKER in line for line in lines)

def _scan_bbox_start(lines: list[str]) -> int:
    start = 0
    while start < len(lines) and any(m in lines[start] for m in LAYER_MARKERS):
        start += 1
    return start

def _skirt_safe_approach(x0: float, y0: float, z_print: float) -> list[str]:
    return [
        f"G1 Z{STARTUP_SAFE_Z_MM} F{SKIRT_Z_F} ; postprocess safe z",
        f"G1 X{x0:.3f} Y{y0:.3f} F{SKIRT_TRAVEL_F} ; postprocess travel",
        f"G1 Z{z_print:.3f} F{SKIRT_Z_F} ; postprocess skirt",
    ]

def _next_marker_idx(lines: list[str], start: int, marker: str, *, max_forward: int = 40) -> int | None:
    end = min(start + max_forward, len(lines))
    for j in range(start + 1, end):
        if marker in lines[j]:
            return j
    return None

def _slicer_prep_between(lines: list[str], start: int, end: int) -> bool:
    for j in range(start + 1, min(end, len(lines))):
        stripped = lines[j].strip()
        if G91_RE.match(stripped) or RETRACT_RE.match(stripped):
            return True
        if ";WIPE_START" in stripped:
            return True
    return False

def _slicer_layer_prep_before(lines: list[str], idx: int, lookback: int = 24) -> bool:
    layer_change_idx = None
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        if LAYER_CHANGE_MARKER in lines[j]:
            layer_change_idx = j
            break
    if layer_change_idx is not None:
        return _slicer_prep_between(lines, layer_change_idx, idx)
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        if any(m in lines[j] for m in LAYER_MARKERS):
            break
        stripped = lines[j].strip()
        if G91_RE.match(stripped) or RETRACT_RE.match(stripped):
            return True
    return False

def _near_layer_end(lines: list[str], ext_i: int, travel_i: int) -> bool:
    for j in range(ext_i + 1, travel_i + 1):
        low = lines[j].lower()
        if any(m in lines[j] for m in LAYER_MARKERS):
            return True
        if "postprocess layer retract" in low or "wipe_start" in low:
            return True
    return False

def _has_retract_between(lines: list[str], start: int, end: int) -> bool:
    for j in range(start + 1, end):
        stripped = lines[j].strip()
        if RETRACT_RE.match(stripped):
            return True
        low = lines[j].lower()
        if "postprocess travel retract" in low or "postprocess layer retract" in low:
            return True
    return False

def _is_gcode_motion_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        return False
    return stripped.upper().startswith(("G0", "G1", "G2", "G3"))

def _print_body_end(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if PRUSA_CONFIG_BEGIN in line:
            return i
        low = line.lower()
        for marker in _PRINT_BODY_END_MARKERS:
            if marker == PRUSA_CONFIG_BEGIN:
                continue
            if marker in low:
                return i
    return len(lines)

def _coast_travel_body_start(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if AFTER_LAYER_MARKER in line or TYPE_EXTERNAL in line or TYPE_PERIMETER in line:
            return i
    for i, line in enumerate(lines):
        if LAYER_CHANGE_MARKER in line:
            return i + 1
    return head_index(lines, fallback=0)

def analysis_after_transform(base: GcodeAnalysis, result: str, prusa_cfg: dict[str, str]) -> GcodeAnalysis:
    updated = dict(base)
    updated["lines"] = result.count("\n") + (1 if result and not result.endswith("\n") else 0)
    updated["large"] = len(result) > LARGE_GCODE_BYTES
    updated["layers"] = count_layers(result, prusa_cfg)
    _, has_brim = has_skirt_or_brim(result)
    updated["has_brim"] = has_brim
    return updated  # type: ignore[return-value]

def count_layers(text: str, prusa_cfg: dict[str, str]) -> int:
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
    for key in PRUSA_LAYER_COUNT_KEYS:
        if key in prusa_cfg and prusa_cfg[key].isdigit():
            return int(prusa_cfg[key])
    return 0

def has_skirt_or_brim(text: str | list[str]) -> tuple[bool, bool]:
    if isinstance(text, list):
        chunk, chars = [], 0
        for line in text:
            chunk.append(line)
            chars += len(line) + 1
            if chars >= SKIRT_BRIM_SCAN_CHARS:
                break
        low = "\n".join(chunk).lower()
    else:
        low = text[:SKIRT_BRIM_SCAN_CHARS].lower()
    return (
        any(t in low for t in (TYPE_SKIRT.lower(), TYPE_SKIRT_BRIM.lower(), "; skirt", "; type:skirt", PP_SKIRT.lower())),
        TYPE_BRIM.lower() in low or TYPE_OUTER_BRIM.lower() in low,
    )

def is_pp_line(line: str, *, pa_only: bool = False) -> bool:
    stripped = line.strip()
    is_pa = bool(
        "postprocess" in line and M900_RE.match(stripped)
    )
    if pa_only:
        return is_pa
    if is_pa or MARKER in line or stripped.startswith("; postprocessed:"):
        return True
    return bool(";" in stripped and "postprocess" in stripped.split(";", 1)[1].lower())

def strip_pp_lines(lines: list[str], full: bool = False) -> list[str]:
    """Remove postprocess lines. Default (full=False) strips only duplicate M900 PA."""
    return [ln for ln in lines if not is_pp_line(ln, pa_only=not full)]

_TYPE_KIND_ORDER: tuple[tuple[str, str], ...] = (
    (TYPE_IRONING, "ironing"),
    (TYPE_TOP_SOLID, "top"),
    (TYPE_INTERFACE, "interface"),
    (TYPE_SUPPORT_MAT, "support"),
    (TYPE_SUPPORT, "support"),
    (TYPE_BOTTOM_SOLID, "bottom"),
    (TYPE_BRIM, "brim"),
    (TYPE_OUTER_BRIM, "brim"),
    (TYPE_EXTERNAL, "external"),
    (TYPE_GAP_FILL, "gap_fill"),
    (TYPE_PERIMETER, "perimeter"),
    (TYPE_INTERNAL, "internal"),
    (TYPE_SOLID, "solid"),
    (TYPE_OVERHANG_BRIDGE, "overhang"),
    (TYPE_OVERHANG, "overhang"),
    (TYPE_BRIDGE, "bridge"),
)
_TYPE_KIND_EXACT: dict[str, str] = dict(_TYPE_KIND_ORDER)

def type_feature(line: str) -> str | None:
    if ";TYPE:" not in line:
        return None
    stripped = line.strip()
    if stripped in _TYPE_KIND_EXACT:
        return _TYPE_KIND_EXACT[stripped]
    for tag, kind in _TYPE_KIND_ORDER:
        if tag in line:
            return kind
    return "other"

class GCodeBuilder:
    def __init__(self, pa_fw: str = PA_FIRMWARE):
        self.pa_fw = pa_fw

    def timestamp(self, ts: str) -> str:
        return f"; postprocessed: {ts}"

    def flow_layer(self, layer: int, flow: int) -> str:
        return f"M221 S{flow} ; postprocess flow L{layer}"

    def flow_reset(self) -> str:
        return f"M221 S{FLOW_NORMAL_PCT} ; postprocess flow normal"

    def flow_bridge(self, pct: int) -> str:
        return f"M221 S{pct} ; postprocess flow bridge"

    def flow_seam(self, pct: int) -> str:
        return f"M221 S{pct} ; postprocess flow seam"

    def flow_boost(self, pct: int, label: str) -> str:
        return f"M221 S{pct} ; postprocess {label}"

    def seam_extra_retract(self, mm: float, retract_f: int) -> str:
        return f"G1 E-{mm} F{retract_f} ; postprocess seam extra retract"

    def z_hop(self, mm: float) -> str:
        return f"G91\nG1 Z{mm} F{Z_HOP_F} ; postprocess z hop\nG90"

    def layer_retract(self, mm: float, retract_f: int) -> str:
        return f"G1 E-{mm} F{retract_f} ; postprocess layer retract"

    def travel_retract(self, mm: float, retract_f: int) -> str:
        return f"G1 E-{mm} F{retract_f} ; postprocess travel retract"

    def retract_wipe(self, x: float, y: float, dx: float, e: float, retract_f: int) -> str:
        return f"G1 X{x + dx:.3f} Y{y:.3f} E-{e:.3f} F{retract_f} ; postprocess retract wipe"

    def wait_bed(self, temp: str | int) -> str:
        return f"M190 S{temp} ; postprocess wait bed"

    def homing(self) -> str:
        return "G28 ; postprocess homing"

    def absolute_mode(self) -> str:
        return "G90 ; postprocess absolute"

    def wait_hotend(self, temp: str | int) -> str:
        return f"M109 S{temp} ; postprocess wait hotend"

    def mesh_enable(self) -> str:
        return ENABLE_MESH_ON_START

    def purge(self, nozzle_diameter: float = NOZZLE_DIAMETER_MM, first_layer_height: float = LAYER_HEIGHT_FIRST_MM) -> str:
        e_first = PURGE_E_FACTOR * first_layer_height * (nozzle_diameter * PURGE_NOZZLE_MULT) / PURGE_E_DIVISOR
        e_second = e_first * PURGE_E_SECOND_MULT
        return f"""G1 X{PURGE_X_START} Y{PURGE_Y_START} F{PURGE_TRAVEL_F} ; postprocess purge
G1 Z{first_layer_height:.3f} F{PURGE_Z_F} ; postprocess purge
G1 X{PURGE_X_START} Y{PURGE_Y_END} Z{first_layer_height:.3f} F{PURGE_EXTRUDE_F} E{e_first:.2f} ; postprocess purge
G1 X{PURGE_X_SECOND} Y{PURGE_Y_END} Z{first_layer_height:.3f} F{PURGE_TRAVEL_F} ; postprocess purge
G1 X{PURGE_X_SECOND} Y{PURGE_Y_START} Z{first_layer_height:.3f} F{PURGE_EXTRUDE_F} E{e_second:.2f} ; postprocess purge
G92 E0 ; postprocess purge"""

    def z_fix_suffix(self) -> str:
        return " ; postprocess z fix"

    def layer_sync(self) -> str:
        return "G92 E0 ; postprocess layer sync"

    def cap_f_suffix(self) -> str:
        return " ; postprocess cap F"

    def skirt_comment(self) -> str:
        return f"; {PP_SKIRT}"

    def skirt_z(self, z: float) -> str:
        return f"G1 Z{z} F{SKIRT_Z_F} ; {PP_SKIRT}"

    def skirt_travel(self, x: float, y: float, f: int = SKIRT_TRAVEL_F) -> str:
        return f"G1 X{x} Y{y} F{f} ; {PP_SKIRT}"

    def skirt_extrude(self, x: float, y: float, e: float, f: int = SKIRT_EXTRUDE_F) -> str:
        return f"G1 X{x} Y{y} E{e:.2f} F{f} ; {PP_SKIRT}"

    def skirt_reset_e(self) -> str:
        return f"G92 E0 ; {PP_SKIRT}"

    def fan_layer(self, pwm: int, layer: int) -> str:
        return f"M106 S{pwm} ; fan postprocess layer {layer}"

    def fan_command(self, label: str, pwm: int) -> str:
        return f"M106 S{pwm} ; fan {label} postprocess"

    def fan_startup_off(self) -> str:
        return "M106 S0 ; fan OFF startup postprocess"

    def fan_capped(self, pwm: int) -> str:
        return self.fan_command("capped", pwm)

    def fan_restore(self, pwm: int) -> str:
        return self.fan_command("restore", pwm)

    def accel(self, accel: int) -> str:
        return f"M204 P{accel} ; postprocess accel"

    def cap_accel_suffix(self) -> str:
        return " ; postprocess cap accel"

    def pressure_advance(self, pa_k: float) -> str:
        return f"M900 K{pa_k} ; linear advance postprocess"

class GCodeAnalyzer:
    def _slicer_print_time(self, text: str) -> str | None:
        m = SLICER_TIME_RE.search(text)
        return m.group(1).strip() if m else None

    def _slicer_metadata(self, text: str) -> tuple[str | None, float | None]:
        est_raw: str | None = None
        layer_h: float | None = None
        in_thumbnail = False
        pos = 0
        end = min(len(text), METADATA_SCAN_BYTES)
        comment_lines = 0

        while pos < end and comment_lines < METADATA_MAX_COMMENT_LINES:
            nl = text.find("\n", pos)
            if nl == -1 or nl > end:
                line = text[pos:end]
                pos = end
            else:
                line = text[pos:nl]
                pos = nl + 1
            comment_lines += 1
            stripped = line.strip()
            if not stripped.startswith(";"):
                break
            lower = stripped.lower()
            if THUMBNAIL_BEGIN in lower:
                in_thumbnail = True
                continue
            if in_thumbnail:
                if THUMBNAIL_END in lower:
                    in_thumbnail = False
                continue
            if layer_h is None:
                m = LAYER_H_RE.search(line)
                if m:
                    layer_h = float(m.group(1).replace(",", "."))
            if est_raw is None:
                m = SLICER_TIME_RE.search(line)
                if m:
                    est_raw = m.group(1).strip()
            if layer_h is not None and est_raw is not None:
                break

        if est_raw is None and len(text) > SLICER_META_SCAN_BYTES:
            est_raw = self._slicer_print_time(text[-SLICER_META_SCAN_BYTES:])
        return est_raw, layer_h

    def layer_h_from_hint(self, hint: str) -> float | None:
        m = LAYER_H_PATH_RE.search(hint)
        return float(m.group(1).replace(",", ".")) if m else None

    def parse_slicer_seconds(self, time_str: str | None) -> int | None:
        if not time_str:
            return None
        h = m = s = 0
        for part in time_str.split():
            if part.endswith("h"):
                h = int(part[:-1])
            elif part.endswith("m"):
                m = int(part[:-1])
            elif part.endswith("s"):
                s = int(part[:-1])
        return h * 3600 + m * 60 + s

    def count_type_markers(self, text: str, tag: str) -> int:
        return text.count(tag)

    def is_large_gcode(self, text: str) -> bool:
        return len(text) > LARGE_GCODE_BYTES

    def needs_support(self, overhang_markers: int, has_support: bool) -> bool:
        return overhang_markers >= SUPPORT_OVERHANG_MIN and not has_support

    def is_postprocessed(self, text: str) -> bool:
        return MARKER in text

    def count_pp_fan_lines(self, text: str) -> int:
        return len(PP_FAN_RE.findall(text))

    def has_pressure_advance(self, text: str) -> bool:
        return bool(M900_RE.search(text))

    def analyze(self, text: str, hint: str = "", *, prusa_cfg: dict[str, str] | None = None) -> GcodeAnalysis:
        large = self.is_large_gcode(text)
        cfg = prusa_cfg if prusa_cfg is not None else parse_prusa_config(text)
        has_sup = TYPE_SUPPORT in text or TYPE_SUPPORT_MAT in text or TYPE_INTERFACE in text
        has_skirt, has_brim = has_skirt_or_brim(text)
        overhang = self.count_type_markers(text, TYPE_OVERHANG)
        top_lines = self.count_type_markers(text, TYPE_TOP_SOLID)
        ironing_lines = self.count_type_markers(text, TYPE_IRONING)
        interface_lines = self.count_type_markers(text, TYPE_INTERFACE)
        cfg_ironing = cfg.get(PRUSA_KEY_IRONING, "0") not in ("0", "false", "")
        has_ironing = ironing_lines > 0 or cfg_ironing
        top_pattern = cfg.get(PRUSA_KEY_TOP_SOLID_INFILL_PATTERN) or None
        if large:
            extrude_lines = max(text.count("\nG1"), top_lines * LARGE_EXTRUDE_LINE_ESTIMATE_MULT, 1)
        else:
            extrude_lines = sum(1 for ln in text.splitlines() if G1_EXTRUDE_RE.match(ln.strip()))
        est_raw, layer_h = self._slicer_metadata(text)
        if layer_h is None:
            lh = cfg.get(PRUSA_KEY_LAYER_HEIGHT) or cfg.get(PRUSA_KEY_FIRST_LAYER_HEIGHT)
            if lh:
                try:
                    layer_h = float(lh.replace(",", "."))
                except ValueError:
                    pass
        if layer_h is None and hint:
            layer_h = self.layer_h_from_hint(hint)
        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        return {
            "overhang_markers": overhang,
            "has_support": has_sup,
            "has_skirt": has_skirt,
            "has_brim": has_brim,
            "needs_support": self.needs_support(overhang, has_sup),
            "layers": count_layers(text, cfg),
            "top_lines": top_lines,
            "ironing_lines": ironing_lines,
            "interface_lines": interface_lines,
            "has_ironing": has_ironing,
            "top_pattern": top_pattern,
            "extrude_lines": extrude_lines,
            "layer_h": layer_h,
            "est_seconds": self.parse_slicer_seconds(est_raw),
            "slicer_time": est_raw,
            "lines": line_count,
            "large": large,
        }

    def get_stats(self, text: str, analysis: GcodeAnalysis | None = None, fan_pp: int | None = None) -> GcodeStats:
        a = analysis or self.analyze(text)
        return {
            **{k: a[k] for k in _ANALYSIS_STAT_KEYS},
            "fan_pp": fan_pp if fan_pp is not None else self.count_pp_fan_lines(text),
            "postprocessed": self.is_postprocessed(text),
            "pressure_advance": self.has_pressure_advance(text[:HEAD_SCAN_BYTES]),
        }

class GCodeValidator:
    def __init__(self, analyzer: GCodeAnalyzer | None = None):
        self.analyzer = analyzer or GCodeAnalyzer()

    def _startup_text(self, text: str) -> str:
        for marker in LAYER_MARKERS:
            if marker in text:
                return text.split(marker, 1)[0]
        return text

    def validate(self, text: str, expect_postprocess: bool = False, analysis: GcodeAnalysis | None = None) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        analysis = analysis or self.analyzer.analyze(text)
        startup = self._startup_text(text)
        large = analysis["large"]
        pp = self.analyzer.is_postprocessed(text)

        if INVALID_MACRO_SNIPPET in text[:HEAD_SCAN_BYTES] and not pp:
            errors.append("Invalid macro first_layer_height[0] in gcode")

        if expect_postprocess and not pp:
            warnings.append("Missing E5S1 marker — post-process not applied")
        elif expect_postprocess and self.analyzer.count_pp_fan_lines(text) == 0:
            warnings.append("Marker present but no post-process M106 fan commands")

        if not pp:
            if not self.analyzer.has_pressure_advance(text[:HEAD_SCAN_BYTES]):
                warnings.append("No linear advance — corners may blob")
            if not M109_RE.search(startup):
                warnings.append("Purge without M109 — filament may extrude cold")
            if not large and not any(G1_EXTRUDE_RE.match(l.strip()) for l in startup.splitlines()):
                warnings.append("Purge without E extrusion in startup")
            if not large:
                fan_on = sum(
                    1
                    for line in startup.splitlines()
                    if (m := FAN_ON_RE.match(line.strip()))
                    and int(m.group(1)) > 0
                    and "postprocess" not in line
                )
                if fan_on:
                    warnings.append(f"Fan ON ({fan_on}x) before first layer")
                if G29_RE.search(startup) and G28_RE.search(startup):
                    warnings.append("G29 in startup — remove from start gcode if probing hangs")

        if not G28_RE.search(startup):
            warnings.append("No G28 (homing) in file")

        if not large:
            relative = False
            z_low: list[float] = []
            for line in startup.splitlines():
                relative = _coord_relative(line, relative)
                if relative:
                    continue
                z = _z_from_motion_line(line)
                if z is not None and z < Z_VALIDATION_LOW_MM:
                    z_low.append(z)
            if z_low and min(z_low) < Z_MIN_WARN:
                warnings.append(f"Minimum Z {min(z_low):.2f}mm — check Z-offset")

        if not analysis["layers"]:
            warnings.append("No layer change markers")

        if analysis["needs_support"] and not pp:
            warnings.append(
                "Overhangs without support — enable support in slicer; post-process will apply max cooling"
            )
        elif analysis["needs_support"] and pp:
            pass
        elif not pp and not analysis["has_skirt"] and not analysis["has_brim"]:
            warnings.append("No skirt/brim — E5S1 skirt will be injected on post-process")

        return errors, warnings

def cap_f_line(line: str, cap: int, last_f: int, builder: GCodeBuilder) -> tuple[str, bool, int]:
    m = F_RE.search(line)
    if m:
        f_val = int(m.group(1))
        if f_val <= cap:
            return line, False, f_val
        return F_RE.sub(f"F{cap}", line, count=1) + builder.cap_f_suffix(), True, cap
    if last_f <= cap:
        return line, False, last_f
    return line + f" F{cap}{builder.cap_f_suffix()}", True, cap

def speed_cap_for(
    kind: str | None,
    layer_count: int,
    in_startup: bool,
    profile: E5S1Profile,
) -> int | None:
    if kind in ("top", "bottom"):
        return None
    ceiling = profile["max_print_f"]
    if in_startup or layer_count <= 1:
        if kind == "external":
            return min(profile["first_layer_f"], ceiling)
        if kind in FEAT_INFILL:
            return min(int(profile["first_layer_f"] * FIRST_LAYER_INFILL_FACTOR), ceiling)
        if kind in FEAT_WALL:
            return min(int(profile["first_layer_f"] * FIRST_LAYER_INTERNAL_WALL_FACTOR), ceiling)
        return min(profile["first_layer_f"], ceiling)
    if layer_count <= profile["cap_extrusion_layers"]:
        if kind in FEAT_WALL:
            cap = min(profile["wall_early_f"], ceiling)
        else:
            cap = min(profile["cap_extrusion_f"], ceiling)
    elif kind in FEAT_INFILL:
        cap = min(profile["max_infill_f"], ceiling)
    else:
        cap = None
    if kind in FEAT_WALL_CAP and cap is not None:
        cap = min(cap, profile["seam_join_f"])
    elif kind in FEAT_WALL_CAP:
        cap = profile["seam_join_f"]
    return cap

def layer_retract_lines(
    profile: E5S1Profile,
    builder: GCodeBuilder,
    *,
    seam_extra: bool = False,
    last_x: float | None = None,
    last_y: float | None = None,
) -> list[str]:
    lines: list[str] = []
    if profile["retract_lift"] > 0:
        lines.append(builder.z_hop(profile["retract_lift"]))
    lines.append(builder.layer_retract(profile["retract_mm"], profile["retract_f"]))
    if last_x is not None and last_y is not None and LAYER_RETRACT_WIPE_MM > 0:
        lines.append(builder.retract_wipe(last_x, last_y, LAYER_RETRACT_WIPE_MM, LAYER_RETRACT_WIPE_E_MM, profile["retract_f"]))
    if seam_extra and profile["seam_extra_retract"] > 0:
        lines.append(builder.seam_extra_retract(profile["seam_extra_retract"], profile["retract_f"]))
    return lines

def recent_retract(out: list[str], window: int = PEEK_RETRACT_WINDOW) -> bool:
    for line in out[-window:]:
        if not RETRACT_RE.match(line.strip()):
            continue
        if "postprocess" in line.lower():
            return True
    return False

def peek_slicer_fan(lines: list[str], idx: int, window: int = PEEK_SLICER_FAN_WINDOW) -> tuple[int | None, int | None]:
    end = min(idx + 1 + window, len(lines))
    limit = end
    for j in range(idx + 1, end):
        if type_feature(lines[j]) is not None and j > idx + 1:
            limit = j
            break
    motions = 0
    for j in range(idx + 1, limit):
        stripped = lines[j].strip()
        if (m := FAN_ON_RE.match(stripped)) and "postprocess" not in stripped.lower():
            return int(m.group(1)), j
        if MOTION_RE.match(stripped):
            motions += 1
            if motions > PEEK_FAN_GRACE_MOTION:
                break
    return None, None

def e5s1_fan_target_label(
    kind: str,
    layer_count: int,
    layer_fan_cap: int | None,
    profile: E5S1Profile,
    *,
    max_part_cooling: bool = False,
) -> tuple[int, str] | None:
    if pwm_key := FAN_PROFILE_KEYS.get(kind):
        return profile[pwm_key], kind
    if kind in FEAT_SEAM and layer_count > profile["fan_off_layers"]:
        if max_part_cooling:
            return profile["max_fan_pwm"], "max_cooling"
        pwm = min(profile["seam_fan_pwm"], profile["min_fan_pwm"]) if kind == "perimeter" else profile["seam_fan_pwm"]
        return pwm, "seam"
    if kind in (FEAT_SEAM | {"bottom", "brim"}) and layer_count <= profile["fan_off_layers"]:
        if kind in FEAT_SEAM:
            return profile["min_fan_pwm"], "adhesion"
        return (layer_fan_cap if layer_fan_cap is not None else 0), "adhesion"
    return None

def tune_fan_speed(
    out: list[str],
    actions: list[str],
    kind: str,
    lines: list[str],
    idx: int,
    layer_count: int,
    layer_fan_cap: int | None,
    profile: E5S1Profile,
    builder: GCodeBuilder,
    *,
    max_part_cooling: bool = False,
    suppress_fan: bool = False,
) -> int | None:
    if suppress_fan:
        return None
    slicer_fan, fan_idx = peek_slicer_fan(lines, idx)
    target = e5s1_fan_target_label(kind, layer_count, layer_fan_cap, profile, max_part_cooling=max_part_cooling)
    if not target:
        return None
    pwm, label = target
    if slicer_fan == pwm:
        return None
    out.append(builder.fan_command(label, pwm))
    actions.append(f"fan_{label}")
    if fan_idx is not None and slicer_fan is not None and slicer_fan != pwm:
        return fan_idx
    return None

def fan_pwm_for_layer(layer: int, profile: E5S1Profile) -> int | None:
    off = profile["fan_off_layers"]
    ramp_end = profile["full_fan_layer"] - 1
    if layer <= off:
        return 0
    if layer <= ramp_end:
        span = max(1, ramp_end - off)
        step = layer - off
        pwm = max(1, int(profile["min_fan_pwm"] * step / span))
        return min(pwm, profile["max_fan_pwm"])
    return profile["max_fan_pwm"]

def sanitize_startup_line(line: str, first_layer_height_mm: float) -> tuple[str | None, str | None]:
    stripped = line.rstrip("\n\r")
    if INVALID_MACRO_SNIPPET in stripped:
        return stripped.replace(INVALID_MACRO_SNIPPET, str(first_layer_height_mm)), "macro_fixed"
    return stripped, None

def head_index(lines: list[str], fallback: int | None = None) -> int:
    for i, line in enumerate(lines):
        if any(marker in line for marker in LAYER_MARKERS):
            return i
    if fallback is not None:
        return fallback
    return min(len(lines), PA_PROBE_LINES)

def scan_bounding_box(lines: list[str]) -> tuple[float, float, float, float] | None:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    has_moves = False
    start = _scan_bbox_start(lines)
    scan_end = len(lines)
    span = scan_end - start
    if span <= 0:
        return None
    if span <= BBOX_SCAN_LIMIT:
        indices: range = range(start, scan_end)
    else:
        step = max(1, span // BBOX_SCAN_LIMIT)
        indices = range(start, scan_end, step)

    for i in indices:
        stripped = lines[i].strip()
        if not stripped or stripped.startswith(";"):
            continue

        if stripped.upper().startswith(("G1", "G2", "G3")):
            e_match = E_VAL_RE.search(stripped)
            if e_match:
                e_val = e_match.group(1)
                if not e_val.startswith("-") and e_val != "0":
                    x_match = X_VAL_RE.search(stripped)
                    y_match = Y_VAL_RE.search(stripped)
                    if x_match:
                        x = _axis_float(x_match)
                        min_x = min(min_x, x)
                        max_x = max(max_x, x)
                        has_moves = True
                    if y_match:
                        y = _axis_float(y_match)
                        min_y = min(min_y, y)
                        max_y = max(max_y, y)
                        has_moves = True

    if has_moves:
        return min_x, min_y, max_x, max_y
    return None

def _coord_relative(line: str, relative: bool) -> bool:
    stripped = line.strip()
    if G91_RE.match(stripped):
        return True
    if G90_RE.match(stripped):
        return False
    return relative

def _head_relative_mode(head: list[str]) -> bool:
    relative = False
    for line in head:
        relative = _coord_relative(line, relative)
    return relative

def _z_from_motion_line(line: str, *, relative: bool = False) -> float | None:
    if relative:
        return None
    stripped = line.strip()
    if stripped.startswith(";"):
        return None
    head = stripped.split(";", 1)[0].strip()
    if not G01_LINE_RE.match(head):
        return None
    m = Z_VAL_RE.search(head)
    if not m:
        return None
    return float(m.group(1))

def _fix_z_line(line: str, target: float, builder: GCodeBuilder, *, relative: bool = False) -> tuple[str, bool]:
    z = _z_from_motion_line(line, relative=relative)
    if z is None or z >= Z_MIN_WARN:
        return line, False
    head, sep, tail = line.partition(";")
    fixed_head = Z_VAL_RE.sub(rf"Z{target}", head, count=1)
    suffix = f"{sep}{tail}" if sep else ""
    return fixed_head + suffix + builder.z_fix_suffix(), True

def _fix_z_startup_head(head: list[str], target: float, builder: GCodeBuilder) -> tuple[list[str], bool, bool]:
    fixed_head: list[str] = []
    z_changed = False
    relative = False
    for line in head:
        relative = _coord_relative(line, relative)
        low = line.lower()
        if "postprocess" not in low and PP_SKIRT not in low:
            fixed_head.append(line)
            continue
        new_line, line_changed = _fix_z_line(line, target, builder, relative=relative)
        fixed_head.append(new_line)
        if line_changed:
            z_changed = True
    return fixed_head, z_changed, relative

def generate_contour_skirt(profile: E5S1Profile, bbox: tuple[float, float, float, float] | None, builder: GCodeBuilder) -> list[str]:
    z_val = profile["first_layer_height_mm"]
    lines = [builder.skirt_comment()]

    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox
        offset = _skirt_offset_mm(bbox)
        base_x0 = max(BED_X_MIN, min_x - offset)
        base_y0 = max(BED_Y_MIN, min_y - offset)
        base_x1 = min(BED_X_MAX, max_x + offset)
        base_y1 = min(BED_Y_MAX, max_y + offset)
    else:
        base_x0 = profile["skirt_origin_x_mm"]
        base_y0 = profile["skirt_origin_y_mm"]
        base_x1 = base_x0 + profile["skirt_side_mm"]
        base_y1 = base_y0 + profile["skirt_side_mm"]

    lines.extend(_skirt_safe_approach(base_x0, base_y0, z_val))

    for loop in range(profile["skirt_loops"]):
        offset_mm = loop * profile["skirt_loop_offset_mm"]
        x0 = max(BED_X_MIN, base_x0 - offset_mm)
        y0 = max(BED_Y_MIN, base_y0 - offset_mm)
        x1 = min(BED_X_MAX, base_x1 + offset_mm)
        y1 = min(BED_Y_MAX, base_y1 + offset_mm)

        len_x = x1 - x0
        len_y = y1 - y0

        if len_x <= SKIRT_MIN_SIDE_MM or len_y <= SKIRT_MIN_SIDE_MM:
            continue

        segment_e_x = len_x * profile["skirt_extrusion_mm_per_mm"]
        segment_e_y = len_y * profile["skirt_extrusion_mm_per_mm"]
        lines.extend(
            [
                builder.skirt_travel(x0, y0),
                builder.skirt_extrude(x1, y0, segment_e_x),
                builder.skirt_extrude(x1, y1, segment_e_y),
                builder.skirt_extrude(x0, y1, segment_e_x),
                builder.skirt_extrude(x0, y0, segment_e_y),
            ]
        )
    lines.append(builder.skirt_reset_e())
    return lines

def _bbox_side_mm(bbox: tuple[float, float, float, float]) -> float:
    min_x, min_y, max_x, max_y = bbox
    return max(max_x - min_x, max_y - min_y)

def _skirt_offset_mm(bbox: tuple[float, float, float, float] | None) -> float:
    if bbox is not None and _bbox_side_mm(bbox) < SKIRT_OFFSET_SMALL_BBOX_MM:
        return SKIRT_OFFSET_SMALL_MM
    return SKIRT_OFFSET_MM

def _segment_cumulative_dist(region: list[str], seg: list[int]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    cum = 0.0
    last_x, last_y = None, None
    for idx in seg:
        step, x, y = _motion_step_mm(region[idx], last_x, last_y)
        if step > 0:
            cum += step
        out.append((idx, cum))
        last_x, last_y = x, y
    return out

def _comment_prefix_len(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if MOTION_RE.match(line.strip()):
            return i
    return len(lines)

def _line_index(lines: list[str], pattern: re.Pattern[str]) -> int | None:
    for i, line in enumerate(lines):
        if pattern.search(line.strip()):
            return i
    return None

def _insert_after(lines: list[str], idx: int | None, line: str) -> None:
    insert_idx = (idx + 1) if idx is not None else _comment_prefix_len(lines)
    for part in reversed(line.split("\n")):
        lines.insert(insert_idx, part)

def _insert_skirt_block(head: list[str], block: list[str]) -> list[str]:
    idx = len(head)
    for i, line in enumerate(head):
        if "postprocess purge" in line.lower():
            idx = i + 1
        elif M109_RE.match(line.strip()):
            idx = max(idx, i + 1)
    return head[:idx] + block + head[idx:]

def _normalize_startup_order(head: list[str]) -> list[str]:
    prefix = _comment_prefix_len(head)
    comments = head[:prefix]
    motion = head[prefix:]
    buckets: dict[str, list[str]] = {
        "bed_heat": [],
        "g28": [],
        "mesh": [],
        "heat": [],
        "purge": [],
        "skirt": [],
        "other": [],
    }
    for line in motion:
        low = line.lower()
        if PP_SKIRT in low or "postprocess safe z" in low or "postprocess travel" in low:
            buckets["skirt"].append(line)
            continue
        if M140_RE.match(line.strip()) or M190_RE.match(line.strip()):
            buckets["bed_heat"].append(line)
        elif G28_RE.search(line.strip()):
            buckets["g28"].append(line)
        elif G29_RE.search(line.strip()) or M420_RE.match(line.strip()) or "postprocess mesh" in low or "bed_mesh" in low:
            buckets["mesh"].append(line)
        elif M109_RE.match(line.strip()) or M104_RE.match(line.strip()):
            buckets["heat"].append(line)
        elif "postprocess purge" in low:
            buckets["purge"].append(line)
        else:
            buckets["other"].append(line)
    return (
        comments
        + buckets["bed_heat"]
        + buckets["g28"]
        + buckets["mesh"]
        + buckets["heat"]
        + buckets["purge"]
        + buckets["other"]
        + buckets["skirt"]
    )

def repair_startup(
    lines: list[str],
    profile: E5S1Profile,
    builder: GCodeBuilder,
    actions: list[str],
) -> tuple[list[str], int]:
    h_idx = head_index(lines)
    head, tail = list(lines[:h_idx]), lines[h_idx:]
    changed = False
    if not G28_RE.search("\n".join(head)):
        head.insert(_comment_prefix_len(head), builder.homing())
        actions.append("g28_added")
        changed = True
    head_join = "\n".join(head).upper()
    g28_idx = _line_index(head, G28_RE)
    if g28_idx is not None and "M420" not in head_join and "G29" not in head_join and "BED_MESH" not in head_join:
        _insert_after(head, g28_idx, builder.mesh_enable())
        actions.append("mesh_enabled")
        changed = True
    bed_temp: str | None = None
    for line in head:
        if m := M140_S_RE.match(line.strip()):
            bed_temp = m.group(1)
            break
    if bed_temp and not M190_RE.search("\n".join(head)):
        m140_idx = _line_index(head, M140_RE)
        _insert_after(head, m140_idx, builder.wait_bed(bed_temp))
        actions.append("m190_added")
        changed = True
    if not M109_RE.search("\n".join(head)):
        hotend_c = profile["first_layer_temperature_c"]
        for line in head:
            if m := M104_RE.match(line.strip()):
                hotend_c = m.group(1)
        mesh_idx = _line_index(head, M420_RE) or _line_index(head, BED_MESH_RE)
        _insert_after(head, mesh_idx if mesh_idx is not None else g28_idx, builder.wait_hotend(hotend_c))
        actions.append("m109_added")
        changed = True
    if not any(G1_EXTRUDE_RE.match(line.strip()) for line in head):
        purge_at = _line_index(head, M109_RE)
        purge_block = builder.purge(profile["nozzle_diameter_mm"], profile["first_layer_height_mm"])
        if _head_relative_mode(head):
            purge_block = f"{builder.absolute_mode()}\n{purge_block}"
            actions.append("g90_before_purge")
        _insert_after(head, purge_at, purge_block)
        actions.append("purge_added")
        changed = True
    fixed_head, z_changed, _ = _fix_z_startup_head(head, profile["first_layer_height_mm"], builder)
    head = fixed_head
    if z_changed:
        actions.append("z_fix")
        changed = True
    has_skirt, has_brim = has_skirt_or_brim(lines)
    bbox = scan_bounding_box(tail)
    normalized_head = _normalize_startup_order(head)
    if normalized_head != head:
        actions.append("startup_order")
        head = normalized_head
        changed = True
    insert_at = head_index(head)
    if not has_skirt and not has_brim and not any(PP_SKIRT in line for line in lines):
        skirt_block = generate_contour_skirt(profile, bbox, builder)
        if _head_relative_mode(head):
            skirt_block = [builder.absolute_mode(), *skirt_block]
            actions.append("g90_before_skirt")
        head = head[:insert_at] + skirt_block + head[insert_at:]
        actions.append(f"skirt_added×{profile['skirt_loops']}")
        changed = True
    result = head + tail if changed else lines
    return result, len(head)

def _segment_closed(region: list[str], seg: list[int]) -> bool:
    sx = sy = lx = ly = None
    for idx in seg:
        upper = region[idx].upper()
        if not upper.startswith(("G0", "G1", "G2", "G3")):
            continue
        m_x, m_y = X_VAL_RE.search(upper), Y_VAL_RE.search(upper)
        x, y = _axis_float(m_x), _axis_float(m_y)
        if x is None or y is None:
            continue
        if sx is None:
            sx, sy = x, y
        lx, ly = x, y
    if sx is None or lx is None:
        return False
    return math.hypot(lx - sx, ly - sy) <= LOOP_CLOSE_TOL_MM

def _collect_perimeter_segments(
    region: list[str],
) -> list[tuple[list[int], float, int, bool, str]]:
    segments: list[tuple[list[int], float, int, bool, str]] = []
    in_perimeter = False
    curr_seg: list[int] = []
    curr_dist = 0.0
    curr_kind = "perimeter"
    last_x, last_y = None, None
    layer_num = 0

    for i, line in enumerate(region):
        if any(m in line for m in LAYER_MARKERS):
            layer_num += 1
        feat = type_feature(line)
        if feat in FEAT_PERIMETER:
            if curr_seg:
                segments.append((curr_seg, curr_dist, layer_num, _segment_closed(region, curr_seg), curr_kind))
            in_perimeter = True
            curr_kind = feat
            curr_seg = []
            curr_dist = 0.0
        elif feat is not None:
            in_perimeter = False
            if curr_seg:
                segments.append((curr_seg, curr_dist, layer_num, _segment_closed(region, curr_seg), curr_kind))
                curr_seg = []

        upper = line.upper()
        if upper.startswith(("G0", "G1", "G2", "G3")):
            m_e = E_VAL_RE.search(upper)
            e_val = m_e.group(1) if m_e else None
            is_extrude = bool(e_val is not None and not e_val.startswith("-") and e_val != "0")
            step, x, y = _motion_step_mm(line, last_x, last_y)

            if in_perimeter and is_extrude:
                if not curr_seg:
                    curr_dist = 0.0
                elif step > 0:
                    curr_dist += step
                curr_seg.append(i)
            elif curr_seg:
                segments.append((curr_seg, curr_dist, layer_num, _segment_closed(region, curr_seg), curr_kind))
                curr_seg = []

            last_x, last_y = x, y

    if curr_seg:
        segments.append((curr_seg, curr_dist, layer_num, _segment_closed(region, curr_seg), curr_kind))
    return segments

def _feature_before(lines: list[str], idx: int, lookback: int = 24) -> str | None:
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        feat = type_feature(lines[j])
        if feat is not None:
            return feat
    return None

def _feature_after(lines: list[str], idx: int, lookahead: int = 24) -> str | None:
    for j in range(idx + 1, min(idx + lookahead, len(lines))):
        feat = type_feature(lines[j])
        if feat is not None:
            return feat
    return None

def _infill_long_travel(lines: list[str], ext_i: int, travel_i: int, travel_mm: float) -> bool:
    if travel_mm < TRAVEL_COAST_MIN_MM:
        return False
    if _near_layer_end(lines, ext_i, travel_i):
        return False
    if _coast_blocked_before_travel(lines, ext_i, travel_i):
        return False
    if _active_wall_feature(lines, ext_i) or _wall_travel_target(lines, travel_i):
        return False
    src = _feature_before(lines, ext_i)
    dst = _feature_after(lines, travel_i)
    if src in FEAT_WALL or dst in FEAT_WALL:
        return False
    return src in FEAT_INFILL and dst in FEAT_INFILL

def repair_perimeter_seam_join(
    lines: list[str],
    profile: E5S1Profile,
    builder: GCodeBuilder,
    actions: list[str],
    *,
    body_start: int | None = None,
) -> list[str]:
    start = body_start if body_start is not None else head_index(lines)
    region = lines[start:]
    inject_before: dict[int, list[str]] = {}
    inject_after: dict[int, list[str]] = {}
    overrides: dict[int, str] = {}
    join_f = profile["seam_join_f"]
    seam_flow = profile["seam_flow_pct"]
    joined = 0

    for seg, dist, _layer, closed, kind in _collect_perimeter_segments(region):
        if not closed or not seg:
            continue
        i1 = seg[-1]
        overrides[i1] = cap_f_line(region[i1], join_f, join_f, builder)[0] + " ; postprocess loop close cap"
        joined += 1
        if kind == "external" and seam_flow < FLOW_NORMAL_PCT:
            cum = _segment_cumulative_dist(region, seg)
            join_start = next((idx for idx, d in cum if dist - d <= SEAM_JOIN_FLOW_MM), None)
            if join_start is not None:
                inject_before.setdefault(join_start, []).append(
                    builder.flow_seam(seam_flow),
                )
                inject_after.setdefault(i1, []).append(builder.flow_reset())

    if not joined:
        return lines

    out = list(region)
    for idx in sorted(overrides, reverse=True):
        out[idx] = overrides[idx]
    for idx in sorted(inject_after, reverse=True):
        for ln in reversed(inject_after[idx]):
            out.insert(idx + 1, ln)
    for idx in sorted(inject_before, reverse=True):
        for ln in reversed(inject_before[idx]):
            out.insert(idx, ln)
    actions.append(f"perimeter_seam_join×{joined}")
    return lines[:start] + out

def repair_small_perimeters(
    lines: list[str],
    builder: GCodeBuilder,
    actions: list[str],
    *,
    body_start: int | None = None,
) -> list[str]:
    start = body_start if body_start is not None else head_index(lines)
    region = lines[start:]
    overrides: dict[int, str] = {}
    capped = 0

    for seg, dist, _layer, closed, _kind in _collect_perimeter_segments(region):
        if closed or dist >= SMALL_PERIMETER_THRESHOLD_MM or not seg:
            continue
        i0 = seg[0]
        line, _, _ = cap_f_line(region[i0], SMALL_PERIMETER_SPEED_CAP_F, SMALL_PERIMETER_SPEED_CAP_F, builder)
        overrides[i0] = line + " ; postprocess small perimeter speed cap"
        capped += 1

    if not capped:
        return lines

    out = list(region)
    for idx in sorted(overrides, reverse=True):
        out[idx] = overrides[idx]
    actions.append(f"small_perimeters_fixed×{capped}")
    return lines[:start] + out

def repair_coast(lines: list[str], actions: list[str]) -> list[str]:
    out = list(lines)
    coasted = 0
    for i in range(len(out) - 1, 0, -1):
        if "postprocess layer retract" not in out[i].lower():
            continue
        for j in range(i - 1, max(i - 24, -1), -1):
            stripped = out[j].strip()
            if not G1_EXTRUDE_RE.match(stripped):
                continue
            if "postprocess coast" in out[j]:
                break
            new_line = _coast_e_on_line(out[j], COAST_E_MM)
            if new_line:
                out[j] = new_line + " ; postprocess coast"
                coasted += 1
            break
    if coasted:
        actions.append(f"coast×{coasted}")
    return out

def repair_travel_coast(lines: list[str], actions: list[str]) -> list[str]:
    out = list(lines)
    body_start = _coast_travel_body_start(out)
    body_end = _print_body_end(out)
    last_x, last_y = None, None
    last_ext_i: int | None = None
    coasted = 0
    for i in range(body_start, body_end):
        line = out[i]
        if any(m in line for m in LAYER_MARKERS):
            last_ext_i = None
            continue
        if not _is_gcode_motion_line(line):
            continue
        upper = line.strip().upper()
        low = line.lower()
        if "postprocess purge" in low or PP_SKIRT in low:
            continue
        m_e = E_VAL_RE.search(upper)
        e_val = float(m_e.group(1)) if m_e else 0.0
        is_extrude = e_val > COAST_MIN_REMAIN_E_MM
        step, x, y = _motion_step_mm(line, last_x, last_y)
        if is_extrude:
            last_ext_i = i
        elif last_ext_i is not None:
            ext_i = cast(int, last_ext_i)
            if "postprocess coast" not in out[ext_i]:
                if _infill_long_travel(out, ext_i, i, step):
                    new_line = _coast_e_on_line(out[ext_i], COAST_E_MM)
                    if new_line:
                        out[ext_i] = new_line + " ; postprocess coast travel"
                        coasted += 1
            last_ext_i = None
        if x is not None:
            last_x = x
        if y is not None:
            last_y = y
    if coasted:
        actions.append(f"coast_travel×{coasted}")
    return out

def repair_travel_retract(
    lines: list[str],
    profile: E5S1Profile,
    builder: GCodeBuilder,
    actions: list[str],
) -> list[str]:
    out = list(lines)
    body_start = _coast_travel_body_start(out)
    body_end = _print_body_end(out)
    last_x, last_y = None, None
    last_ext_i: int | None = None
    retracted = 0
    for i in range(body_start, body_end):
        line = out[i]
        low = line.lower()
        if "postprocess purge" in low or PP_SKIRT in low:
            continue
        if any(m in line for m in LAYER_MARKERS):
            last_ext_i = None
            continue
        if not _is_gcode_motion_line(line):
            continue
        upper = line.strip().upper()
        m_e = E_VAL_RE.search(upper)
        e_val = float(m_e.group(1)) if m_e else 0.0
        is_extrude = e_val > COAST_MIN_REMAIN_E_MM
        step, x, y = _motion_step_mm(line, last_x, last_y)
        if is_extrude:
            last_ext_i = i
        elif last_ext_i is not None:
            ext_i = cast(int, last_ext_i)
            if _infill_long_travel(out, ext_i, i, step) and not _has_retract_between(out, ext_i, i):
                out.insert(
                    i,
                    builder.travel_retract(TRAVEL_RETRACT_MM, profile["retract_f"]),
                )
                retracted += 1
                i += 1
            last_ext_i = None
        if x is not None:
            last_x = x
        if y is not None:
            last_y = y
    if retracted:
        actions.append(f"travel_retract×{retracted}")
    return out

def _travel_mm_before_extrusion(lines: list[str], idx: int, lookback: int = 24) -> float:
    total = 0.0
    lx, ly = None, None
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        if any(m in lines[j] for m in LAYER_MARKERS):
            break
        stripped = lines[j].strip()
        if G1_EXTRUDE_RE.match(stripped):
            m = E_VAL_RE.search(stripped.upper())
            if m and float(m.group(1)) > COAST_MIN_REMAIN_E_MM:
                if X_VAL_RE.search(stripped.upper()) or Y_VAL_RE.search(stripped.upper()):
                    break
        step, x, y = _motion_step_mm(lines[j], lx, ly)
        if x is not None:
            lx = x
        if y is not None:
            ly = y
        total += step
    return total

def repair_travel_start_boost(
    lines: list[str],
    builder: GCodeBuilder,
    actions: list[str],
) -> list[str]:
    out = list(lines)
    body_start = _coast_travel_body_start(out)
    body_end = _print_body_end(out)
    boosted = 0
    i = body_start
    while i < body_end:
        line = out[i]
        low = line.lower()
        if any(m in line for m in LAYER_MARKERS):
            i += 1
            continue
        if "postprocess skirt" in low or "postprocess purge" in low:
            i += 1
            continue
        stripped = line.strip()
        if not G1_EXTRUDE_RE.match(stripped):
            i += 1
            continue
        m_e = E_VAL_RE.search(stripped.upper())
        if not m_e or float(m_e.group(1)) <= COAST_MIN_REMAIN_E_MM:
            i += 1
            continue
        if _travel_mm_before_extrusion(out, i) < TRAVEL_COAST_MIN_MM:
            i += 1
            continue
        if _near_layer_start(out, i) or _active_wall_feature(out, i):
            i += 1
            continue
        if _feature_before(out, i) not in FEAT_INFILL:
            i += 1
            continue
        out.insert(i, builder.flow_boost(TRAVEL_START_BOOST_PCT, "travel start boost"))
        boosted += 1
        i += 1
        remain = TRAVEL_START_BOOST_MM
        lx, ly = None, None
        boost_end = i - 1
        while i < body_end and remain > 0:
            cur = out[i]
            if any(m in cur for m in LAYER_MARKERS):
                break
            cur_stripped = cur.strip()
            if not G1_EXTRUDE_RE.match(cur_stripped):
                i += 1
                continue
            cm = E_VAL_RE.search(cur_stripped.upper())
            if not cm or float(cm.group(1)) <= COAST_MIN_REMAIN_E_MM:
                break
            step, x, y = _motion_step_mm(cur, lx, ly)
            if x is not None:
                lx = x
            if y is not None:
                ly = y
            remain -= step
            boost_end = i
            i += 1
        out.insert(boost_end + 1, builder.flow_reset())
        i = boost_end + 2
    if boosted:
        actions.append(f"travel_start_boost×{boosted}")
    return out

def _e_only_positive(line: str) -> float | None:
    stripped = line.strip().upper()
    if not stripped.startswith("G1"):
        return None
    m_e = E_VAL_RE.search(stripped)
    if not m_e:
        return None
    e_val = float(m_e.group(1))
    if e_val <= 0:
        return None
    if X_VAL_RE.search(stripped) or Y_VAL_RE.search(stripped) or Z_VAL_RE.search(stripped):
        return None
    return e_val

def _near_layer_start(lines: list[str], idx: int, lookback: int = 16) -> bool:
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        if AFTER_LAYER_MARKER in lines[j] or LAYER_CHANGE_MARKER in lines[j]:
            return True
        if LAYER_BEFORE_MARKER in lines[j]:
            return False
    return False

def _active_wall_feature(lines: list[str], idx: int, lookback: int = 12) -> bool:
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        feat = type_feature(lines[j])
        if feat in FEAT_SEAM:
            return True
        if feat is not None and feat not in FEAT_SEAM:
            return False
    return False

def _wall_travel_target(lines: list[str], travel_i: int, lookahead: int = 16) -> bool:
    for j in range(travel_i + 1, min(travel_i + lookahead, len(lines))):
        if any(m in lines[j] for m in LAYER_MARKERS):
            return False
        if type_feature(lines[j]) in FEAT_SEAM:
            return True
        stripped = lines[j].strip()
        if G1_EXTRUDE_RE.match(stripped):
            m = E_VAL_RE.search(stripped.upper())
            if m and float(m.group(1)) > COAST_MIN_REMAIN_E_MM:
                return _active_wall_feature(lines, j)
    return False

def _after_slicer_wipe(lines: list[str], idx: int, lookback: int = 16) -> bool:
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        low = lines[j].lower()
        if "wipe_end" in low:
            return True
        if any(m in lines[j] for m in LAYER_MARKERS):
            return False
        stripped = lines[j].strip()
        if G1_EXTRUDE_RE.match(stripped):
            m = E_VAL_RE.search(stripped.upper())
            if m and float(m.group(1)) > COAST_MIN_REMAIN_E_MM:
                return False
    return False

def _after_layer_travel(lines: list[str], idx: int, lookback: int = 20) -> bool:
    if _e_only_positive(lines[idx]) is None:
        return False
    seen_z_up = False
    for j in range(idx - 1, max(idx - lookback, -1), -1):
        low = lines[j].lower()
        if AFTER_LAYER_MARKER in lines[j] or "wipe_end" in low:
            return True
        if LAYER_BEFORE_MARKER in lines[j]:
            return False
        upper = lines[j].strip().upper()
        if upper.startswith("G1") and " Z" in upper:
            zm = Z_VAL_RE.search(upper)
            if zm and float(zm.group(1)) >= 0.4:
                seen_z_up = True
        if seen_z_up and G1_EXTRUDE_RE.match(lines[j].strip()):
            m = E_VAL_RE.search(upper)
            if m and float(m.group(1)) > COAST_MIN_REMAIN_E_MM:
                return False
    return False

def _slow_deretract_line(
    out: list[str],
    idx: int,
    *,
    max_e: float,
) -> bool:
    if "deretract slow" in out[idx].lower():
        return False
    e_val = _e_only_positive(out[idx])
    if e_val is None or e_val > max_e:
        return False
    head = out[idx].split(";", 1)[0].rstrip()
    if F_RE.search(head):
        head = F_RE.sub(f"F{DERETRACT_F}", head, count=1)
    else:
        head = f"{head} F{DERETRACT_F}"
    out[idx] = f"{head} ; postprocess deretract slow"
    return True

def repair_deretract(lines: list[str], actions: list[str]) -> list[str]:
    out = list(lines)
    slowed = 0
    i = 0
    while i < len(out):
        low = out[i].lower()
        if "postprocess" in low and "e-" in low and RETRACT_RE.match(out[i].strip()):
            for j in range(i + 1, min(i + 16, len(out))):
                stripped = out[j].strip()
                if not G1_EXTRUDE_RE.match(stripped):
                    continue
                m = E_VAL_RE.search(stripped)
                if not m:
                    break
                if float(m.group(1)) <= 0:
                    break
                if _slow_deretract_line(out, j, max_e=DERETRACT_MAX_E_MM):
                    slowed += 1
                break
        elif ((_after_slicer_wipe(out, i)
                or (_travel_mm_before_extrusion(out, i) >= TRAVEL_COAST_MIN_MM
                    and not _active_wall_feature(out, i)))
                and not _after_layer_travel(out, i)
                and not _near_layer_start(out, i)) and _slow_deretract_line(
            out, i, max_e=SLICER_DERETRACT_MAX_E_MM,
        ):
            slowed += 1
        i += 1
    if slowed:
        actions.append(f"deretract_slow×{slowed}")
    return out

def _clean_stale_slicer_retract_block(block: list[str]) -> tuple[list[str], int]:
    cleaned: list[str] = []
    removed = 0
    skip_until = 0
    for bi, ln in enumerate(block):
        if bi < skip_until:
            continue
        if ln.strip().startswith(";WIPE_START"):
            prev = bi - 1
            while prev >= 0 and not block[prev].strip():
                prev -= 1
            if prev >= 0 and _stale_slicer_retract(block[prev]):
                if cleaned and _stale_slicer_retract(cleaned[-1]):
                    cleaned.pop()
                    removed += 1
            end = bi + 1
            while end < len(block) and ";WIPE_END" not in block[end]:
                end += 1
            skip_until = min(end + 1, len(block))
            removed += 1
            continue
        if _stale_slicer_retract(ln):
            removed += 1
            continue
        cleaned.append(ln)
    return cleaned, removed

def _pp_retract_after_layer_change(lines: list[str], layer_change_idx: int, before_idx: int) -> bool:
    for j in range(layer_change_idx + 1, before_idx):
        if "postprocess layer retract" in lines[j].lower():
            return True
    return False

def repair_stale_layer_gap(lines: list[str], actions: list[str]) -> list[str]:
    """Drop slicer retract/wipe between LAYER_CHANGE and BEFORE when PP already retracted."""
    out = list(lines)
    removed = 0
    i = 0
    while i < len(out):
        if LAYER_CHANGE_MARKER not in out[i]:
            i += 1
            continue
        before_idx = _next_marker_idx(out, i, LAYER_BEFORE_MARKER)
        if before_idx is None:
            i += 1
            continue
        if not _pp_retract_after_layer_change(out, i, before_idx):
            i = before_idx
            continue
        cleaned, r = _clean_stale_slicer_retract_block(out[i + 1 : before_idx])
        removed += r
        out = out[: i + 1] + cleaned + out[before_idx:]
        i = before_idx
    if removed:
        actions.append(f"stale_layer_gap×{removed}")
    return out

def _pp_retract_before_marker(lines: list[str], marker_idx: int, lookback: int = 32) -> bool:
    for j in range(marker_idx - 1, max(marker_idx - lookback, -1), -1):
        if "postprocess layer retract" in lines[j].lower():
            return True
        if LAYER_CHANGE_MARKER in lines[j]:
            break
    return False

def _stale_slicer_retract(line: str) -> bool:
    low = line.lower()
    if any(k in low for k in (
        "postprocess layer retract",
        "postprocess retract wipe",
        "postprocess travel retract",
        "postprocess z hop",
    )):
        return False
    stripped = line.strip()
    if not RETRACT_RE.match(stripped):
        return False
    if X_VAL_RE.search(stripped) or Y_VAL_RE.search(stripped):
        return False
    m = E_VAL_RE.search(stripped.upper())
    return m is not None and abs(float(m.group(1))) <= 1.5

def repair_stale_layer_wipe(lines: list[str], actions: list[str]) -> list[str]:
    """Drop slicer end-of-layer retract/wipe between BEFORE and AFTER when PP already retracted."""
    out: list[str] = []
    removed = 0
    i = 0
    n = len(lines)
    while i < n:
        if LAYER_BEFORE_MARKER not in lines[i]:
            out.append(lines[i])
            i += 1
            continue
        after_end = i + 1
        while after_end < n and AFTER_LAYER_MARKER not in lines[after_end]:
            after_end += 1
        if after_end >= n:
            out.extend(lines[i:])
            break
        block = lines[i : after_end + 1]
        if _pp_retract_before_marker(lines, i):
            cleaned, removed_block = _clean_stale_slicer_retract_block(block)
            removed += removed_block
            out.extend(cleaned)
        else:
            out.extend(block)
        i = after_end + 1
    if removed:
        actions.append(f"stale_wipe_removed×{removed}")
    return out

def repair_layer_marker(
    lines: list[str],
    builder: GCodeBuilder,
    actions: list[str],
    prusa_cfg: dict[str, str],
) -> list[str]:
    before_count = after_count = change_count = 0
    for line in lines:
        if LAYER_BEFORE_MARKER in line:
            before_count += 1
        if AFTER_LAYER_MARKER in line:
            after_count += 1
        if LAYER_CHANGE_MARKER in line:
            change_count += 1

    if before_count == 0 and after_count > 0:
        patched: list[str] = []
        for line in lines:
            if AFTER_LAYER_MARKER in line:
                if not patched or patched[-1].strip() != LAYER_BEFORE_MARKER:
                    patched.append(LAYER_BEFORE_MARKER)
                    patched.append(builder.layer_sync())
                    actions.append("layer_marker")
            patched.append(line)
        return patched
    if before_count == 0 and change_count > 0:
        sync = builder.layer_sync()
        patched = []
        for line in lines:
            if LAYER_CHANGE_MARKER in line and (not patched or patched[-1].strip() != sync):
                patched.append(sync)
                actions.append("layer_marker")
            patched.append(line)
        return patched
    if count_layers("\n".join(lines), prusa_cfg) == 0:
        patched = list(lines)
        for i, line in enumerate(patched):
            if LAYER_N_MARKER in line:
                patched[i:i] = [LAYER_BEFORE_MARKER, builder.layer_sync()]
                actions.append("layer_marker")
                break
        return patched
    return lines

def inject_pa(lines: list[str], pa_fw: str, pa_k: float, builder: GCodeBuilder | None = None) -> tuple[list[str], str | None]:
    if not pa_k or pa_fw == "none":
        return lines, None
    builder = builder or GCodeBuilder(pa_fw)
    head = lines[:head_index(lines)]
    if any(M900_RE.match(line.strip()) for line in head):
        return lines, None
    extrusion_idx = next(
        (i for i in range(len(head) - 1, -1, -1) if G1_EXTRUDE_RE.match(head[i].strip())),
        None,
    )
    if extrusion_idx is None:
        m109 = [i for i, line in enumerate(head) if M109_RE.match(line.strip())]
        if not m109:
            return lines, None
        extrusion_idx = m109[-1]
    cmd = builder.pressure_advance(pa_k)
    return lines[:extrusion_idx + 1] + [cmd] + lines[extrusion_idx + 1:], f"pa_{pa_fw}_{pa_k}"

class TransformContext:
    def __init__(
        self,
        profile: E5S1Profile,
        builder: GCodeBuilder,
        skip_overhang_fan: bool,
        layer_h: float | None = None,
        *,
        has_before_after_markers: bool = True,
        max_part_cooling: bool = False,
    ):
        self.profile = profile
        self.builder = builder
        self.skip_overhang_fan = skip_overhang_fan
        self.max_part_cooling = max_part_cooling
        self.uses_before_after_markers = has_before_after_markers
        self.layer_h = layer_h or LAYER_HEIGHT_FIRST_MM
        self.out: list[str] = []
        self.actions: list[str] = []
        self.layer_count = 0
        self.in_startup = True
        self.layer_fan_cap: int | None = None
        self.boost_fan = False
        self.cool_boost = False
        self.flow_bridge = False
        self.seam_flow = False
        self.surface_kind: str | None = None
        self.pending_surface_clear = False
        self.last_f = profile["default_motion_f"]
        self.last_pa_k: float | None = None
        self.last_x: float | None = None
        self.last_y: float | None = None
        self.skip_fan_at: set[int] = set()
        self.current_line = ""
        self.current_upper = ""

    def update_line(self, line: str) -> None:
        self.current_line = line
        self.current_upper = line.upper()

    def reset_flow(self) -> None:
        if self.flow_bridge or self.seam_flow:
            self.out.append(self.builder.flow_reset())
            self.actions.append("flow_reset")
            self.flow_bridge = False
            self.seam_flow = False

    def apply_pa(self, feat: str) -> None:
        if self.builder.pa_fw != PA_FIRMWARE or self.profile["pa_k"] <= 0:
            return
        scale = 1.0
        if feat in FEAT_SEAM:
            scale = PA_PERIMETER_SCALE
        elif feat in ("internal", "solid"):
            scale = PA_INFILL_SCALE
        elif feat in FEAT_COOL:
            scale = PA_BRIDGE_SCALE
        elif feat == "ironing":
            scale = PA_IRONING_SCALE
        k = round(self.profile["pa_k"] * scale, 4)
        if k == self.last_pa_k:
            return
        self.out.append(self.builder.pressure_advance(k))
        self.actions.append(f"pa_dynamic_K{k}")
        self.last_pa_k = k

    def restore_layer_fan(self) -> None:
        if self.layer_fan_cap is not None:
            self.out.append(self.builder.fan_restore(self.layer_fan_cap))
            self.actions.append("fan_restore")

    def begin_layer(self, stripped: str) -> None:
        self.layer_count += 1
        cap = fan_pwm_for_layer(self.layer_count, self.profile)
        if self.max_part_cooling and self.layer_count > self.profile["fan_off_layers"]:
            cap = self.profile["max_fan_pwm"]
        self.out.append(stripped)
        ramp = self.profile["flow_ramp"]
        if self.layer_count <= len(ramp):
            flow = ramp[self.layer_count - 1]
            self.out.append(self.builder.flow_layer(self.layer_count, flow))
            self.actions.append(f"flow_l{self.layer_count}_S{flow}")
        elif self.layer_count == len(ramp) + 1:
            self.out.append(self.builder.flow_reset())
            self.actions.append("flow_reset")
        if cap is not None:
            self.out.append(self.builder.fan_layer(cap, self.layer_count))
            self.actions.append(f"fan_l{self.layer_count}_pwm_{cap}")
        if self.layer_count <= self.profile["first_layer_motion_layers"]:
            self.out.append(self.builder.accel(self.profile["first_layer_accel"]))
            self.actions.append(f"accel_l{self.layer_count}")
        elif self.layer_count == self.profile["first_layer_motion_layers"] + 1:
            self.out.append(self.builder.accel(self.profile["default_accel"]))
            self.actions.append(f"accel_default_l{self.layer_count}")
        self.layer_fan_cap = cap

def transform_speed_tracking(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    if ctx.current_upper.startswith(("G0", "G1", "G2", "G3")):
        if fm := F_RE.search(ctx.current_line):
            ctx.last_f = int(fm.group(1))
        m_x, m_y = X_VAL_RE.search(ctx.current_upper), Y_VAL_RE.search(ctx.current_upper)
        if m_x:
            ctx.last_x = _axis_float(m_x)
        if m_y:
            ctx.last_y = _axis_float(m_y)
    return False

def transform_startup_line(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    if ctx.in_startup:
        fixed, fix_action = sanitize_startup_line(ctx.current_line, ctx.profile["first_layer_height_mm"])
        if fix_action:
            ctx.actions.append(fix_action)
        if fixed is None:
            return True
        if fixed != ctx.current_line:
            ctx.update_line(fixed)
    return False

def transform_header(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    if ctx.current_line.startswith("; generated by"):
        ctx.out += [ctx.current_line, ctx.builder.timestamp(datetime.now().isoformat(timespec="seconds")), MARKER]
        ctx.actions.append("header")
        return True
    return False

def transform_feature_type(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    feat = type_feature(ctx.current_line)
    if feat is not None:
        ctx.pending_surface_clear = False
    if feat in FEAT_COOL:
        if ctx.cool_boost:
            ctx.restore_layer_fan()
        ctx.reset_flow()
        ctx.out.append(ctx.current_line)
        if feat == "bridge":
            ctx.out.append(ctx.builder.flow_bridge(ctx.profile["bridge_flow_pct"]))
            ctx.actions.append("flow_bridge")
            ctx.flow_bridge = True
            ctx.out.append(ctx.builder.fan_command("bridge", ctx.profile["bridge_fan_pwm"]))
            ctx.actions.append("fan_bridge")
        elif not ctx.skip_overhang_fan or ctx.max_part_cooling:
            pwm = ctx.profile["max_fan_pwm"] if ctx.max_part_cooling else ctx.profile["overhang_fan_pwm"]
            ctx.out.append(ctx.builder.fan_command("overhang", pwm))
            ctx.actions.append("fan_overhang" if not ctx.max_part_cooling else "fan_max_cooling")
        ctx.apply_pa(feat)
        ctx.boost_fan = True
        ctx.cool_boost = True
        ctx.surface_kind = feat
        return True

    if feat is not None:
        ctx.reset_flow()
        if ctx.cool_boost:
            ctx.restore_layer_fan()
            ctx.cool_boost = False

        ctx.boost_fan = feat in FEAT_FAN_BOOST

        ctx.apply_pa(feat)

        if feat in FEAT_FAN_TUNE:
            ctx.out.append(ctx.current_line)
            skip_idx = tune_fan_speed(
                ctx.out, ctx.actions, feat, lines, idx, ctx.layer_count, ctx.layer_fan_cap, ctx.profile, ctx.builder,
                max_part_cooling=ctx.max_part_cooling,
            )
            if skip_idx:
                ctx.skip_fan_at.add(skip_idx)
            ctx.surface_kind = feat
            return True

        if feat == "other":
            ctx.out.append(ctx.current_line)
            ctx.surface_kind = None
            ctx.boost_fan = False
            return True

        ctx.out.append(ctx.current_line)
        ctx.surface_kind = feat
        return True

    return False

def transform_ironing_fan(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    fan_m = FAN_ON_RE.match(ctx.current_line)
    if ctx.surface_kind == "ironing" and fan_m and "postprocess" not in ctx.current_line.lower():
        pwm = int(fan_m.group(1))
        if pwm != ctx.profile["ironing_fan_pwm"]:
            ctx.out.append(ctx.builder.fan_command("ironing", ctx.profile["ironing_fan_pwm"]))
            ctx.actions.append("fan_ironing")
        else:
            ctx.out.append(ctx.current_line)
        return True
    return False

def transform_layer_boundary(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    if AFTER_LAYER_MARKER in ctx.current_line and ctx.uses_before_after_markers:
        ctx.in_startup = False
        if ctx.cool_boost:
            ctx.restore_layer_fan()
        ctx.reset_flow()
        ctx.boost_fan = False
        ctx.cool_boost = False
        ctx.pending_surface_clear = True
        ctx.out.append(ctx.current_line)
        return True
    if LAYER_BEFORE_MARKER in ctx.current_line:
        ctx.in_startup = False
        if ctx.cool_boost:
            ctx.restore_layer_fan()
        ctx.reset_flow()
        if LAYER_RETRACT and ctx.layer_count >= 1 and not recent_retract(ctx.out):
            if not ctx.uses_before_after_markers and not _slicer_layer_prep_before(lines, idx):
                seam_extra = ctx.surface_kind in FEAT_SEAM
                ctx.out.extend(layer_retract_lines(
                    ctx.profile, ctx.builder, seam_extra=seam_extra, last_x=ctx.last_x, last_y=ctx.last_y,
                ))
                ctx.actions.append("retract_layer")
                if seam_extra and ctx.profile["seam_extra_retract"] > 0:
                    ctx.actions.append("seam_extra_retract")
        ctx.boost_fan = False
        ctx.cool_boost = False
        ctx.pending_surface_clear = True
        ctx.begin_layer(ctx.current_line)
        return True
    if AFTER_LAYER_MARKER in ctx.current_line:
        ctx.in_startup = False
        if ctx.cool_boost:
            ctx.restore_layer_fan()
        ctx.reset_flow()
        ctx.boost_fan = False
        ctx.cool_boost = False
        ctx.pending_surface_clear = True
        ctx.begin_layer(ctx.current_line)
        return True
    if LAYER_CHANGE_MARKER in ctx.current_line:
        ctx.in_startup = False
        if not ctx.uses_before_after_markers or ctx.layer_count == 0:
            if ctx.cool_boost:
                ctx.restore_layer_fan()
            ctx.reset_flow()
            ctx.boost_fan = False
            ctx.cool_boost = False
            ctx.pending_surface_clear = True
            ctx.begin_layer(ctx.current_line)
        else:
            ctx.out.append(ctx.current_line)
        return True
    return False

def transform_accel_cap(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    if not (1 <= ctx.layer_count <= LAYER_FIRST_MOTION):
        return False
    cap_accel = ctx.profile["first_layer_accel"]
    stripped = ctx.current_line.strip()
    m_p = M204_P_RE.match(stripped)
    if m_p:
        if int(m_p.group(1)) > cap_accel:
            ctx.out.append(
                re.sub(r"\bP\d+\b", f"P{cap_accel}", ctx.current_line, count=1, flags=re.I)
                + ctx.builder.cap_accel_suffix()
            )
            ctx.actions.append(f"m204_cap_l{ctx.layer_count}")
        else:
            ctx.out.append(ctx.current_line)
        return True
    m_s = M204_S_RE.match(stripped)
    if m_s:
        if int(m_s.group(1)) > cap_accel:
            ctx.out.append(
                re.sub(r"\bS\d+\b", f"S{cap_accel}", ctx.current_line, count=1, flags=re.I)
                + ctx.builder.cap_accel_suffix()
            )
            ctx.actions.append(f"m204_cap_l{ctx.layer_count}")
        else:
            ctx.out.append(ctx.current_line)
        return True
    return False

def transform_fan_cap(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    fan_m = FAN_ON_RE.match(ctx.current_line)
    if ctx.in_startup and fan_m and int(fan_m.group(1)) > 0:
        ctx.out.append(ctx.builder.fan_startup_off())
        ctx.actions.append("fan_off_startup")
        return True
    if ctx.layer_fan_cap is not None and fan_m and not ctx.boost_fan and int(fan_m.group(1)) > ctx.layer_fan_cap:
        ctx.out.append(ctx.builder.fan_capped(ctx.layer_fan_cap))
        ctx.actions.append("fan_cap")
        return True
    return False

def transform_speed_cap(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    fan_m = FAN_ON_RE.match(ctx.current_line)
    if (
        ctx.current_upper.startswith(("G0", "G1", "G2", "G3"))
        and G1_EXTRUDE_RE.match(ctx.current_line)
        and not fan_m
    ):
        if ctx.pending_surface_clear:
            ctx.surface_kind = None
            ctx.pending_surface_clear = False
        if _e_only_positive(ctx.current_line) is not None:
            ctx.out.append(ctx.current_line)
            return True
        f_cap = speed_cap_for(ctx.surface_kind, ctx.layer_count, ctx.in_startup, ctx.profile)

        w = ctx.profile["nozzle_diameter_mm"]
        h = ctx.profile["first_layer_height_mm"] if (ctx.layer_count <= 1 or ctx.in_startup) else ctx.layer_h
        volume_per_mm = w * h
        if volume_per_mm > 0:
            max_speed_mm_s = ctx.profile["max_volumetric_flow"] / volume_per_mm
            flow_cap_f = int(max_speed_mm_s * MM_S_TO_F)
            if f_cap is None or flow_cap_f < f_cap:
                f_cap = flow_cap_f

        if f_cap is not None:
            new_line, capped, last_f = cap_f_line(ctx.current_line, f_cap, ctx.last_f, ctx.builder)
            ctx.out.append(new_line)
            ctx.last_f = last_f
            if capped:
                ctx.actions.append(f"cap_flow_l{ctx.layer_count or 'startup'}")
            return True
    return False

def transform_travel_cap(ctx: TransformContext, _lines: list[str], _idx: int) -> bool:
    fan_m = FAN_ON_RE.match(ctx.current_line)
    if (
        ctx.current_upper.startswith(("G0", "G1", "G2", "G3"))
        and not G1_EXTRUDE_RE.match(ctx.current_line)
        and not fan_m
        and " Z" not in ctx.current_upper
    ):
        cap = ctx.profile["default_motion_f"]
        new_line, capped, last_f = cap_f_line(ctx.current_line, cap, ctx.last_f, ctx.builder)
        ctx.out.append(new_line)
        ctx.last_f = last_f
        if capped:
            ctx.actions.append("cap_travel")
        return True
    return False

def transform_gcode(
    lines: list[str],
    *,
    analysis: GcodeAnalysis,
    prusa_cfg: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    profile = build_e5s1_profile()
    pa_fw = PA_FIRMWARE
    need_sup = analysis["needs_support"]
    skip_overhang_fan = analysis["large"] and analysis["overhang_markers"] > OVERHANG_FAN_SKIP_THRESHOLD and not need_sup
    cfg = prusa_cfg if prusa_cfg is not None else {}

    uses_before_after = uses_before_after_markers(lines)

    builder = GCodeBuilder(pa_fw)
    ctx = TransformContext(
        profile,
        builder,
        skip_overhang_fan,
        analysis["layer_h"],
        has_before_after_markers=uses_before_after,
        max_part_cooling=need_sup,
    )

    transformers = [
        transform_speed_tracking,
        transform_startup_line,
        transform_header,
        transform_feature_type,
        transform_ironing_fan,
        transform_layer_boundary,
        transform_accel_cap,
        transform_fan_cap,
        transform_speed_cap,
        transform_travel_cap,
    ]

    for i, line in enumerate(lines):
        if i in ctx.skip_fan_at:
            continue

        ctx.update_line(line.rstrip("\n\r"))
        handled = False
        for transformer in transformers:
            if transformer(ctx, lines, i):
                handled = True
                break

        if not handled:
            ctx.out.append(ctx.current_line)

    repair_actions: list[str] = []
    out = ctx.out
    out, body_start = repair_startup(out, profile, builder, repair_actions)
    out = repair_perimeter_seam_join(out, profile, builder, repair_actions, body_start=body_start)
    out = repair_small_perimeters(out, builder, repair_actions, body_start=body_start)
    out = repair_coast(out, repair_actions)
    out = repair_travel_coast(out, repair_actions)
    out = repair_travel_retract(out, profile, builder, repair_actions)
    out = repair_travel_start_boost(out, builder, repair_actions)
    out = repair_deretract(out, repair_actions)
    out = repair_stale_layer_wipe(out, repair_actions)
    out = repair_stale_layer_gap(out, repair_actions)
    out = repair_layer_marker(out, builder, repair_actions, cfg)
    ctx.actions.extend(repair_actions)
    out = strip_pp_lines(out)
    out, pa_action = inject_pa(out, pa_fw, profile["pa_k"], builder)
    if pa_action:
        ctx.actions.append(pa_action)
    if skip_overhang_fan:
        ctx.actions.append(f"fan_overhang_skip×{analysis['overhang_markers']}")
    elif need_sup:
        ctx.actions.append("max_part_cooling")
    return out, ctx.actions

def _export_search_dirs() -> tuple[Path, ...]:
    dirs = [Path.home() / name for name in EXPORT_FOLDER_NAMES]
    extra = os.environ.get(ENV_E5S1_EXPORT_DIR, "").strip()
    if extra:
        dirs.append(Path(extra))
    return tuple(dirs)

EXPORT_SEARCH_DIRS = _export_search_dirs()

class RecentExportFinder:
    def _recent_gcode_candidates(
        self,
        folder: Path,
        now: float,
        max_age_s: int,
        max_files: int,
        warnings: list[str],
    ) -> list[Path]:
        heap: list[tuple[float, int, Path]] = []
        seq = 0
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if not entry.is_file() or not entry.name.endswith(".gcode"):
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                    except OSError as exc:
                        warnings.append(f"export stat failed {entry.path}: {exc}")
                        continue
                    if now - mtime > max_age_s:
                        continue
                    seq += 1
                    item = (mtime, seq, Path(entry.path))
                    if len(heap) < max_files:
                        heapq.heappush(heap, item)
                    elif mtime > heap[0][0]:
                        heapq.heapreplace(heap, item)
        except OSError as exc:
            warnings.append(f"export scan skipped {folder}: {exc}")
            return []
        return [path for _, _, path in sorted(heap, key=lambda item: (-item[0], -item[1]))]

    def find_recent_export(
        self,
        max_age_s: int = EXPORT_MAX_AGE_S,
        max_files: int = EXPORT_MAX_FILES,
    ) -> tuple[Path | None, list[str]]:
        warnings: list[str] = []
        now = time.time()
        for folder in EXPORT_SEARCH_DIRS:
            if not folder.is_dir():
                continue
            for candidate in self._recent_gcode_candidates(folder, now, max_age_s, max_files, warnings):
                try:
                    with candidate.open(encoding="utf-8", errors="replace") as f:
                        if MARKER in f.read(MARKER_HEAD_BYTES):
                            return candidate, warnings
                except OSError as exc:
                    warnings.append(f"export read failed {candidate}: {exc}")
                    continue
        return None, warnings

    def path_note(self, path: Path, argv: list[str] | None = None, export: Path | None = None) -> str:
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

class StateLogger:
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

class DefaultLogger:
    def __init__(self, state_logger: StateLogger, analyzer: GCodeAnalyzer):
        self.state_logger = state_logger
        self.analyzer = analyzer

    def format_actions(self, actions: list[str]) -> str:
        if not actions:
            return "none"
        counts: dict[str, int] = {}
        order: list[str] = []
        for action in actions:
            if action not in counts:
                order.append(action)
                counts[action] = 0
            counts[action] += 1
        return "[" + ", ".join(f"{a}×{counts[a]}" if counts[a] > 1 else a for a in order) + "]"

    def log_result(
        self,
        event: str,
        note: str,
        errors: list[str],
        warnings: list[str],
        text: str,
        quiet: bool,
        extra: list[str] | None = None,
        analysis: GcodeAnalysis | None = None,
    ) -> None:
        parts = [note, f"stats={self.analyzer.get_stats(text, analysis=analysis)}"] + (extra or [])
        if warnings:
            parts.append(f"warnings={warnings}")
        if errors:
            parts.append(f"errors={errors}")
        label = event if event.endswith("SKIP") else f"{event} {'FAIL' if errors else ('WARN' if warnings else 'OK')}"
        self.state_logger.log(label, " | ".join(parts), echo=not quiet)

    def log_state_warn(self, msg: str, quiet: bool) -> None:
        if not quiet:
            self.state_logger.log("STATE WARN", msg)

    def log_fail(self, note: str, quiet: bool) -> None:
        self.state_logger.log("POSTPROCESS FAIL", note, echo=not quiet)

class PostProcessApp:
    def __init__(
        self,
        logger: DefaultLogger | None = None,
        analyzer: GCodeAnalyzer | None = None,
        validator: GCodeValidator | None = None,
        export_finder: RecentExportFinder | None = None,
        state_logger: StateLogger | None = None,
    ):
        self.analyzer = analyzer or GCodeAnalyzer()
        self.validator = validator or GCodeValidator(self.analyzer)
        self.export_finder = export_finder or RecentExportFinder()
        self.state_logger = state_logger or StateLogger()

        if logger is None:
            self.logger = DefaultLogger(self.state_logger, self.analyzer)
        else:
            self.logger = logger

    def run(self, paths: list[Path], quiet: bool = False, force: bool = False, argv: list[str] | None = None) -> int:
        code = 0

        for path in paths:
            start = time.monotonic()
            if not path.is_file():
                self.logger.log_fail(f"{path} | file not found", quiet)
                code = 1
                continue

            raw = path.read_text(encoding="utf-8", errors="replace")
            hint = " ".join(str(p) for p in [path] if p)

            if self.analyzer.is_postprocessed(raw) and not force:
                prusa_cfg = parse_prusa_config(raw)
                analysis = self.analyzer.analyze(raw, hint, prusa_cfg=prusa_cfg)
                errors, warnings = self.validator.validate(raw, expect_postprocess=True, analysis=analysis)
                self.logger.log_result(
                    "POSTPROCESS SKIP",
                    self.export_finder.path_note(path, argv),
                    errors,
                    warnings,
                    raw,
                    quiet,
                    ["skipped=already_processed"],
                    analysis,
                )
                code |= bool(errors)
                continue

            prusa_cfg = parse_prusa_config(raw)
            analysis = self.analyzer.analyze(raw, hint, prusa_cfg=prusa_cfg)
            lines = strip_pp_lines(raw.splitlines(), full=force)
            new_lines, actions = transform_gcode(lines, analysis=analysis, prusa_cfg=prusa_cfg)

            result = "\n".join(new_lines) + "\n"
            path.write_text(result, encoding="utf-8")

            export = None
            try:
                export, export_warnings = self.export_finder.find_recent_export()
                for warning in export_warnings:
                    self.logger.log_state_warn(warning, quiet)
                hint = " ".join(str(p) for p in [path, export] if p)
            except OSError as e:
                self.logger.log_state_warn(str(e), quiet)

            result_analysis = analysis_after_transform(analysis, result, prusa_cfg)
            errors, warnings = self.validator.validate(result, expect_postprocess=True, analysis=result_analysis)
            try:
                state_data = {
                    **{k: v for k, v in result_analysis.items() if v is not None and k != "large"},
                    "last_path": str(path),
                    "last_export": str(export or "")
                }
                self.state_logger.write_state(state_data)
            except OSError as e:
                self.logger.log_state_warn(str(e), quiet)

            extra = [
                f"slicer={result_analysis['slicer_time'] or '?'}",
                f"actions={self.logger.format_actions(actions)}",
                f"pp={int((time.monotonic() - start) * 1000)}ms",
                f"{path.stat().st_size // 1024}KB",
            ]

            self.logger.log_result(
                "POSTPROCESS",
                self.export_finder.path_note(path, argv, export),
                errors,
                warnings,
                result,
                quiet,
                extra,
                result_analysis,
            )
            code |= bool(errors)
        return code

def run_postprocess(paths: list[Path], quiet: bool = False, force: bool = False, argv: list[str] | None = None) -> int:
    return PostProcessApp().run(paths, quiet, force, argv)

if __name__ == "__main__":
    cli_argv = sys.argv[1:]
    cli_force = "--force" in cli_argv or "-f" in cli_argv
    cli_paths = [Path(p) for p in cli_argv if not p.startswith("-")]
    sys.exit(PostProcessApp().run(cli_paths, quiet=True, force=cli_force, argv=cli_argv))
