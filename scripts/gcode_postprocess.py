from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict
import abc
import configparser
import heapq
import json
import os
import re
import sys
import time

"""E5S1 infrastructure constants, bundle.ini loader, and profile builder settings."""

PROJECT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT / "logs"
STATE_FILE = LOG_DIR / "e5s1_state.json"
LOG_FILE = LOG_DIR / "e5s1_events.log"

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

Z_APPROACH_MAX = 2.0
Z_MIN_WARN = 0.35
LAYER_RETRACT = True
M204_CAP_LAYERS = 3
SUPPORT_OVERHANG_MIN = 1

ENABLE_MESH_ON_START = "M420 S1 Z10 ; postprocess mesh"

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

BED_X_MIN = 2.0
BED_X_MAX = 218.0
BED_Y_MIN = 2.0
BED_Y_MAX = 218.0
SKIRT_OFFSET_MM = 5.0
Z_APPROACH_MIN = 0.5
LOW_EST_TIME_SCAN_LIMIT = 100_000
BBOX_SCAN_LIMIT = 100_000
PEEK_SLICER_FAN_WINDOW = 24
PEEK_RETRACT_WINDOW = 8
OVERHANG_FAN_SKIP_THRESHOLD = 40

SMALL_PERIMETER_THRESHOLD_MM = 20.0
SMALL_PERIMETER_SPEED_CAP_F = 900
SMALL_PERIMETER_FLOW_BOOST_PCT = 105

PA_INFILL_SCALE = 1.2
PA_PERIMETER_SCALE = 0.9
PA_BRIDGE_SCALE = 0.5
PA_IRONING_SCALE = 0.2

KEY_IRONING = "ironing"
KEY_TOP_SOLID_INFILL_PATTERN = "top_solid_infill_pattern"
KEY_LAYER_HEIGHT = "layer_height"
KEY_FIRST_LAYER_HEIGHT = "first_layer_height"
KEY_FLOW_RAMP = "flow_ramp"
KEY_NOZZLE_DIAMETER_MM = "nozzle_diameter_mm"
KEY_NOZZLE_DIAMETER = "nozzle_diameter"
KEY_RETRACT_LENGTH = "retract_length"
KEY_RETRACT_SPEED = "retract_speed"
KEY_RETRACT_LIFT = "retract_lift"
KEY_DISABLE_FAN_FIRST_LAYERS = "disable_fan_first_layers"
KEY_FULL_FAN_SPEED_LAYER = "full_fan_speed_layer"
KEY_MIN_FAN_SPEED = "min_fan_speed"
KEY_MAX_FAN_SPEED = "max_fan_speed"
KEY_BRIDGE_FAN_SPEED = "bridge_fan_speed"
KEY_BRIDGE_FLOW_RATIO = "bridge_flow_ratio"
KEY_OVERHANG_FAN_PCT = "overhang_fan_pct"
KEY_TOP_FAN_PCT = "top_fan_pct"
KEY_IRONING_FAN_PCT = "ironing_fan_pct"
KEY_INTERFACE_FAN_PCT = "interface_fan_pct"
KEY_SUPPORT_FAN_PCT = "support_fan_pct"
KEY_SEAM_EXTRA_RETRACT = "seam_extra_retract"
KEY_SEAM_FLOW_PCT = "seam_flow_pct"
KEY_SEAM_FAN_PWM = "seam_fan_pwm"
KEY_SEAM_JOIN_SPEED = "seam_join_speed"
KEY_FIRST_LAYER_SPEED = "first_layer_speed"
KEY_MAX_PRINT_SPEED = "max_print_speed"
KEY_FIRST_LAYER_ACCELERATION = "first_layer_acceleration"
KEY_DEFAULT_ACCELERATION = "default_acceleration"
KEY_PA_K = "pa_k"
KEY_CAP_EXTRUSION_LAYERS = "cap_extrusion_layers"
KEY_FIRST_LAYER_MOTION_LAYERS = "first_layer_motion_layers"
KEY_SKIRTS = "skirts"
KEY_MIN_SKIRT_LENGTH = "min_skirt_length"
KEY_PP_SKIRT_ORIGIN_X = "pp_skirt_origin_x"
KEY_PP_SKIRT_ORIGIN_Y = "pp_skirt_origin_y"
KEY_PP_SKIRT_LOOP_OFFSET_MM = "pp_skirt_loop_offset_mm"
KEY_PP_SKIRT_EXTRUSION_MM_PER_MM = "pp_skirt_extrusion_mm_per_mm"
KEY_FIRST_LAYER_TEMPERATURE = "first_layer_temperature"
KEY_MAX_VOLUMETRIC_FLOW = "max_volumetric_flow"
ENV_E5S1_EXPORT_DIR = "E5S1_EXPORT_DIR"

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

class BundleConfig:
    def __init__(self, path: Path | str | None = None):
        self._config = configparser.ConfigParser(allow_no_value=True)
        self._config.optionxform = lambda option: str(option)  # Preserve case

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
    _instance: BundleConfig | None = None

    @classmethod
    def get_instance(cls) -> BundleConfig:
        if cls._instance is None:
            cls._instance = BundleConfig()
        return cls._instance

def get_bundle_config() -> BundleConfig:
    return BundleConfigFactory.get_instance()

CUSTOM_PARAM_KEYS = (
    "custom_parameters_print",
    "custom_parameters_filament",
    "custom_parameters_printer",
)

DEFAULT_NOZZLE_DIAMETER_MM = 0.8
DEFAULT_NOZZLE_WALL_MM_S = 30
DEFAULT_NOZZLE_INFILL_MM_S = 55
DEFAULT_NOZZLE_CAP_MM_S = 25
DEFAULT_NOZZLE_DEFAULT_MM_S = 40

DEFAULT_RETRACT_LENGTH_MM = 1.2
DEFAULT_RETRACT_SPEED_MM_S = 45.0
DEFAULT_RETRACT_LIFT_MM = 0.4

DEFAULT_FAN_OFF_LAYERS = 2
DEFAULT_FAN_RAMP_LAYERS = 2
DEFAULT_MIN_FAN_PCT = 80
DEFAULT_MAX_FAN_PCT = 100
DEFAULT_BRIDGE_FAN_PCT = 100

DEFAULT_BRIDGE_FLOW_PCT = 95
DEFAULT_FIRST_LAYER_SPEED_MM_S = 20.0
DEFAULT_MAX_PRINT_SPEED_MM_S = 250.0
DEFAULT_FIRST_LAYER_ACCEL = 500
DEFAULT_DEFAULT_ACCEL = 2000
DEFAULT_FIRST_LAYER_HEIGHT_MM = 0.24
DEFAULT_FIRST_LAYER_TEMPERATURE_C = "215"

DEFAULT_CAP_EXTRUSION_LAYERS = 3
DEFAULT_FIRST_LAYER_MOTION_LAYERS = 3
DEFAULT_FLOW_RAMP = (100, 88, 92, 96)

DEFAULT_SEAM_EXTRA_RETRACT_MM = 0.4
DEFAULT_SEAM_FLOW_PCT = 96
DEFAULT_SEAM_FAN_PCT = 85
DEFAULT_SEAM_JOIN_SPEED_MM_S = 18.0

DEFAULT_OVERHANG_FAN_PCT = 86
DEFAULT_TOP_FAN_PCT = 71
DEFAULT_IRONING_FAN_PCT = 35
DEFAULT_INTERFACE_FAN_PCT = 78
DEFAULT_SUPPORT_FAN_PCT = 78

