"""E5S1 profile using bundle.ini with auto-initialization and update."""
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

# Default values (fallback if no config exists)
_DEFAULTS: dict[str, Any] = {
    "nozzle_diameter": 0.8,
    "pp_wall_speed_mm_s": 28,
    "pp_infill_speed_mm_s": 50,
    "pp_cap_speed_mm_s": 22,
    "pp_default_speed_mm_s": 38,
    "retract_length": 1.2,
    "retract_speed": 50.0,
    "retract_lift": 0.6,
    "disable_fan_first_layers": 2,
    "full_fan_speed_layer": 6,
    "min_fan_speed": 65,
    "max_fan_speed": 100,
    "bridge_fan_speed": 100,
    "bridge_flow_ratio": 0.92,
    "first_layer_speed": 18.0,
    "max_print_speed": 200.0,
    "first_layer_acceleration": 600,
    "default_acceleration": 1500,
    "first_layer_height": 0.24,
    "first_layer_temperature": 210,
    "cap_extrusion_layers": 4,
    "first_layer_motion_layers": 4,
    "flow_ramp": "100,90,94,97,100",
    "seam_extra_retract": 0.6,
    "seam_flow_pct": 94,
    "seam_fan_pct": 80,
    "seam_join_speed": 15.0,
    "overhang_fan_pct": 85,
    "top_fan_pct": 70,
    "ironing_fan_pct": 30,
    "interface_fan_pct": 75,
    "support_fan_pct": 75,
    "pa_k": 0.06,
    "skirts": 3,
    "min_skirt_length": 40.0,
    "pp_skirt_origin_x": 3.0,
    "pp_skirt_origin_y": 3.0,
    "pp_skirt_loop_offset_mm": 2.0,
    "pp_skirt_extrusion_mm_per_mm": 0.1,
}

_CUSTOM_PARAM_KEYS = (
    "custom_parameters_print",
    "custom_parameters_filament",
    "custom_parameters_printer",
)


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
    """Initialize bundle.ini with defaults and prusa-derived config (auto-save)."""
    section_order = ["print", "filament", "printer", "defaults"]
    section_to_use = section_order[0]

    # Use prusa config first, then defaults, then set in bundle.ini if missing
    for key, default in _DEFAULTS.items():
        if not bundle.has(key):
            # Check if prusa has this key
            if key in prusa_cfg:
                bundle.set(key, prusa_cfg[key], section_to_use)
            else:
                bundle.set(key, default, "defaults")


