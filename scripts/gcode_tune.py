"""Fan, seam, speed and retraction tuning for transform."""
from __future__ import annotations

import abc

from config import INVALID_MACRO_SNIPPET, PEEK_SLICER_FAN_WINDOW, PEEK_RETRACT_WINDOW
from gcode_features import preserves_geometry
from gcode_patterns import FAN_ON_RE, F_RE, RETRACT_RE
from profile import E5S1Profile
from gcode_emit import GCodeBuilder


class SpeedTuner:
    def cap_f_line(self, line: str, cap: int, last_f: int, builder: GCodeBuilder) -> tuple[str, bool, int]:
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
        self,
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


class RetractionTuner:
    def layer_retract_lines(self, profile: E5S1Profile, builder: GCodeBuilder) -> list[str]:
        lines: list[str] = []
        if profile["retract_lift"] > 0:
            lines.append(builder.z_hop(profile["retract_lift"]))
        lines.append(builder.layer_retract(profile["retract_mm"], profile["retract_f"]))
        return lines

    def recent_retract(self, out: list[str], window: int = PEEK_RETRACT_WINDOW, *, seam: bool = False) -> bool:
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


class IFeatureTuner(abc.ABC):
    @abc.abstractmethod
    def tune(self, out: list[str], actions: list[str], kind: str, lines: list[str], idx: int, layer_count: int, layer_fan_cap: int | None, profile: E5S1Profile, builder: GCodeBuilder) -> int | None:
        pass


class FanSpeedTuner(IFeatureTuner):
    def peek_slicer_fan(self, lines: list[str], idx: int, window: int = PEEK_SLICER_FAN_WINDOW) -> tuple[int | None, int | None]:
        end = min(idx + 1 + window, len(lines))
        for j in range(idx + 1, end):
            stripped = lines[j].strip()
            if (m := FAN_ON_RE.match(stripped)) and "postprocess" not in stripped.lower():
                return int(m.group(1)), j
            upper = stripped.upper()
            if upper.startswith(("G0", "G1")) and " E" in upper:
                break
        return None, None

    def e5s1_fan_target(self, kind: str, layer_count: int, layer_fan_cap: int | None, profile: E5S1Profile) -> tuple[int, str] | None:
        if kind == "top":
            return profile["top_fan_pwm"], "fan_top"
        if kind == "ironing":
            return profile["ironing_fan_pwm"], "fan_ironing"
        if kind == "interface":
            return profile["interface_fan_pwm"], "fan_interface"
        if kind == "support":
            return profile["support_fan_pwm"], "fan_support"
        if kind == "external" and layer_count > profile["fan_off_layers"]:
            return profile["seam_fan_pwm"], "fan_seam"
        if kind == "perimeter" and layer_count > profile["fan_off_layers"]:
            return min(profile["seam_fan_pwm"], profile["min_fan_pwm"]), "fan_seam"
        if kind in ("bottom", "external", "perimeter", "brim") and layer_count <= profile["fan_off_layers"]:
            target = layer_fan_cap if layer_fan_cap is not None else 0
            return target, "fan_adhesion"
        return None

    def fan_builder_for(self, kind: str, layer_count: int, profile: E5S1Profile, builder: GCodeBuilder):
        if kind in ("external", "perimeter"):
            if layer_count > profile["fan_off_layers"]:
                return builder.fan_seam
            return builder.fan_adhesion
        fb = builder.get_fan_builder(kind)
        return fb if fb else builder.fan_adhesion

    def tune(self, out: list[str], actions: list[str], kind: str, lines: list[str], idx: int, layer_count: int, layer_fan_cap: int | None, profile: E5S1Profile, builder: GCodeBuilder) -> int | None:
        slicer_fan, fan_idx = self.peek_slicer_fan(lines, idx)
        target = self.e5s1_fan_target(kind, layer_count, layer_fan_cap, profile)
        if not target:
            return None
        pwm, act = target
        if slicer_fan == pwm:
            return None
        out.append(self.fan_builder_for(kind, layer_count, profile, builder)(pwm))
        actions.append(act)
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
