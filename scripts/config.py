"""E5S1 infrastructure constants — paths, markers, TYPE tags."""
from __future__ import annotations

from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT / "logs"
LOG_FILE = LOG_DIR / "e5s1_state.json"
STATE_FILE = LOG_DIR / "e5s1_state.json"

MARKER = "; --- E5S1 postprocess ---"
LAYER_BEFORE_MARKER = ";BEFORE_LAYER_CHANGE"
LAYER_CHANGE_MARKER = ";LAYER_CHANGE"
AFTER_LAYER_MARKER = ";AFTER_LAYER_CHANGE"
LAYER_N_MARKER = ";LAYER:"

HEAD_SCAN_BYTES = 8000
SLICER_META_SCAN_BYTES = 32000
MARKER_HEAD_BYTES = max(4096, len(MARKER) + 64)
PA_PROBE_LINES = 800
LARGE_GCODE_BYTES = 2 * 1024 * 1024
METADATA_SCAN_BYTES = 8 * 1024 * 1024

PRUSA_CONFIG_BEGIN = "; prusaslicer_config = begin"
PRUSA_CONFIG_END = "; prusaslicer_config = end"
PRUSA_CONFIG_SCAN_BYTES = 512 * 1024

FIRMWARE_KLIPPER = False
PA_FIRMWARE = "klipper" if FIRMWARE_KLIPPER else "auto"

Z_APPROACH_MAX = 2.0
Z_MIN_WARN = 0.35
LAYER_RETRACT = True
M204_CAP_LAYERS = 3
SUPPORT_OVERHANG_MIN = 1

ENABLE_MESH_ON_START = "M420 S1 Z10 ; postprocess mesh"
STARTUP_PURGE = """G1 X2.0 Y20 F5000.0 ; postprocess purge
G1 Z0.28 F1500.0 ; postprocess purge
G1 X2.0 Y145.0 Z0.28 F1500.0 E15 ; postprocess purge
G1 X2.3 Y145.0 Z0.28 F5000.0 ; postprocess purge
G1 X2.3 Y20 Z0.28 F1500.0 E30 ; postprocess purge
G92 E0 ; postprocess purge"""

INVALID_MACRO_SNIPPET = "first_layer_height[0]"
THUMBNAIL_BEGIN = "; thumbnail begin"
THUMBNAIL_END = "; thumbnail end"

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

PRESERVE_GEOMETRY_FEATURES = frozenset({"top", "bottom"})

PP_FAN_TAGS = (
    "; fan postprocess",
    "; fan capped postprocess",
    "; fan bridge postprocess",
    "; fan overhang postprocess",
    "; fan top postprocess",
    "; fan ironing postprocess",
    "; fan interface postprocess",
    "; fan support postprocess",
    "; fan seam postprocess",
    "; fan adhesion postprocess",
    "; fan restore postprocess",
)

# Hardcoded thresholds, limits and scan windows
BED_X_MIN = 2.0
BED_X_MAX = 218.0
BED_Y_MIN = 2.0
BED_Y_MAX = 218.0
SKIRT_OFFSET_MM = 5.0
TPU_MAX_SPEED_MM_S = 30.0
TPU_SPEED_MULTIPLIER = 0.5
TPU_PA_MULTIPLIER = 2.5
PETG_PA_MULTIPLIER = 1.3
Z_APPROACH_MIN = 0.5
LOW_EST_TIME_SCAN_LIMIT = 100_000
BBOX_SCAN_LIMIT = 100_000
PEEK_SLICER_FAN_WINDOW = 24
PEEK_RETRACT_WINDOW = 8
KLIPPER_MESH_ENABLE = "BED_MESH_PROFILE LOAD=default ; postprocess mesh"

