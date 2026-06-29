"""Post-process G-code line emitters (M/G codes and PP comment suffixes)."""
from __future__ import annotations

import abc
from config import ENABLE_MESH_ON_START, STARTUP_PURGE, KLIPPER_MESH_ENABLE

PP_SKIRT = "postprocess skirt"


class IGCodeEmitter(abc.ABC):
    @abc.abstractmethod
    def mesh_enable(self) -> str:
        pass

    @abc.abstractmethod
    def pressure_advance(self, pa_k: float) -> str:
        pass


class MarlinGCodeEmitter(IGCodeEmitter):
    def mesh_enable(self) -> str:
        return ENABLE_MESH_ON_START

    def pressure_advance(self, pa_k: float) -> str:
        return f"M900 K{pa_k} ; linear advance postprocess"


class KlipperGCodeEmitter(IGCodeEmitter):
    def mesh_enable(self) -> str:
        return KLIPPER_MESH_ENABLE

    def pressure_advance(self, pa_k: float) -> str:
        return f"SET_PRESSURE_ADVANCE ADVANCE={pa_k} ; linear advance postprocess"


class GCodeBuilder:
    def __init__(self, pa_fw: str = "marlin"):
        if pa_fw == "klipper":
            self.emitter: IGCodeEmitter = KlipperGCodeEmitter()
        else:
            self.emitter = MarlinGCodeEmitter()

    def timestamp(self, ts: str) -> str:
        return f"; postprocessed: {ts}"

    def flow_layer(self, layer: int, flow: int) -> str:
        return f"M221 S{flow} ; postprocess flow L{layer}"

    def flow_reset(self) -> str:
        return "M221 S100 ; postprocess flow normal"

    def flow_bridge(self, pct: int) -> str:
        return f"M221 S{pct} ; postprocess flow bridge"

    def z_hop(self, mm: float) -> str:
        return f"G1 Z{mm} F600 ; postprocess z hop"

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

    def fan_bridge(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan bridge postprocess"

    def fan_overhang(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan overhang postprocess"

    def fan_top(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan top postprocess"

    def fan_ironing(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan ironing postprocess"

    def fan_interface(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan interface postprocess"

    def fan_support(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan support postprocess"

    def fan_seam(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan seam postprocess"

    def fan_adhesion(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan adhesion postprocess"

    def fan_restore(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan restore postprocess"

    def fan_startup_off(self) -> str:
        return "M106 S0 ; fan OFF startup postprocess"

    def fan_capped(self, pwm: int) -> str:
        return f"M106 S{pwm} ; fan capped postprocess"

    def accel(self, accel: int) -> str:
        return f"M204 S{accel} ; postprocess accel"

    def cap_accel_suffix(self) -> str:
        return " ; postprocess cap accel"

    def pressure_advance(self, pa_k: float) -> str:
        return self.emitter.pressure_advance(pa_k)

    def get_fan_builder(self, feature: str):
        builders = {
            "top": self.fan_top,
            "ironing": self.fan_ironing,
            "interface": self.fan_interface,
            "support": self.fan_support,
            "bottom": self.fan_adhesion,
            "brim": self.fan_adhesion,
        }
        return builders.get(feature)
