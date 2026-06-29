"""Post-process G-code line emitters (M/G codes and PP comment suffixes)."""
from __future__ import annotations

from config import ENABLE_MESH_ON_START, STARTUP_PURGE, KLIPPER_MESH_ENABLE

PP_SKIRT = "postprocess skirt"


def pp_timestamp(ts: str) -> str:
    return f"; postprocessed: {ts}"


def pp_flow_layer(layer: int, flow: int) -> str:
    return f"M221 S{flow} ; postprocess flow L{layer}"


def pp_flow_reset() -> str:
    return "M221 S100 ; postprocess flow normal"


def pp_flow_bridge(pct: int) -> str:
    return f"M221 S{pct} ; postprocess flow bridge"


def pp_z_hop(mm: float) -> str:
    return f"G1 Z{mm} F600 ; postprocess z hop"


def pp_layer_retract(mm: float, retract_f: int) -> str:
    return f"G1 E-{mm} F{retract_f} ; postprocess layer retract"


def pp_homing() -> str:
    return "G28 ; postprocess homing"


def pp_wait_hotend(temp: str | int) -> str:
    return f"M109 S{temp} ; postprocess wait hotend"


def pp_mesh_enable(pa_fw: str = "marlin") -> str:
    if pa_fw == "klipper":
        return KLIPPER_MESH_ENABLE
    return ENABLE_MESH_ON_START


def pp_purge(nozzle_diameter: float = 0.8, first_layer_height: float = 0.24) -> str:
    e_first = 125.0 * first_layer_height * (nozzle_diameter * 1.25) / 2.405
    e_second = e_first * 2.0
    return f"""G1 X2.0 Y20 F5000.0 ; postprocess purge
G1 Z{first_layer_height:.3f} F1500.0 ; postprocess purge
G1 X2.0 Y145.0 Z{first_layer_height:.3f} F1500.0 E{e_first:.2f} ; postprocess purge
G1 X2.3 Y145.0 Z{first_layer_height:.3f} F5000.0 ; postprocess purge
G1 X2.3 Y20 Z{first_layer_height:.3f} F1500.0 E{e_second:.2f} ; postprocess purge
G92 E0 ; postprocess purge"""


def pp_z_fix_suffix() -> str:
    return " ; postprocess z fix"


def pp_layer_sync() -> str:
    return "G92 E0 ; postprocess layer sync"


def pp_cap_f_suffix() -> str:
    return " ; postprocess cap F"


def pp_skirt_comment() -> str:
    return f"; {PP_SKIRT}"


def pp_skirt_z(z: float) -> str:
    return f"G1 Z{z} F600 ; {PP_SKIRT}"


def pp_skirt_travel(x: float, y: float, f: int = 6000) -> str:
    return f"G1 X{x} Y{y} F{f} ; {PP_SKIRT}"


def pp_skirt_extrude(x: float, y: float, e: float, f: int = 600) -> str:
    return f"G1 X{x} Y{y} E{e:.2f} F{f} ; {PP_SKIRT}"


def pp_skirt_reset_e() -> str:
    return f"G92 E0 ; {PP_SKIRT}"


def pp_fan_layer(pwm: int, layer: int) -> str:
    return f"M106 S{pwm} ; fan postprocess layer {layer}"


def pp_fan_bridge(pwm: int) -> str:
    return f"M106 S{pwm} ; fan bridge postprocess"


def pp_fan_overhang(pwm: int) -> str:
    return f"M106 S{pwm} ; fan overhang postprocess"


def pp_fan_top(pwm: int) -> str:
    return f"M106 S{pwm} ; fan top postprocess"


def pp_fan_ironing(pwm: int) -> str:
    return f"M106 S{pwm} ; fan ironing postprocess"


def pp_fan_interface(pwm: int) -> str:
    return f"M106 S{pwm} ; fan interface postprocess"


def pp_fan_support(pwm: int) -> str:
    return f"M106 S{pwm} ; fan support postprocess"


def pp_fan_seam(pwm: int) -> str:
    return f"M106 S{pwm} ; fan seam postprocess"


def pp_fan_adhesion(pwm: int) -> str:
    return f"M106 S{pwm} ; fan adhesion postprocess"


def pp_fan_restore(pwm: int) -> str:
    return f"M106 S{pwm} ; fan restore postprocess"


def pp_fan_startup_off() -> str:
    return "M106 S0 ; fan OFF startup postprocess"


def pp_fan_capped(pwm: int) -> str:
    return f"M106 S{pwm} ; fan capped postprocess"


def pp_accel(accel: int) -> str:
    return f"M204 S{accel} ; postprocess accel"


def pp_cap_accel_suffix() -> str:
    return " ; postprocess cap accel"


def pa_command(pa_fw: str, pa_k: float) -> str:
    if pa_fw == "klipper":
        return f"SET_PRESSURE_ADVANCE ADVANCE={pa_k} ; linear advance postprocess"
    return f"M900 K{pa_k} ; linear advance postprocess"


FAN_BUILDERS = {
    "top": pp_fan_top,
    "ironing": pp_fan_ironing,
    "interface": pp_fan_interface,
    "support": pp_fan_support,
    "bottom": pp_fan_adhesion,
    "brim": pp_fan_adhesion,
}
