"""E5S1 profile — autonomous defaults with optional Prusa export overrides."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict, Any

from config import (
    FIRMWARE_KLIPPER,
    PA_FIRMWARE,
    PRUSA_CONFIG_BEGIN,
    PRUSA_CONFIG_END,
    PRUSA_CONFIG_SCAN_BYTES,
)
from bundle_config import BundleConfig, get_bundle_config

_CUSTOM_PARAM_KEYS = (
    "custom_parameters_print",
    "custom_parameters_filament",
    "custom_parameters_printer",
)

_NOZZLE_DIAMETER_MM = 0.8
_NOZZLE_WALL_MM_S = 30
_NOZZLE_INFILL_MM_S = 55
_NOZZLE_CAP_MM_S = 25
_NOZZLE_DEFAULT_MM_S = 40

_RETRACT_LENGTH_MM = 0.8
_RETRACT_SPEED_MM_S = 45.0
_RETRACT_LIFT_MM = 0.4

_FAN_OFF_LAYERS = 2
_FAN_RAMP_LAYERS = 2
_MIN_FAN_PCT = 70
_MAX_FAN_PCT = 100
_BRIDGE_FAN_PCT = 100

_BRIDGE_FLOW_PCT = 95
_FIRST_LAYER_SPEED_MM_S = 20.0
_MAX_PRINT_SPEED_MM_S = 250.0
_FIRST_LAYER_ACCEL = 500
_DEFAULT_ACCEL = 2000
_FIRST_LAYER_HEIGHT_MM = 0.24
_FIRST_LAYER_TEMPERATURE_C = "215"

_CAP_EXTRUSION_LAYERS = 3
_FIRST_LAYER_MOTION_LAYERS = 3
_FLOW_RAMP = (100, 88, 92, 96)

_SEAM_EXTRA_RETRACT_MM = 0.4
_SEAM_FLOW_PCT = 96
_SEAM_FAN_PCT = 85
_SEAM_JOIN_SPEED_MM_S = 18.0

_OVERHANG_FAN_PCT = 86
_TOP_FAN_PCT = 71
_IRONING_FAN_PCT = 35
_INTERFACE_FAN_PCT = 78
_SUPPORT_FAN_PCT = 78

_PA_K = 0.08

_SKIRT_LOOPS = 3
_SKIRT_SIDE_MM = 40.0
_SKIRT_ORIGIN_X_MM = 3.0
_SKIRT_ORIGIN_Y_MM = 3.0
_SKIRT_LOOP_OFFSET_MM = 2.0
_SKIRT_EXTRUSION_MM_PER_MM = 0.1


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


def pct_to_pwm(pct: int) -> int:
    return max(0, min(255, int(255 * pct / 100)))


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


def firmware_label() -> str:
    return "klipper" if FIRMWARE_KLIPPER else "marlin"


def resolve_pa_firmware(gcode_sample: str = "") -> str:
    if PA_FIRMWARE != "auto":
        return PA_FIRMWARE
    low = gcode_sample.lower()
    if any(token in low for token in ("klipper", "set_pressure_advance", "smoothieware")):
        return "klipper"
    if "marlin" in low:
        return "marlin"
    return firmware_label()


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
    for key in _CUSTOM_PARAM_KEYS:
        merged.update(_parse_custom_parameters(cfg.get(key, "")))
    return merged


def _cfg_float(cfg: dict[str, str], key: str, default: float) -> float:
    raw = cfg.get(key, "").strip()
    if not raw or raw.lower() == "nil":
        return default
    try:
        return float(raw.replace(",", ".").rstrip("%"))
    except ValueError as exc:
        raise ProfileConfigError(f"Invalid float for config key: {key}") from exc


def _cfg_int(cfg: dict[str, str], key: str, default: int) -> int:
    raw = cfg.get(key, "").strip()
    if not raw or raw.lower() == "nil":
        return default
    try:
        return int(float(raw.replace(",", ".")))
    except ValueError as exc:
        raise ProfileConfigError(f"Invalid integer for config key: {key}") from exc


def _cfg_speed_f(cfg: dict[str, str], key: str, default_mm_s: float) -> int:
    raw = cfg.get(key, "").strip()
    if not raw or raw.lower() == "nil":
        return int(default_mm_s * 60)
    speed_mm_s = float(raw.replace(",", "."))
    if speed_mm_s <= 0:
        return int(default_mm_s * 60)
    return int(speed_mm_s * 60)


def _cfg_optional_speed_f(cfg: dict[str, str], key: str) -> int | None:
    raw = cfg.get(key, "").strip()
    if not raw or raw.lower() == "nil":
        return None
    speed_mm_s = float(raw.replace(",", "."))
    if speed_mm_s <= 0:
        return None
    return int(speed_mm_s * 60)


def _cfg_pct_pwm(cfg: dict[str, str], key: str, default_pct: int) -> int:
    return pct_to_pwm(_cfg_int(cfg, key, default_pct))


def _cfg_flow_ramp(cfg: dict[str, str], default: tuple[int, ...]) -> list[int]:
    raw = cfg.get("flow_ramp", "").strip()
    if not raw:
        return list(default)
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError as exc:
        raise ProfileConfigError("Invalid flow_ramp value") from exc


def _nozzle_diameter_mm(cfg: dict[str, str]) -> float:
    return _cfg_float(cfg, "nozzle_diameter", _NOZZLE_DIAMETER_MM)


def _nozzle_speed_caps(cfg: dict[str, str]) -> tuple[int, int, int, int]:
    nozzle_diameter_mm = _nozzle_diameter_mm(cfg)
    wall_early_f = _cfg_optional_speed_f(cfg, "pp_wall_speed_mm_s")
    if wall_early_f is None:
        wall_early_f = int(nozzle_diameter_mm * _NOZZLE_WALL_MM_S * 60)
    max_infill_f = _cfg_optional_speed_f(cfg, "pp_infill_speed_mm_s")
    if max_infill_f is None:
        max_infill_f = int(nozzle_diameter_mm * _NOZZLE_INFILL_MM_S * 60)
    cap_extrusion_f = _cfg_optional_speed_f(cfg, "pp_cap_speed_mm_s")
    if cap_extrusion_f is None:
        cap_extrusion_f = int(nozzle_diameter_mm * _NOZZLE_CAP_MM_S * 60)
    default_motion_f = int(nozzle_diameter_mm * _NOZZLE_DEFAULT_MM_S * 60)
    return wall_early_f, max_infill_f, cap_extrusion_f, default_motion_f


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
        "nozzle_diameter": _NOZZLE_DIAMETER_MM,
        "retract_length": _RETRACT_LENGTH_MM,
        "retract_speed": _RETRACT_SPEED_MM_S,
        "retract_lift": _RETRACT_LIFT_MM,
        "disable_fan_first_layers": _FAN_OFF_LAYERS,
        "full_fan_speed_layer": _FAN_OFF_LAYERS + _FAN_RAMP_LAYERS + 1,
        "min_fan_speed": _MIN_FAN_PCT,
        "max_fan_speed": _MAX_FAN_PCT,
        "bridge_fan_speed": _BRIDGE_FAN_PCT,
        "bridge_flow_ratio": _BRIDGE_FLOW_PCT / 100,
        "overhang_fan_pct": _OVERHANG_FAN_PCT,
        "top_fan_pct": _TOP_FAN_PCT,
        "ironing_fan_pct": _IRONING_FAN_PCT,
        "interface_fan_pct": _INTERFACE_FAN_PCT,
        "support_fan_pct": _SUPPORT_FAN_PCT,
        "seam_extra_retract": _SEAM_EXTRA_RETRACT_MM,
        "seam_flow_pct": _SEAM_FLOW_PCT,
        "seam_fan_pwm": _SEAM_FAN_PCT,
        "seam_join_speed": _SEAM_JOIN_SPEED_MM_S,
        "first_layer_speed": _FIRST_LAYER_SPEED_MM_S,
        "max_print_speed": _MAX_PRINT_SPEED_MM_S,
        "first_layer_acceleration": _FIRST_LAYER_ACCEL,
        "default_acceleration": _DEFAULT_ACCEL,
        "pa_k": _PA_K,
        "flow_ramp": ",".join(map(str, _FLOW_RAMP)),
        "cap_extrusion_layers": _CAP_EXTRUSION_LAYERS,
        "first_layer_motion_layers": _FIRST_LAYER_MOTION_LAYERS,
        "skirts": _SKIRT_LOOPS,
        "min_skirt_length": _SKIRT_SIDE_MM,
        "pp_skirt_origin_x": _SKIRT_ORIGIN_X_MM,
        "pp_skirt_origin_y": _SKIRT_ORIGIN_Y_MM,
        "pp_skirt_loop_offset_mm": _SKIRT_LOOP_OFFSET_MM,
        "pp_skirt_extrusion_mm_per_mm": _SKIRT_EXTRUSION_MM_PER_MM,
        "first_layer_height": _FIRST_LAYER_HEIGHT_MM,
        "first_layer_temperature": int(_FIRST_LAYER_TEMPERATURE_C),
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

    # Helper functions for common conversions
    def get_int(key: str, default: int) -> int:
        return bundle.get(key, default, converter=int)

    def get_float(key: str, default: float) -> float:
        return bundle.get(key, default, converter=float)

    def get_pwm(key: str, default_pct: int) -> int:
        return pct_to_pwm(get_int(key, default_pct))

    def get_speed_f(key: str, default_mm_s: float) -> int:
        return int(get_float(key, default_mm_s) * 60)

    fan_off = get_int("disable_fan_first_layers", _FAN_OFF_LAYERS)
    full_fan = get_int("full_fan_speed_layer", fan_off + _FAN_RAMP_LAYERS + 1)
    bridge_ratio = get_float("bridge_flow_ratio", _BRIDGE_FLOW_PCT / 100)
    bridge_flow_pct = int(bridge_ratio * 100) if bridge_ratio <= 1 else int(bridge_ratio)
    wall_early_f, max_infill_f, cap_extrusion_f, default_motion_f = _nozzle_speed_caps({
        "nozzle_diameter": str(get_float("nozzle_diameter", _NOZZLE_DIAMETER_MM)),
        "pp_wall_speed_mm_s": str(bundle.get("pp_wall_speed_mm_s", "")),
        "pp_infill_speed_mm_s": str(bundle.get("pp_infill_speed_mm_s", "")),
        "pp_cap_speed_mm_s": str(bundle.get("pp_cap_speed_mm_s", "")),
    })

    return {
        "retract_mm": get_float("retract_length", _RETRACT_LENGTH_MM),
        "retract_f": get_speed_f("retract_speed", _RETRACT_SPEED_MM_S),
        "retract_lift": get_float("retract_lift", _RETRACT_LIFT_MM),
        "fan_off_layers": fan_off,
        "full_fan_layer": full_fan,
        "min_fan_pwm": get_pwm("min_fan_speed", _MIN_FAN_PCT),
        "max_fan_pwm": get_pwm("max_fan_speed", _MAX_FAN_PCT),
        "bridge_fan_pwm": get_pwm("bridge_fan_speed", _BRIDGE_FAN_PCT),
        "bridge_flow_pct": bridge_flow_pct,
        "overhang_fan_pwm": get_pwm("overhang_fan_pct", _OVERHANG_FAN_PCT),
        "top_fan_pwm": get_pwm("top_fan_pct", _TOP_FAN_PCT),
        "ironing_fan_pwm": get_pwm("ironing_fan_pct", _IRONING_FAN_PCT),
        "interface_fan_pwm": get_pwm("interface_fan_pct", _INTERFACE_FAN_PCT),
        "support_fan_pwm": get_pwm("support_fan_pct", _SUPPORT_FAN_PCT),
        "seam_extra_retract": get_float("seam_extra_retract", _SEAM_EXTRA_RETRACT_MM),
        "seam_flow_pct": get_int("seam_flow_pct", _SEAM_FLOW_PCT),
        "seam_fan_pwm": get_pwm("seam_fan_pwm", _SEAM_FAN_PCT),
        "seam_join_f": get_speed_f("seam_join_speed", _SEAM_JOIN_SPEED_MM_S),
        "first_layer_f": get_speed_f("first_layer_speed", _FIRST_LAYER_SPEED_MM_S),
        "wall_early_f": wall_early_f,
        "max_infill_f": max_infill_f,
        "cap_extrusion_f": cap_extrusion_f,
        "max_print_f": get_speed_f("max_print_speed", _MAX_PRINT_SPEED_MM_S),
        "default_motion_f": default_motion_f,
        "first_layer_accel": get_int("first_layer_acceleration", _FIRST_LAYER_ACCEL),
        "default_accel": get_int("default_acceleration", _DEFAULT_ACCEL),
        "pa_k": get_float("pa_k", _PA_K),
        "flow_ramp": _cfg_flow_ramp({"flow_ramp": bundle.get("flow_ramp", ",".join(map(str, _FLOW_RAMP)))}, _FLOW_RAMP),
        "cap_extrusion_layers": get_int("cap_extrusion_layers", _CAP_EXTRUSION_LAYERS),
        "first_layer_motion_layers": get_int("first_layer_motion_layers", _FIRST_LAYER_MOTION_LAYERS),
        "skirt_loops": get_int("skirts", _SKIRT_LOOPS),
        "skirt_side_mm": get_float("min_skirt_length", _SKIRT_SIDE_MM),
        "skirt_origin_x_mm": get_float("pp_skirt_origin_x", _SKIRT_ORIGIN_X_MM),
        "skirt_origin_y_mm": get_float("pp_skirt_origin_y", _SKIRT_ORIGIN_Y_MM),
        "skirt_loop_offset_mm": get_float("pp_skirt_loop_offset_mm", _SKIRT_LOOP_OFFSET_MM),
        "skirt_extrusion_mm_per_mm": get_float("pp_skirt_extrusion_mm_per_mm", _SKIRT_EXTRUSION_MM_PER_MM),
        "first_layer_height_mm": get_float("first_layer_height", _FIRST_LAYER_HEIGHT_MM),
        "first_layer_temperature_c": str(get_int("first_layer_temperature", int(_FIRST_LAYER_TEMPERATURE_C))),
    }