def build_e5s1_profile(
    prusa_cfg: dict[str, str] | None = None,
    bundle: BundleConfig | None = None,
) -> E5S1Profile:
    """Build config, auto-initializing bundle.ini with defaults if needed."""
    prusa_cfg = _merge_custom_parameters(prusa_cfg or {})
    bundle = bundle or get_bundle_config()

    # Initialize bundle if needed
    _init_bundle_defaults(bundle, prusa_cfg)

    # Section priority: prusa config > print > filament > printer > defaults
    section_order: list[str] = []
    for prefix in ("printer:", "filament:", "print:"):
        section_order.extend([s for s in bundle.sections if s.startswith(prefix)])
    section_order.extend([s for s in bundle.sections if not any(s.startswith(p) for p in ("printer:", "filament:", "print:"))])
    section_order.append("defaults")

    # Helper to get value from prusa config first, then bundle, then default
    def get_val(key: str, default: Any = None, to_int: bool = False, to_float: bool = False) -> Any:
        if key in prusa_cfg:
            raw = prusa_cfg[key]
            try:
                if to_int:
                    return int(float(raw))
                if to_float:
                    return float(raw)
                return raw
            except ValueError:
                pass
        return bundle.get(
            key,
            default,
            section_priority=section_order,
            converter=lambda x: int(float(x)) if to_int else (float(x) if to_float else x),
        )

    nozzle_diameter = get_val("nozzle_diameter", _DEFAULTS["nozzle_diameter"], to_float=True)
    bridge_ratio = get_val("bridge_flow_ratio", _DEFAULTS["bridge_flow_ratio"], to_float=True)
    bridge_flow_pct = int(bridge_ratio * 100) if bridge_ratio <= 1 else int(bridge_ratio)

    # Calculate speed caps
    wall_early_f_raw = get_val("pp_wall_speed_mm_s", _DEFAULTS["pp_wall_speed_mm_s"], to_float=True)
    max_infill_f_raw = get_val("pp_infill_speed_mm_s", _DEFAULTS["pp_infill_speed_mm_s"], to_float=True)
    cap_extrusion_f_raw = get_val("pp_cap_speed_mm_s", _DEFAULTS["pp_cap_speed_mm_s"], to_float=True)
    default_motion_f_raw = get_val("pp_default_speed_mm_s", _DEFAULTS["pp_default_speed_mm_s"], to_float=True)

    wall_early_f = int(nozzle_diameter * wall_early_f_raw * 60)
    max_infill_f = int(nozzle_diameter * max_infill_f_raw * 60)
    cap_extrusion_f = int(nozzle_diameter * cap_extrusion_f_raw * 60)
    default_motion_f = int(nozzle_diameter * default_motion_f_raw * 60)

    # Parse flow ramp
    flow_ramp_str = get_val("flow_ramp", _DEFAULTS["flow_ramp"])
    try:
        flow_ramp = [int(x.strip()) for x in str(flow_ramp_str).split(",") if x.strip()]
    except Exception:
        flow_ramp = [100, 90, 94, 97, 100]

    # Build and return profile
    return {
        "retract_mm": get_val("retract_length", _DEFAULTS["retract_length"], to_float=True),
        "retract_f": int(get_val("retract_speed", _DEFAULTS["retract_speed"], to_float=True) * 60),
        "retract_lift": get_val("retract_lift", _DEFAULTS["retract_lift"], to_float=True),
        "fan_off_layers": get_val("disable_fan_first_layers", _DEFAULTS["disable_fan_first_layers"], to_int=True),
        "full_fan_layer": get_val("full_fan_speed_layer", _DEFAULTS["full_fan_speed_layer"], to_int=True),
        "min_fan_pwm": pct_to_pwm(get_val("min_fan_speed", _DEFAULTS["min_fan_speed"], to_int=True)),
        "max_fan_pwm": pct_to_pwm(get_val("max_fan_speed", _DEFAULTS["max_fan_speed"], to_int=True)),
        "bridge_fan_pwm": pct_to_pwm(get_val("bridge_fan_speed", _DEFAULTS["bridge_fan_speed"], to_int=True)),
        "bridge_flow_pct": bridge_flow_pct,
        "overhang_fan_pwm": pct_to_pwm(get_val("overhang_fan_pct", _DEFAULTS["overhang_fan_pct"], to_int=True)),
        "top_fan_pwm": pct_to_pwm(get_val("top_fan_pct", _DEFAULTS["top_fan_pct"], to_int=True)),
        "ironing_fan_pwm": pct_to_pwm(get_val("ironing_fan_pct", _DEFAULTS["ironing_fan_pct"], to_int=True)),
        "interface_fan_pwm": pct_to_pwm(get_val("interface_fan_pct", _DEFAULTS["interface_fan_pct"], to_int=True)),
        "support_fan_pwm": pct_to_pwm(get_val("support_fan_pct", _DEFAULTS["support_fan_pct"], to_int=True)),
        "seam_extra_retract": get_val("seam_extra_retract", _DEFAULTS["seam_extra_retract"], to_float=True),
        "seam_flow_pct": get_val("seam_flow_pct", _DEFAULTS["seam_flow_pct"], to_int=True),
        "seam_fan_pwm": pct_to_pwm(get_val("seam_fan_pct", _DEFAULTS["seam_fan_pct"], to_int=True)),
        "seam_join_f": int(get_val("seam_join_speed", _DEFAULTS["seam_join_speed"], to_float=True) * 60),
        "first_layer_f": int(get_val("first_layer_speed", _DEFAULTS["first_layer_speed"], to_float=True) * 60),
        "wall_early_f": wall_early_f,
        "max_infill_f": max_infill_f,
        "cap_extrusion_f": cap_extrusion_f,
        "max_print_f": int(get_val("max_print_speed", _DEFAULTS["max_print_speed"], to_float=True) * 60),
        "default_motion_f": default_motion_f,
        "first_layer_accel": get_val("first_layer_acceleration", _DEFAULTS["first_layer_acceleration"], to_int=True),
        "default_accel": get_val("default_acceleration", _DEFAULTS["default_acceleration"], to_int=True),
        "pa_k": get_val("pa_k", _DEFAULTS["pa_k"], to_float=True),
        "flow_ramp": flow_ramp,
        "cap_extrusion_layers": get_val("cap_extrusion_layers", _DEFAULTS["cap_extrusion_layers"], to_int=True),
        "first_layer_motion_layers": get_val("first_layer_motion_layers", _DEFAULTS["first_layer_motion_layers"], to_int=True),
        "skirt_loops": get_val("skirts", _DEFAULTS["skirts"], to_int=True),
        "skirt_side_mm": get_val("min_skirt_length", _DEFAULTS["min_skirt_length"], to_float=True),
        "skirt_origin_x_mm": get_val("pp_skirt_origin_x", _DEFAULTS["pp_skirt_origin_x"], to_float=True),
        "skirt_origin_y_mm": get_val("pp_skirt_origin_y", _DEFAULTS["pp_skirt_origin_y"], to_float=True),
        "skirt_loop_offset_mm": get_val("pp_skirt_loop_offset_mm", _DEFAULTS["pp_skirt_loop_offset_mm"], to_float=True),
        "skirt_extrusion_mm_per_mm": get_val("pp_skirt_extrusion_mm_per_mm", _DEFAULTS["pp_skirt_extrusion_mm_per_mm"], to_float=True),
        "first_layer_height_mm": get_val("first_layer_height", _DEFAULTS["first_layer_height"], to_float=True),
        "first_layer_temperature_c": str(get_val("first_layer_temperature", _DEFAULTS["first_layer_temperature"], to_int=True)),
    }