DEFAULT_PA_K = 0.03
DEFAULT_BUNDLE_PA_K = 0.03
DEFAULT_MAX_VOLUMETRIC_FLOW = 15.0

DEFAULT_SKIRT_LOOPS = 3
DEFAULT_SKIRT_SIDE_MM = 40.0
DEFAULT_SKIRT_ORIGIN_X_MM = 3.0
DEFAULT_SKIRT_ORIGIN_Y_MM = 3.0
DEFAULT_SKIRT_LOOP_OFFSET_MM = 2.0
DEFAULT_SKIRT_EXTRUSION_MM_PER_MM = 0.1

class ProfileConfigError(ValueError):
    pass

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
    filament_type: str
    max_volumetric_flow: float

def pct_to_pwm(pct: int) -> int:
    return max(0, min(255, int(255 * pct / 100)))

def resolve_pa_firmware(gcode_sample: str = "") -> str:
    return "marlin"

def _parse_custom_parameters(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not raw or raw.strip() in ("", '""', "''"):
        return out
    for part in raw.replace("\n", ";").split(";"):
        part = part.strip().strip('"')
        if " = " in part:
            key, val = part.split(" = ", 1)
            out[key.strip()] = val.strip()
    return out

def _merge_custom_parameters(cfg: dict[str, str]) -> dict[str, str]:
    merged = dict(cfg)
    for key in CUSTOM_PARAM_KEYS:
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

def _init_bundle_defaults(bundle: BundleConfig, prusa_cfg: dict[str, str]) -> None:
    # First, sync known keys from prusa_cfg if not already set in bundle
    for key, val in prusa_cfg.items():
        if not bundle.has(key):
            bundle.set(key, val)

    # Now set our E5S1 defaults if not set
    defaults: dict[str, Any] = {
        KEY_NOZZLE_DIAMETER: DEFAULT_NOZZLE_DIAMETER_MM,
        KEY_RETRACT_LENGTH: DEFAULT_RETRACT_LENGTH_MM,
        KEY_RETRACT_SPEED: DEFAULT_RETRACT_SPEED_MM_S,
        KEY_RETRACT_LIFT: DEFAULT_RETRACT_LIFT_MM,
        KEY_DISABLE_FAN_FIRST_LAYERS: DEFAULT_FAN_OFF_LAYERS,
        KEY_FULL_FAN_SPEED_LAYER: DEFAULT_FAN_OFF_LAYERS + DEFAULT_FAN_RAMP_LAYERS + 1,
        KEY_MIN_FAN_SPEED: DEFAULT_MIN_FAN_PCT,
        KEY_MAX_FAN_SPEED: DEFAULT_MAX_FAN_PCT,
        KEY_BRIDGE_FAN_SPEED: DEFAULT_BRIDGE_FAN_PCT,
        KEY_BRIDGE_FLOW_RATIO: DEFAULT_BRIDGE_FLOW_PCT / 100,
        KEY_OVERHANG_FAN_PCT: DEFAULT_OVERHANG_FAN_PCT,
        KEY_TOP_FAN_PCT: DEFAULT_TOP_FAN_PCT,
        KEY_IRONING_FAN_PCT: DEFAULT_IRONING_FAN_PCT,
        KEY_INTERFACE_FAN_PCT: DEFAULT_INTERFACE_FAN_PCT,
        KEY_SUPPORT_FAN_PCT: DEFAULT_SUPPORT_FAN_PCT,
        KEY_SEAM_EXTRA_RETRACT: DEFAULT_SEAM_EXTRA_RETRACT_MM,
        KEY_SEAM_FLOW_PCT: DEFAULT_SEAM_FLOW_PCT,
        KEY_SEAM_FAN_PWM: DEFAULT_SEAM_FAN_PCT,
        KEY_SEAM_JOIN_SPEED: DEFAULT_SEAM_JOIN_SPEED_MM_S,
        KEY_FIRST_LAYER_SPEED: DEFAULT_FIRST_LAYER_SPEED_MM_S,
        KEY_MAX_PRINT_SPEED: DEFAULT_MAX_PRINT_SPEED_MM_S,
        KEY_FIRST_LAYER_ACCELERATION: DEFAULT_FIRST_LAYER_ACCEL,
        KEY_DEFAULT_ACCELERATION: DEFAULT_DEFAULT_ACCEL,
        KEY_PA_K: DEFAULT_PA_K,
        KEY_FLOW_RAMP: ",".join(map(str, DEFAULT_FLOW_RAMP)),
        KEY_CAP_EXTRUSION_LAYERS: DEFAULT_CAP_EXTRUSION_LAYERS,
        KEY_FIRST_LAYER_MOTION_LAYERS: DEFAULT_FIRST_LAYER_MOTION_LAYERS,
        KEY_SKIRTS: DEFAULT_SKIRT_LOOPS,
        KEY_MIN_SKIRT_LENGTH: DEFAULT_SKIRT_SIDE_MM,
        KEY_PP_SKIRT_ORIGIN_X: DEFAULT_SKIRT_ORIGIN_X_MM,
        KEY_PP_SKIRT_ORIGIN_Y: DEFAULT_SKIRT_ORIGIN_Y_MM,
        KEY_PP_SKIRT_LOOP_OFFSET_MM: DEFAULT_SKIRT_LOOP_OFFSET_MM,
        KEY_PP_SKIRT_EXTRUSION_MM_PER_MM: DEFAULT_SKIRT_EXTRUSION_MM_PER_MM,
        KEY_FIRST_LAYER_HEIGHT: DEFAULT_FIRST_LAYER_HEIGHT_MM,
        KEY_FIRST_LAYER_TEMPERATURE: int(DEFAULT_FIRST_LAYER_TEMPERATURE_C),
        KEY_MAX_VOLUMETRIC_FLOW: DEFAULT_MAX_VOLUMETRIC_FLOW,
    }

    for key, val in defaults.items():
        if val is not None and not bundle.has(key):
            bundle.set(key, val)

def build_e5s1_profile(prusa_cfg: dict[str, str] | None = None, bundle: BundleConfig | None = None) -> E5S1Profile:
    prusa_cfg = _merge_custom_parameters(prusa_cfg or {})
    if bundle is None:
        bundle = get_bundle_config()

    # Initialize bundle with defaults (if not already present)
    _init_bundle_defaults(bundle, prusa_cfg)

    # Helper functions for common conversions prioritizing prusa_cfg
    def get_str(key: str, default: str) -> str:
        val = prusa_cfg.get(key)
        if val is not None and val.lower() != "nil":
            return val
        return str(bundle.get(key, default))

    def get_int(key: str, default: int) -> int:
        val = prusa_cfg.get(key)
        if val is not None and val.lower() != "nil":
            try:
                return int(float(val.replace(",", ".")))
            except ValueError:
                pass
        return bundle.get(key, default, converter=int)

    def get_float(key: str, default: float) -> float:
        val = prusa_cfg.get(key)
        if val is not None and val.lower() != "nil":
            try:
                return float(val.replace(",", ".").rstrip("%"))
            except ValueError:
                pass
        return bundle.get(key, default, converter=float)

    def get_pwm(key: str, default_pct: int) -> int:
        return pct_to_pwm(get_int(key, default_pct))

    def get_speed_f(key: str, default_mm_s: float) -> int:
        return int(get_float(key, default_mm_s) * 60)

    def get_optional_speed_f(key: str) -> int | None:
        val = get_str(key, "")
        if not val or val.lower() == "nil":
            return None
        try:
            speed_mm_s = float(val.replace(",", "."))
            if speed_mm_s <= 0:
                return None
            return int(speed_mm_s * 60)
        except ValueError:
            return None

    def parse_flow_ramp(raw_val: str, default: tuple[int, ...]) -> list[int]:
        if not raw_val:
            return list(default)
        try:
            return [int(x.strip()) for x in raw_val.split(",") if x.strip()]
        except ValueError as exc:
            raise ProfileConfigError("Invalid flow_ramp value") from exc

    # Locked to PLA and 0.8mm nozzle
    filament_type = "PLA"
    nozzle_diameter = 0.8

    max_print_speed_val = get_float("max_print_speed", DEFAULT_MAX_PRINT_SPEED_MM_S)
    retract_speed_val = get_float(KEY_RETRACT_SPEED, DEFAULT_RETRACT_SPEED_MM_S)

    fan_off = get_int(KEY_DISABLE_FAN_FIRST_LAYERS, DEFAULT_FAN_OFF_LAYERS)
    full_fan = get_int(KEY_FULL_FAN_SPEED_LAYER, fan_off + DEFAULT_FAN_RAMP_LAYERS + 1)
    bridge_ratio = get_float(KEY_BRIDGE_FLOW_RATIO, DEFAULT_BRIDGE_FLOW_PCT / 100)
    bridge_flow_pct = int(bridge_ratio * 100) if bridge_ratio <= 1 else int(bridge_ratio)

    wall_early_f = get_optional_speed_f("pp_wall_speed_mm_s")
    if wall_early_f is None:
        wall_early_f = int(nozzle_diameter * DEFAULT_NOZZLE_WALL_MM_S * 60)
    max_infill_f = get_optional_speed_f("pp_infill_speed_mm_s")
    if max_infill_f is None:
        max_infill_f = int(nozzle_diameter * DEFAULT_NOZZLE_INFILL_MM_S * 60)
    cap_extrusion_f = get_optional_speed_f("pp_cap_speed_mm_s")
    if cap_extrusion_f is None:
        cap_extrusion_f = int(nozzle_diameter * DEFAULT_NOZZLE_CAP_MM_S * 60)
    default_motion_f = int(nozzle_diameter * DEFAULT_NOZZLE_DEFAULT_MM_S * 60)

    # Simplified PA K-value loader
    user_pa = get_str(KEY_PA_K, "")
    if user_pa and user_pa != str(DEFAULT_PA_K) and user_pa != str(DEFAULT_BUNDLE_PA_K):
        try:
            pa_k = float(user_pa)
        except ValueError:
            pa_k = get_float(KEY_PA_K, DEFAULT_PA_K)
    else:
        pa_k = DEFAULT_PA_K

    # Simple flow ramp configuration
    if KEY_FLOW_RAMP in prusa_cfg:
        flow_ramp = parse_flow_ramp(prusa_cfg[KEY_FLOW_RAMP], DEFAULT_FLOW_RAMP)
    else:
        flow_ramp = parse_flow_ramp(bundle.get(KEY_FLOW_RAMP, ",".join(map(str, DEFAULT_FLOW_RAMP))), DEFAULT_FLOW_RAMP)

    return {
        "retract_mm": get_float(KEY_RETRACT_LENGTH, DEFAULT_RETRACT_LENGTH_MM),
        "retract_f": int(retract_speed_val * 60),
        "retract_lift": get_float(KEY_RETRACT_LIFT, DEFAULT_RETRACT_LIFT_MM),
        "fan_off_layers": fan_off,
        "full_fan_layer": full_fan,
        "min_fan_pwm": get_pwm(KEY_MIN_FAN_SPEED, DEFAULT_MIN_FAN_PCT),
        "max_fan_pwm": get_pwm(KEY_MAX_FAN_SPEED, DEFAULT_MAX_FAN_PCT),
        "bridge_fan_pwm": get_pwm(KEY_BRIDGE_FAN_SPEED, DEFAULT_BRIDGE_FAN_PCT),
        "bridge_flow_pct": bridge_flow_pct,
        "overhang_fan_pwm": get_pwm(KEY_OVERHANG_FAN_PCT, DEFAULT_OVERHANG_FAN_PCT),
        "top_fan_pwm": get_pwm(KEY_TOP_FAN_PCT, DEFAULT_TOP_FAN_PCT),
        "ironing_fan_pwm": get_pwm(KEY_IRONING_FAN_PCT, DEFAULT_IRONING_FAN_PCT),
        "interface_fan_pwm": get_pwm(KEY_INTERFACE_FAN_PCT, DEFAULT_INTERFACE_FAN_PCT),
        "support_fan_pwm": get_pwm(KEY_SUPPORT_FAN_PCT, DEFAULT_SUPPORT_FAN_PCT),
        "seam_extra_retract": get_float(KEY_SEAM_EXTRA_RETRACT, DEFAULT_SEAM_EXTRA_RETRACT_MM),
        "seam_flow_pct": get_int(KEY_SEAM_FLOW_PCT, DEFAULT_SEAM_FLOW_PCT),
        "seam_fan_pwm": get_pwm(KEY_SEAM_FAN_PWM, DEFAULT_SEAM_FAN_PCT),
        "seam_join_f": get_speed_f(KEY_SEAM_JOIN_SPEED, DEFAULT_SEAM_JOIN_SPEED_MM_S),
        "first_layer_f": get_speed_f(KEY_FIRST_LAYER_SPEED, DEFAULT_FIRST_LAYER_SPEED_MM_S),
        "wall_early_f": wall_early_f,
        "max_infill_f": max_infill_f,
        "cap_extrusion_f": cap_extrusion_f,
        "max_print_f": int(max_print_speed_val * 60),
        "default_motion_f": default_motion_f,
        "first_layer_accel": get_int(KEY_FIRST_LAYER_ACCELERATION, DEFAULT_FIRST_LAYER_ACCEL),
        "default_accel": get_int(KEY_DEFAULT_ACCELERATION, DEFAULT_DEFAULT_ACCEL),
        "pa_k": pa_k,
        "flow_ramp": flow_ramp,
        "cap_extrusion_layers": get_int(KEY_CAP_EXTRUSION_LAYERS, DEFAULT_CAP_EXTRUSION_LAYERS),
        "first_layer_motion_layers": get_int(KEY_FIRST_LAYER_MOTION_LAYERS, DEFAULT_FIRST_LAYER_MOTION_LAYERS),
        "skirt_loops": get_int(KEY_SKIRTS, DEFAULT_SKIRT_LOOPS),
        "skirt_side_mm": get_float(KEY_MIN_SKIRT_LENGTH, DEFAULT_SKIRT_SIDE_MM),
        "skirt_origin_x_mm": get_float(KEY_PP_SKIRT_ORIGIN_X, DEFAULT_SKIRT_ORIGIN_X_MM),
        "skirt_origin_y_mm": get_float(KEY_PP_SKIRT_ORIGIN_Y, DEFAULT_SKIRT_ORIGIN_Y_MM),
        "skirt_loop_offset_mm": get_float(KEY_PP_SKIRT_LOOP_OFFSET_MM, DEFAULT_SKIRT_LOOP_OFFSET_MM),
        "skirt_extrusion_mm_per_mm": get_float(KEY_PP_SKIRT_EXTRUSION_MM_PER_MM, DEFAULT_SKIRT_EXTRUSION_MM_PER_MM),
        "first_layer_height_mm": get_float(KEY_FIRST_LAYER_HEIGHT, DEFAULT_FIRST_LAYER_HEIGHT_MM),
        "first_layer_temperature_c": str(get_int(KEY_FIRST_LAYER_TEMPERATURE, int(DEFAULT_FIRST_LAYER_TEMPERATURE_C))),
        "nozzle_diameter_mm": nozzle_diameter,
        "filament_type": filament_type,
        "max_volumetric_flow": get_float(KEY_MAX_VOLUMETRIC_FLOW, DEFAULT_MAX_VOLUMETRIC_FLOW),
    }

F_RE = re.compile(r"F(\d+)", re.IGNORECASE)
FAN_ON_RE = re.compile(r"^M106\s+S(\d+)", re.IGNORECASE)
PP_FAN_RE = re.compile(r"^M106\s+S\d+\s*;.*postprocess", re.IGNORECASE | re.MULTILINE)
G1_EXTRUDE_RE = re.compile(r"^G1\b.*\bE[-+]?\d", re.IGNORECASE | re.MULTILINE)
RETRACT_RE = re.compile(r"^G1\b.*\bE-", re.IGNORECASE)
MOTION_RE = re.compile(r"^[GM]\d", re.IGNORECASE)
M104_RE = re.compile(r"^M104\s+S(\d+)", re.IGNORECASE)
M109_RE = re.compile(r"^M109\b", re.IGNORECASE | re.MULTILINE)
M140_RE = re.compile(r"^M140\b", re.IGNORECASE)
M190_RE = re.compile(r"^M190\b", re.IGNORECASE)
M204_S_RE = re.compile(r"^M204\s+S(\d+)", re.IGNORECASE)
M420_RE = re.compile(r"^M420\b", re.IGNORECASE)
M900_RE = re.compile(r"^M900\b", re.IGNORECASE | re.MULTILINE)
G28_RE = re.compile(r"^G28\b", re.MULTILINE)
G29_RE = re.compile(r"^G29\b", re.IGNORECASE)
Z_MOVE_RE = re.compile(r"^G0?1\b.*\bZ([\d.]+)", re.MULTILINE | re.I)
LAYER_H_RE = re.compile(r";\s*layer_height\s*[=:]\s*([\d.,]+)", re.IGNORECASE)
LAYER_H_PATH_RE = re.compile(r"_(\d+[,.]\d+)mm_", re.IGNORECASE)
SLICER_TIME_RE = re.compile(r"; estimated printing time[^=\n]*=\s*(.+)", re.IGNORECASE)

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
        prusa_cfg = parse_prusa_config(text)
    for key in ("total_layer_count", "num_layers"):
        if key in prusa_cfg and prusa_cfg[key].isdigit():
            return int(prusa_cfg[key])
    return 0

def has_skirt_or_brim(text: str) -> tuple[bool, bool]:
    low = text[:120000].lower()
    has_skirt = any(
        tag in low
        for tag in (TYPE_SKIRT.lower(), TYPE_SKIRT_BRIM.lower(), "; skirt", "; type:skirt")
    )
    has_brim = TYPE_BRIM.lower() in low or TYPE_OUTER_BRIM.lower() in low
    return has_skirt, has_brim

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
    return [ln for ln in lines if not is_pp_line(ln, pa_only=not full)]

_FEATURE_SCANNER = None

def get_feature_scanner() -> "GCodeFeatureScanner":
    global _FEATURE_SCANNER
    if _FEATURE_SCANNER is None:
        _FEATURE_SCANNER = GCodeFeatureScanner()
    return _FEATURE_SCANNER

class GCodeFeatureScanner:
    def type_feature(self, line: str) -> str | None:
        if TYPE_IRONING in line:
            return "ironing"
        if TYPE_TOP_SOLID in line:
            return "top"
        if TYPE_INTERFACE in line:
            return "interface"
        if TYPE_SUPPORT_MAT in line or (TYPE_SUPPORT in line and TYPE_INTERFACE not in line):
            return "support"
        if TYPE_BOTTOM_SOLID in line:
            return "bottom"
        if TYPE_BRIM in line or TYPE_OUTER_BRIM in line:
            return "brim"
        if TYPE_EXTERNAL in line:
            return "external"
        if TYPE_GAP_FILL in line:
            return "gap_fill"
        if TYPE_PERIMETER in line:
            return "perimeter"
        if TYPE_INTERNAL in line:
            return "internal"
        if TYPE_SOLID in line:
            return "solid"
        if TYPE_OVERHANG_BRIDGE in line or TYPE_OVERHANG in line:
            return "overhang"
        if TYPE_BRIDGE in line:
            return "bridge"
        if ";TYPE:" in line:
            return "other"
        return None

def preserves_geometry(kind: str | None) -> bool:
    return kind in PRESERVE_GEOMETRY_FEATURES

PP_SKIRT = "postprocess skirt"

class MarlinGCodeEmitter:
    def mesh_enable(self) -> str:
        return ENABLE_MESH_ON_START

    def pressure_advance(self, pa_k: float) -> str:
        return f"M900 K{pa_k} ; linear advance postprocess"

class GCodeBuilder:
    def __init__(self, pa_fw: str = "marlin"):
        self.emitter = MarlinGCodeEmitter()
        self.pa_fw = pa_fw

    def timestamp(self, ts: str) -> str:
        return f"; postprocessed: {ts}"

    def flow_layer(self, layer: int, flow: int) -> str:
        return f"M221 S{flow} ; postprocess flow L{layer}"

    def flow_reset(self) -> str:
        return "M221 S100 ; postprocess flow normal"

    def flow_bridge(self, pct: int) -> str:
        return f"M221 S{pct} ; postprocess flow bridge"

    def z_hop(self, mm: float) -> str:
        return f"G91\nG1 Z{mm} F600 ; postprocess z hop\nG90"

    def layer_retract(self, mm: float, retract_f: int) -> str:
        return f"G1 E-{mm} F{retract_f} ; postprocess layer retract"

    def homing(self) -> str:
        return "G28 ; postprocess homing"

    def wait_hotend(self, temp: str | int) -> str:
        return f"M109 S{temp} ; postprocess wait hotend"

    def mesh_enable(self) -> str:
        return self.emitter.mesh_enable()

    def purge(self, nozzle_diameter: float = 0.8, first_layer_height: float = 0.24) -> str:
        e_first = 125.0 * first_layer_height * (nozzle_diameter * 1.25) / 2.405
        e_second = e_first * 2.0
        return f"""G1 X2.0 Y20 F5000.0 ; postprocess purge
G1 Z{first_layer_height:.3f} F1500.0 ; postprocess purge
G1 X2.0 Y145.0 Z{first_layer_height:.3f} F1500.0 E{e_first:.2f} ; postprocess purge
G1 X2.3 Y145.0 Z{first_layer_height:.3f} F5000.0 ; postprocess purge
G1 X2.3 Y20 Z{first_layer_height:.3f} F1500.0 E{e_second:.2f} ; postprocess purge
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
        return f"G1 Z{z} F600 ; {PP_SKIRT}"

    def skirt_travel(self, x: float, y: float, f: int = 6000) -> str:
        return f"G1 X{x} Y{y} F{f} ; {PP_SKIRT}"

    def skirt_extrude(self, x: float, y: float, e: float, f: int = 600) -> str:
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
        return f"M204 S{accel} ; postprocess accel"

    def cap_accel_suffix(self) -> str:
        return " ; postprocess cap accel"

    def pressure_advance(self, pa_k: float) -> str:
        return self.emitter.pressure_advance(pa_k)

_STAT_FIELDS = (
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

        while pos < end and comment_lines < 100_000:
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

    def count_pp_fan_lines(self, text: str, large: bool) -> int:
        return len(PP_FAN_RE.findall(text))

    def has_pressure_advance(self, text: str) -> bool:
        return bool(M900_RE.search(text))

    def analyze(self, text: str, hint: str = "") -> GcodeAnalysis:
        large = self.is_large_gcode(text)
        prusa_cfg = parse_prusa_config(text)
        has_sup = TYPE_SUPPORT in text or TYPE_SUPPORT_MAT in text or TYPE_INTERFACE in text
        has_skirt, has_brim = has_skirt_or_brim(text)
        overhang = self.count_type_markers(text, TYPE_OVERHANG)
        top_lines = self.count_type_markers(text, TYPE_TOP_SOLID)
        ironing_lines = self.count_type_markers(text, TYPE_IRONING)
        interface_lines = self.count_type_markers(text, TYPE_INTERFACE)
        cfg_ironing = prusa_cfg.get(KEY_IRONING, "0") not in ("0", "false", "")
        has_ironing = ironing_lines > 0 or cfg_ironing
        top_pattern = prusa_cfg.get(KEY_TOP_SOLID_INFILL_PATTERN) or None
        if large:
            extrude_lines = max(text.count("\nG1"), top_lines * 50, 1)
        else:
            extrude_lines = sum(1 for ln in text.splitlines() if G1_EXTRUDE_RE.match(ln.strip()))
        est_raw, layer_h = self._slicer_metadata(text)
        if layer_h is None:
            lh = prusa_cfg.get(KEY_LAYER_HEIGHT) or prusa_cfg.get(KEY_FIRST_LAYER_HEIGHT)
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
            "layers": count_layers(text, prusa_cfg),
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

    def get_stats(self, text: str, analysis: GcodeAnalysis | None = None, fan_pp: int | None = None) -> dict:
        a = analysis or self.analyze(text)
        return {
            "layers": a["layers"],
            "lines": a["lines"],
            "fan_pp": fan_pp if fan_pp is not None else self.count_pp_fan_lines(text, a["large"]),
            "postprocessed": self.is_postprocessed(text),
            "pressure_advance": self.has_pressure_advance(text[:HEAD_SCAN_BYTES]),
            **{k: a[k] for k in _STAT_FIELDS},
        }

class GCodeValidator:
    def __init__(self, analyzer: GCodeAnalyzer | None = None):
        self.analyzer = analyzer or GCodeAnalyzer()

    def _startup_text(self, text: str) -> str:
        for marker in (LAYER_CHANGE_MARKER, LAYER_BEFORE_MARKER, AFTER_LAYER_MARKER):
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
        elif expect_postprocess and self.analyzer.count_pp_fan_lines(text, large) == 0:
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
            z_low = [float(m.group(1)) for m in Z_MOVE_RE.finditer(startup) if float(m.group(1)) < 0.5]
            if z_low and min(z_low) > Z_MIN_WARN:
                warnings.append(f"Minimum Z {min(z_low):.2f}mm — check Z-offset")

        if not analysis["layers"]:
            warnings.append("No layer change markers")

        if analysis["needs_support"]:
            warnings.append(
                "Overhangs without support material — max part cooling applied; enable support in slicer for best results"
            )
        elif not pp and not analysis["has_skirt"] and not analysis["has_brim"]:
            warnings.append("No skirt/brim — E5S1 skirt will be injected on post-process")

        return errors, warnings

BED_MESH_RE = re.compile(r"BED_MESH", re.I)
X_VAL_RE = re.compile(r"\b[Xx]([\d.-]+)")
Y_VAL_RE = re.compile(r"\b[Yy]([\d.-]+)")
E_VAL_RE = re.compile(r"\b[Ee]([\d.-]+)")

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
    if preserves_geometry(kind):
        return None
    ceiling = profile["max_print_f"]
    if in_startup or layer_count <= 1:
        return min(profile["first_layer_f"], ceiling)
    if layer_count <= profile["cap_extrusion_layers"]:
        if kind in ("external", "perimeter", "gap_fill", "brim"):
            return min(profile["wall_early_f"], ceiling)
        return min(profile["cap_extrusion_f"], ceiling)
    if kind in ("internal", "solid", "support"):
        return min(profile["max_infill_f"], ceiling)
    return None

def layer_retract_lines(profile: E5S1Profile, builder: GCodeBuilder) -> list[str]:
    lines: list[str] = []
    if profile["retract_lift"] > 0:
        lines.append(builder.z_hop(profile["retract_lift"]))
    lines.append(builder.layer_retract(profile["retract_mm"], profile["retract_f"]))
    return lines

def recent_retract(out: list[str], window: int = PEEK_RETRACT_WINDOW, *, seam: bool = False) -> bool:
    for line in out[-window:]:
        stripped = line.strip()
        if not RETRACT_RE.match(stripped):
            continue
        low = line.lower()
        if "postprocess" not in low:
            continue
        if seam:
            return True
        if "postprocess layer retract" not in low:
            return True
    return False

def peek_slicer_fan(lines: list[str], idx: int, window: int = PEEK_SLICER_FAN_WINDOW) -> tuple[int | None, int | None]:
    end = min(idx + 1 + window, len(lines))
    for j in range(idx + 1, end):
        stripped = lines[j].strip()
        if (m := FAN_ON_RE.match(stripped)) and "postprocess" not in stripped.lower():
            return int(m.group(1)), j
        upper = stripped.upper()
        if upper.startswith(("G0", "G1")) and " E" in upper:
            break
    return None, None

def e5s1_fan_target_label(kind: str, layer_count: int, layer_fan_cap: int | None, profile: E5S1Profile) -> tuple[int, str] | None:
    pwm_keys = {
        "top": ("top_fan_pwm", "top"),
        "ironing": ("ironing_fan_pwm", "ironing"),
        "interface": ("interface_fan_pwm", "interface"),
        "support": ("support_fan_pwm", "support"),
    }
    if kind in pwm_keys:
        key, label = pwm_keys[kind]
        return profile[key], label
    if kind in ("external", "perimeter") and layer_count > profile["fan_off_layers"]:
        pwm = min(profile["seam_fan_pwm"], profile["min_fan_pwm"]) if kind == "perimeter" else profile["seam_fan_pwm"]
        return pwm, "seam"
    if kind in ("bottom", "external", "perimeter", "brim") and layer_count <= profile["fan_off_layers"]:
        return (layer_fan_cap if layer_fan_cap is not None else 0), "adhesion"
    return None

def tune_fan_speed(out: list[str], actions: list[str], kind: str, lines: list[str], idx: int, layer_count: int, layer_fan_cap: int | None, profile: E5S1Profile, builder: GCodeBuilder) -> int | None:
    slicer_fan, fan_idx = peek_slicer_fan(lines, idx)
    target = e5s1_fan_target_label(kind, layer_count, layer_fan_cap, profile)
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
    return None

def sanitize_startup_line(line: str, first_layer_height_mm: float) -> tuple[str | None, str | None]:
    stripped = line.rstrip("\n\r")
    if INVALID_MACRO_SNIPPET in stripped:
        return stripped.replace(INVALID_MACRO_SNIPPET, str(first_layer_height_mm)), "macro_fixed"
    return stripped, None

def head_index(lines: list[str]) -> int:
    return next(
        (
            i
            for i, line in enumerate(lines)
            if LAYER_BEFORE_MARKER in line or LAYER_CHANGE_MARKER in line or AFTER_LAYER_MARKER in line
        ),
        min(len(lines), PA_PROBE_LINES),
    )

def scan_bounding_box(lines: list[str]) -> tuple[float, float, float, float] | None:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    has_moves = False

    for line in lines:
        stripped = line.strip()
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
                        x = float(x_match.group(1))
                        min_x = min(min_x, x)
                        max_x = max(max_x, x)
                        has_moves = True
                    if y_match:
                        y = float(y_match.group(1))
                        min_y = min(min_y, y)
                        max_y = max(max_y, y)
                        has_moves = True

    if has_moves:
        return min_x, min_y, max_x, max_y
    return None

def generate_contour_skirt(profile: E5S1Profile, bbox: tuple[float, float, float, float] | None, builder: GCodeBuilder) -> list[str]:
    z_val = profile["first_layer_height_mm"]
    lines = [builder.skirt_comment(), builder.skirt_z(z_val)]

    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox
        base_x0 = max(BED_X_MIN, min_x - SKIRT_OFFSET_MM)
        base_y0 = max(BED_Y_MIN, min_y - SKIRT_OFFSET_MM)
        base_x1 = min(BED_X_MAX, max_x + SKIRT_OFFSET_MM)
        base_y1 = min(BED_Y_MAX, max_y + SKIRT_OFFSET_MM)
    else:
        base_x0 = profile["skirt_origin_x_mm"]
        base_y0 = profile["skirt_origin_y_mm"]
        base_x1 = base_x0 + profile["skirt_side_mm"]
        base_y1 = base_y0 + profile["skirt_side_mm"]

    for loop in range(profile["skirt_loops"]):
        offset_mm = loop * profile["skirt_loop_offset_mm"]
        x0 = max(BED_X_MIN, base_x0 - offset_mm)
        y0 = max(BED_Y_MIN, base_y0 - offset_mm)
        x1 = min(BED_X_MAX, base_x1 + offset_mm)
        y1 = min(BED_Y_MAX, base_y1 + offset_mm)

        len_x = x1 - x0
        len_y = y1 - y0

        if len_x <= 0.1 or len_y <= 0.1:
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

def _fix_z_line(line: str, target: float, builder: GCodeBuilder) -> tuple[str, bool]:
    m = Z_MOVE_RE.match(line.strip())
    if not m:
        return line, False
    z = float(m.group(1))
    if Z_MIN_WARN < z < Z_APPROACH_MAX:
        return re.sub(r"(\bZ)([\d.]+)", rf"\g<1>{target}", line, count=1, flags=re.I) + builder.z_fix_suffix(), True
    return line, False

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
    in_skirt = False
    for line in motion:
        low = line.lower()
        if PP_SKIRT in low or in_skirt:
            in_skirt = in_skirt or PP_SKIRT in low
            buckets["skirt"].append(line)
            continue
        if M140_RE.match(line.strip()) or M190_RE.match(line.strip()):
            buckets["bed_heat"].append(line)
        elif G28_RE.search(line.strip()):
            buckets["g28"].append(line)
        elif M420_RE.match(line.strip()) or "postprocess mesh" in low or "bed_mesh" in low:
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
        + buckets["skirt"]
        + buckets["other"]
    )

def repair_homing(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    if not G28_RE.search("\n".join(head)):
        head.insert(_comment_prefix_len(head), builder.homing())
        actions.append("g28_added")
        return head + lines[h_idx:]
    return lines

def repair_mesh_leveling(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    head_text = "\n".join(head)
    g28_idx = _line_index(head, G28_RE)
    head_join = head_text.upper()
    if g28_idx is not None and "M420" not in head_join and "G29" not in head_join and "BED_MESH" not in head_join:
        _insert_after(head, g28_idx, builder.mesh_enable())
        actions.append("mesh_enabled")
        return head + lines[h_idx:]
    return lines

def repair_wait_hotend(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    if not M109_RE.search("\n".join(head)):
        hotend_c = profile["first_layer_temperature_c"]
        for line in head:
            if m := M104_RE.match(line.strip()):
                hotend_c = m.group(1)
        g28_idx = _line_index(head, G28_RE)
        mesh_idx = _line_index(head, M420_RE) or _line_index(head, BED_MESH_RE)
        _insert_after(head, mesh_idx if mesh_idx is not None else g28_idx, builder.wait_hotend(hotend_c))
        actions.append("m109_added")
        return head + lines[h_idx:]
    return lines

def repair_purge_line(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    if not any(G1_EXTRUDE_RE.match(line.strip()) for line in head):
        m109_idx = _line_index(head, M109_RE)
        nozzle_dia = profile.get("nozzle_diameter_mm", DEFAULT_NOZZLE_DIAMETER_MM)
        first_lh = profile["first_layer_height_mm"]
        _insert_after(head, m109_idx, builder.purge(nozzle_dia, first_lh))
        actions.append("purge_added")
        return head + lines[h_idx:]
    return lines

def repair_z_fix(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    fixed_head: list[str] = []
    changed_any = False
    for line in head:
        new_line, changed = _fix_z_line(line, profile["first_layer_height_mm"], builder)
        fixed_head.append(new_line)
        if changed:
            actions.append("z_fix")
            changed_any = True
    if changed_any:
        return fixed_head + lines[h_idx:]
    return lines

def repair_skirt_injection(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    tail = lines[h_idx:]
    body_preview = "\n".join(lines)
    has_skirt, has_brim = has_skirt_or_brim(body_preview)
    if not has_skirt and not has_brim and PP_SKIRT not in body_preview:
        bbox = scan_bounding_box(tail)
        skirt_code = generate_contour_skirt(profile, bbox, builder)
        head = _insert_skirt_block(head, skirt_code)
        actions.append(f"skirt_added×{profile['skirt_loops']}")
        return head + tail
    return lines

def repair_startup_order_normalization(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    h_idx = head_index(lines)
    head = list(lines[:h_idx])
    normalized_head = _normalize_startup_order(head)
    return normalized_head + lines[h_idx:]

def repair_small_perimeters(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    segments = []
    in_perimeter = False
    curr_seg = []
    curr_dist = 0.0
    last_x, last_y = None, None

    for i, line in enumerate(lines):
        upper = line.upper()
        if "TYPE:EXTERNAL PERIMETER" in upper or "TYPE:PERIMETER" in upper:
            in_perimeter = True
            curr_seg = []
            curr_dist = 0.0
        elif "TYPE:" in upper:
            in_perimeter = False
            if curr_seg:
                segments.append((curr_seg, curr_dist))
                curr_seg = []

        if upper.startswith(("G0", "G1")):
            m_x = X_VAL_RE.search(upper)
            m_y = Y_VAL_RE.search(upper)
            m_e = E_VAL_RE.search(upper)

            x = float(m_x.group(1)) if m_x else last_x
            y = float(m_y.group(1)) if m_y else last_y

            is_extrude = bool(m_e and not m_e.group(1).startswith("-") and m_e.group(1) != "0")

            if in_perimeter and is_extrude:
                if not curr_seg:
                    curr_dist = 0.0
                elif last_x is not None and last_y is not None and x is not None and y is not None:
                    import math
                    curr_dist += math.hypot(x - last_x, y - last_y)
                curr_seg.append(i)
            elif curr_seg:
                segments.append((curr_seg, curr_dist))
                curr_seg = []

            last_x, last_y = x, y

    # Filter small perimeters (less than threshold distance)
    small_segments = [seg for seg, dist in segments if 0 < dist < SMALL_PERIMETER_THRESHOLD_MM]

    if not small_segments:
        return lines

    out = list(lines)
    for seg in reversed(small_segments):
        start_idx = seg[0]
        end_idx = seg[-1]

        out.insert(end_idx + 1, "M221 S100 ; postprocess small perimeter flow reset")

        line_start = out[start_idx]
        if F_RE.search(line_start):
            line_start = F_RE.sub(f"F{SMALL_PERIMETER_SPEED_CAP_F}", line_start)
        else:
            line_start += f" F{SMALL_PERIMETER_SPEED_CAP_F}"
        line_start += " ; postprocess small perimeter speed cap"
        out[start_idx] = line_start

        out.insert(start_idx, f"M221 S{SMALL_PERIMETER_FLOW_BOOST_PCT} ; postprocess small perimeter flow boost")

    actions.append(f"small_perimeters_fixed×{len(small_segments)}")
    return out

def repair_layer_marker(lines: list[str], profile: E5S1Profile, builder: GCodeBuilder, actions: list[str]) -> list[str]:
    body = "\n".join(lines)
    if body.count(LAYER_BEFORE_MARKER) == 0 and body.count(AFTER_LAYER_MARKER) > 0:
        patched: list[str] = []
        for line in lines:
            if AFTER_LAYER_MARKER in line:
                if not patched or patched[-1].strip() != LAYER_BEFORE_MARKER:
                    patched.append(LAYER_BEFORE_MARKER)
                    patched.append(builder.layer_sync())
                    actions.append("layer_marker")
            patched.append(line)
        return patched
    elif count_layers(body) == 0:
        patched = list(lines)
        for i, line in enumerate(patched):
            if LAYER_N_MARKER in line:
                patched[i:i] = [LAYER_BEFORE_MARKER, builder.layer_sync()]
                actions.append("layer_marker")
                break
        return patched
    return lines

def repair_gcode(lines: list[str], profile: E5S1Profile, pa_fw: str = "marlin") -> tuple[list[str], list[str]]:
    actions: list[str] = []
    builder = GCodeBuilder(pa_fw)

    steps = [
        repair_homing,
        repair_mesh_leveling,
        repair_wait_hotend,
        repair_purge_line,
        repair_z_fix,
        repair_skirt_injection,
        repair_small_perimeters,
        repair_startup_order_normalization,
        repair_layer_marker,
    ]

    out = list(lines)
    for step in steps:
        out = step(out, profile, builder, actions)

    return out, actions

def inject_pa(lines: list[str], pa_fw: str, pa_k: float, builder: GCodeBuilder | None = None) -> tuple[list[str], str | None]:
    if not pa_k or pa_fw == "none":
        return lines, None
    builder = builder or GCodeBuilder(pa_fw)
    head = lines[:head_index(lines)]
    has_pa = any(M900_RE.match(line.strip()) for line in head)
    if has_pa:
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
    def __init__(self, profile: E5S1Profile, builder: GCodeBuilder, skip_overhang_fan: bool, layer_h: float | None = None):
        self.profile = profile
        self.builder = builder
        self.skip_overhang_fan = skip_overhang_fan
        self.layer_h = layer_h or 0.4  # Default to 0.4 layer height if none detected
        self.out: list[str] = []
        self.actions: list[str] = []
        self.layer_count = 0
        self.in_startup = True
        self.layer_fan_cap: int | None = None
        self.boost_fan = False
        self.cool_boost = False
        self.flow_bridge = False
        self.surface_kind: str | None = None
        self.last_f = profile["default_motion_f"]
        self.skip_fan_at: set[int] = set()
        self.current_line = ""
        self.current_upper = ""

    def update_line(self, line: str) -> None:
        self.current_line = line
        self.current_upper = line.upper()

    def reset_flow(self) -> None:
        if self.flow_bridge:
            self.out.append(self.builder.flow_reset())
            self.actions.append("flow_reset")
            self.flow_bridge = False

    def restore_layer_fan(self) -> None:
        if self.layer_fan_cap is not None:
            self.out.append(self.builder.fan_restore(self.layer_fan_cap))
            self.actions.append("fan_restore")

    def begin_layer(self, stripped: str) -> None:
        self.layer_count += 1
        cap = fan_pwm_for_layer(self.layer_count, self.profile)
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

def transform_speed_tracking(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    if ctx.current_upper.startswith(("G0", "G1")) and (fm := F_RE.search(ctx.current_line)):
        ctx.last_f = int(fm.group(1))
    return False

def transform_startup_line(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    if ctx.in_startup:
        fixed, fix_action = sanitize_startup_line(ctx.current_line, ctx.profile["first_layer_height_mm"])
        if fix_action:
            ctx.actions.append(fix_action)
        if fixed is None:
            return True
        if fixed != ctx.current_line:
            ctx.update_line(fixed)
    return False

def transform_header(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    if ctx.current_line.startswith("; generated by"):
        ctx.out += [ctx.current_line, ctx.builder.timestamp(datetime.now().isoformat(timespec="seconds")), MARKER]
        ctx.actions.append("header")
        return True
    return False

def transform_feature_type(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    feat = get_feature_scanner().type_feature(ctx.current_line)
    if feat in ("bridge", "overhang"):
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
        elif not ctx.skip_overhang_fan:
            ctx.out.append(ctx.builder.fan_command("overhang", ctx.profile["overhang_fan_pwm"]))
            ctx.actions.append("fan_overhang")
        ctx.boost_fan = True
        ctx.cool_boost = True
        ctx.surface_kind = feat
        return True

    if feat is not None:
        ctx.reset_flow()
        if ctx.cool_boost:
            ctx.restore_layer_fan()
            ctx.cool_boost = False

        ctx.boost_fan = feat in ("top", "ironing", "interface", "support", "bottom", "external", "perimeter", "brim", "bridge", "overhang")

        # Dynamically adjust Linear Advance for Marlin
        if ctx.builder.pa_fw == "marlin" and ctx.profile["pa_k"] > 0:
            scale = 1.0
            if feat in ("external", "perimeter"):
                scale = PA_PERIMETER_SCALE
            elif feat in ("internal", "solid", "infill"):
                scale = PA_INFILL_SCALE
            elif feat in ("bridge", "overhang"):
                scale = PA_BRIDGE_SCALE
            elif feat == "ironing":
                scale = PA_IRONING_SCALE
            k = round(ctx.profile["pa_k"] * scale, 4)
            ctx.out.append(ctx.builder.pressure_advance(k))
            ctx.actions.append(f"pa_dynamic_K{k}")

        if feat in ("external", "perimeter", "top", "ironing", "interface", "support", "bottom", "brim"):
            ctx.out.append(ctx.current_line)
            skip_idx = tune_fan_speed(
                ctx.out, ctx.actions, feat, lines, idx, ctx.layer_count, ctx.layer_fan_cap, ctx.profile, ctx.builder
            )
            if skip_idx:
                ctx.skip_fan_at.add(skip_idx)
            ctx.surface_kind = feat
            return True

        if feat == "other":
            ctx.surface_kind = None
            ctx.boost_fan = False
            return True

        ctx.out.append(ctx.current_line)
        ctx.surface_kind = feat
        return True

    return False

def transform_ironing_fan(ctx: TransformContext, lines: list[str], idx: int) -> bool:
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
    if LAYER_BEFORE_MARKER in ctx.current_line or AFTER_LAYER_MARKER in ctx.current_line:
        ctx.in_startup = False
        if ctx.cool_boost:
            ctx.restore_layer_fan()
        ctx.reset_flow()
        if LAYER_BEFORE_MARKER in ctx.current_line and LAYER_RETRACT and ctx.layer_count >= 1 and not recent_retract(ctx.out):
            ctx.out.extend(layer_retract_lines(ctx.profile, ctx.builder))
            ctx.actions.append("retract_layer")
        ctx.boost_fan = False
        ctx.cool_boost = False
        ctx.surface_kind = None
        ctx.begin_layer(ctx.current_line)
        return True
    if LAYER_CHANGE_MARKER in ctx.current_line:
        ctx.in_startup = False
        if ctx.layer_count == 0:
            if ctx.cool_boost:
                ctx.restore_layer_fan()
            ctx.reset_flow()
            ctx.boost_fan = False
            ctx.cool_boost = False
            ctx.surface_kind = None
            ctx.begin_layer(ctx.current_line)
        else:
            ctx.out.append(ctx.current_line)
        return True
    return False

def transform_accel_cap(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    if (m204_m := M204_S_RE.match(ctx.current_line) if 1 <= ctx.layer_count <= M204_CAP_LAYERS else None):
        cap_accel = ctx.profile["first_layer_accel"]
        if int(m204_m.group(1)) > cap_accel:
            ctx.out.append(
                re.sub(r"(M204\s+)S\d+", rf"\g<1>S{cap_accel}", ctx.current_line, count=1, flags=re.I)
                + ctx.builder.cap_accel_suffix()
            )
            ctx.actions.append(f"m204_cap_l{ctx.layer_count}")
        else:
            ctx.out.append(ctx.current_line)
        return True
    return False

def transform_fan_cap(ctx: TransformContext, lines: list[str], idx: int) -> bool:
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

def transform_speed_cap(ctx: TransformContext, lines: list[str], idx: int) -> bool:
    fan_m = FAN_ON_RE.match(ctx.current_line)
    if (
        ctx.current_upper.startswith("G1")
        and " E" in ctx.current_upper
        and G1_EXTRUDE_RE.match(ctx.current_line)
        and not fan_m
    ):
        f_cap = speed_cap_for(ctx.surface_kind, ctx.layer_count, ctx.in_startup, ctx.profile)

        # Volumetric Flow Rate Cap Calculation
        w = ctx.profile.get("nozzle_diameter_mm", 0.8)
        h = ctx.profile["first_layer_height_mm"] if (ctx.layer_count <= 1 or ctx.in_startup) else ctx.layer_h
        volume_per_mm = w * h
        if volume_per_mm > 0:
            max_speed_mm_s = ctx.profile["max_volumetric_flow"] / volume_per_mm
            flow_cap_f = int(max_speed_mm_s * 60)
            if f_cap is None or flow_cap_f < f_cap:
                f_cap = flow_cap_f

        if f_cap is not None:
            new_line, capped, last_f = cap_f_line(ctx.current_line, f_cap, ctx.last_f, ctx.builder)
            ctx.out.append(new_line)
            if capped:
                ctx.actions.append(f"cap_flow_l{ctx.layer_count or 'startup'}")
            return True
    return False

def transform_gcode(
    lines: list[str],
    *,
    analysis: GcodeAnalysis,
    prusa_cfg: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    bundle = get_bundle_config()
    profile = build_e5s1_profile(prusa_cfg, bundle)
    pa_fw = resolve_pa_firmware("\n".join(lines[:PA_PROBE_LINES]))
    need_sup = analysis["needs_support"]
    skip_overhang_fan = analysis["large"] and analysis["overhang_markers"] > OVERHANG_FAN_SKIP_THRESHOLD and not need_sup

    builder = GCodeBuilder(pa_fw)
    ctx = TransformContext(profile, builder, skip_overhang_fan, analysis.get("layer_h"))

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

    out, repair_actions = repair_gcode(ctx.out, profile, pa_fw)
    ctx.actions.extend(repair_actions)
    out = strip_pp_lines(out)
    out, pa_action = inject_pa(out, pa_fw, profile["pa_k"], builder)
    if pa_action:
        ctx.actions.append(pa_action)
    if skip_overhang_fan:
        ctx.actions.append(f"fan_overhang_skip×{analysis['overhang_markers']}")
    elif need_sup:
        ctx.actions.append("support_cooling")
    return out, ctx.actions

def _export_search_dirs() -> tuple[Path, ...]:
    dirs = [
        Path.home() / "Downloads",
        Path.home() / "Documentos",
        Path.home() / "Documents",
    ]
    extra = os.environ.get("E5S1_EXPORT_DIR", "").strip()
    if extra:
        dirs.append(Path(extra))
    return tuple(dirs)

EXPORT_SEARCH_DIRS = _export_search_dirs()

class IExportFinder(abc.ABC):
    @abc.abstractmethod
    def find_recent_export(self, max_age_s: int = 300, max_files: int = 5) -> Path | None:
        pass

    @abc.abstractmethod
    def path_note(self, path: Path, argv: list[str] | None = None, export: Path | None = None) -> str:
        pass

class RecentExportFinder(IExportFinder):
    def _recent_gcode_candidates(self, folder: Path, now: float, max_age_s: int, max_files: int) -> list[Path]:
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

    def find_recent_export(self, max_age_s: int = 300, max_files: int = 5) -> Path | None:
        now = time.time()
        for folder in EXPORT_SEARCH_DIRS:
            if not folder.is_dir():
                continue
            for candidate in self._recent_gcode_candidates(folder, now, max_age_s, max_files):
                try:
                    with candidate.open(encoding="utf-8", errors="replace") as f:
                        if MARKER in f.read(MARKER_HEAD_BYTES):
                            return candidate
                except OSError:
                    continue
        return None

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

class ILogger(abc.ABC):
    @abc.abstractmethod
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
        pass

    @abc.abstractmethod
    def log_state_warn(self, msg: str, quiet: bool) -> None:
        pass

    @abc.abstractmethod
    def log_fail(self, note: str, quiet: bool) -> None:
        pass

    @abc.abstractmethod
    def format_actions(self, actions: list[str]) -> str:
        pass

class DefaultLogger(ILogger):
    def __init__(self, state_logger: IStateLogger, analyzer: GCodeAnalyzer):
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
        logger: ILogger | None = None,
        analyzer: GCodeAnalyzer | None = None,
        validator: GCodeValidator | None = None,
        export_finder: IExportFinder | None = None,
        state_logger: IStateLogger | None = None,
    ):
        self.analyzer = analyzer or GCodeAnalyzer()
        self.validator = validator or GCodeValidator(self.analyzer)
        self.export_finder = export_finder or RecentExportFinder()
        self.state_logger = state_logger or LoggerFactory.get_instance()

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
                analysis = self.analyzer.analyze(raw, hint)
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

            analysis = self.analyzer.analyze(raw, hint)
            prusa_cfg = parse_prusa_config(raw)
            new_lines, actions = transform_gcode(
                strip_pp_lines(raw.splitlines(), full=force),
                analysis=analysis,
                prusa_cfg=prusa_cfg,
            )

            result = "\n".join(new_lines) + "\n"
            path.write_text(result, encoding="utf-8")

            export = None
            try:
                export = self.export_finder.find_recent_export()
                hint = " ".join(str(p) for p in [path, export] if p)
            except OSError as e:
                self.logger.log_state_warn(str(e), quiet)

            result_analysis = self.analyzer.analyze(result, hint)
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

def run_postprocess(
    paths: list[Path],
    quiet: bool = False,
    force: bool = False,
    argv: list[str] | None = None,
) -> int:
    app = PostProcessApp()
    return app.run(paths, quiet, force, argv)

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    argv = sys.argv[1:]
    sys.exit(
        run_postprocess(
            [Path(p) for p in argv],
            quiet=True,
            argv=argv,
        )
    )
