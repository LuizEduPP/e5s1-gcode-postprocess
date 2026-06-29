"""G-code transform loop — Prusa geometry in, E5S1 machine params out."""
from __future__ import annotations

import re
from datetime import datetime

from config import (
    LAYER_BEFORE_MARKER,
    LAYER_CHANGE_MARKER,
    LAYER_RETRACT,
    MARKER,
    M204_CAP_LAYERS,
    PA_PROBE_LINES,
    AFTER_LAYER_MARKER,
)
from gcode_patterns import F_RE, FAN_ON_RE, G1_EXTRUDE_RE, M204_S_RE, strip_pp_lines
from gcode_emit import (
    pp_accel,
    pp_cap_accel_suffix,
    pp_fan_bridge,
    pp_fan_capped,
    pp_fan_ironing,
    pp_fan_layer,
    pp_fan_overhang,
    pp_fan_restore,
    pp_fan_startup_off,
    pp_flow_bridge,
    pp_flow_layer,
    pp_flow_reset,
    pp_timestamp,
)
from gcode_features import type_feature
from gcode_repair import inject_pa, repair_gcode
from gcode_tune import (
    apply_feature_fan_tune,
    apply_seam_block_start,
    cap_f_line,
    fan_pwm_for_layer,
    layer_retract_lines,
    recent_retract,
    sanitize_startup_line,
    seam_end_line,
    speed_cap_for,
)
from profile import E5S1Profile, build_e5s1_profile, resolve_pa_firmware


def _apply_layer_start(
    out: list[str],
    actions: list[str],
    stripped: str,
    layer_count: int,
    profile: E5S1Profile,
) -> int | None:
    cap = fan_pwm_for_layer(layer_count, profile)
    out.append(stripped)
    ramp = profile["flow_ramp"]
    if layer_count <= len(ramp):
        flow = ramp[layer_count - 1]
        out.append(pp_flow_layer(layer_count, flow))
        actions.append(f"flow_l{layer_count}_S{flow}")
    elif layer_count == len(ramp) + 1:
        out.append(pp_flow_reset())
        actions.append("flow_reset")
    if cap is not None:
        out.append(pp_fan_layer(cap, layer_count))
        actions.append(f"fan_l{layer_count}_pwm_{cap}")
    if layer_count <= profile["first_layer_motion_layers"]:
        out.append(pp_accel(profile["first_layer_accel"]))
        actions.append(f"accel_l{layer_count}")
    elif layer_count == profile["first_layer_motion_layers"] + 1:
        out.append(pp_accel(profile["default_accel"]))
        actions.append(f"accel_default_l{layer_count}")
    return cap


def _begin_layer(
    out: list[str],
    actions: list[str],
    stripped: str,
    layer_count: int,
    profile: E5S1Profile,
) -> tuple[int, int | None]:
    layer_count += 1
    return layer_count, _apply_layer_start(out, actions, stripped, layer_count, profile)


def _restore_layer_fan(
    out: list[str],
    actions: list[str],
    layer_fan_cap: int | None,
) -> None:
    if layer_fan_cap is not None:
        out.append(pp_fan_restore(layer_fan_cap))
        actions.append("fan_restore")


def _handle_type_feature(
    out: list[str],
    actions: list[str],
    feat: str,
    stripped: str,
    lines: list[str],
    idx: int,
    *,
    layer_count: int,
    layer_fan_cap: int | None,
    skip_fan_at: set[int],
    cool_boost: bool,
    profile: E5S1Profile,
) -> tuple[str | None, bool, bool, bool, bool]:
    if cool_boost:
        _restore_layer_fan(out, actions, layer_fan_cap)
        cool_boost = False

    boost_fan = feat in (
        "top", "ironing", "interface", "support", "bottom", "external", "perimeter", "brim", "bridge", "overhang"
    )
    flow_seam = seam_join_slow = False

    if feat in ("external", "perimeter"):
        out.append(stripped)
        flow_seam, seam_join_slow = apply_seam_block_start(
            out, actions, feat, profile, layer_count
        )
        if skip_idx := apply_feature_fan_tune(
            out, actions, feat, lines, idx,
            layer_count=layer_count,
            layer_fan_cap=layer_fan_cap,
            profile=profile,
        ):
            skip_fan_at.add(skip_idx)
        return feat, boost_fan, cool_boost, flow_seam, seam_join_slow

    tuned = {"top", "ironing", "interface", "support", "bottom", "brim"}
    if feat in tuned:
        out.append(stripped)
        if skip_idx := apply_feature_fan_tune(
            out, actions, feat, lines, idx,
            layer_count=layer_count,
            layer_fan_cap=layer_fan_cap,
            profile=profile,
        ):
            skip_fan_at.add(skip_idx)
        return feat, boost_fan, cool_boost, False, False

    if feat == "other":
        return None, False, cool_boost, False, False

    out.append(stripped)
    return feat, boost_fan, cool_boost, False, False


def transform_gcode(
    lines: list[str],
    *,
    skip_overhang_fan: bool = False,
    prusa_cfg: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    actions: list[str] = []
    profile = build_e5s1_profile(prusa_cfg)
    pa_fw = resolve_pa_firmware("\n".join(lines[:PA_PROBE_LINES]))
    out: list[str] = []
    layer_count = 0
    in_startup = True
    layer_fan_cap: int | None = None
    boost_fan = False
    cool_boost = False
    flow_bridge = False
    flow_seam = False
    seam_join_slow = False
    surface_kind: str | None = None
    last_f = profile["default_motion_f"]
    skip_fan_at: set[int] = set()

    def _end_seam_block() -> None:
        nonlocal flow_seam, seam_join_slow
        if surface_kind not in ("external", "perimeter"):
            return
        for line in seam_end_line(profile):
            out.append(line)
        actions.append("seam_end")
        if flow_seam:
            out.append(pp_flow_reset())
            actions.append("flow_reset")
            flow_seam = False
        seam_join_slow = False

    def _reset_flow() -> None:
        nonlocal flow_bridge
        if flow_bridge:
            out.append(pp_flow_reset())
            actions.append("flow_reset")
            flow_bridge = False

    for i, line in enumerate(lines):
        stripped = line.rstrip("\n\r")
        upper = stripped.upper()
        fan_m = FAN_ON_RE.match(stripped)

        if i in skip_fan_at:
            continue

        if upper.startswith(("G0", "G1")) and (fm := F_RE.search(stripped)):
            last_f = int(fm.group(1))

        if in_startup:
            fixed, fix_action = sanitize_startup_line(stripped, profile["first_layer_height_mm"])
            if fix_action:
                actions.append(fix_action)
            if fixed is None:
                continue
            if fixed != stripped:
                stripped, upper = fixed, fixed.upper()
                fan_m = FAN_ON_RE.match(stripped)

        if stripped.startswith("; generated by"):
            out += [stripped, pp_timestamp(datetime.now().isoformat(timespec="seconds")), MARKER]
            actions.append("header")
            continue

        feat = type_feature(stripped)
        if feat in ("bridge", "overhang"):
            if surface_kind in ("external", "perimeter"):
                _end_seam_block()
            if cool_boost:
                _restore_layer_fan(out, actions, layer_fan_cap)
            _reset_flow()
            out.append(stripped)
            if feat == "bridge":
                out.append(pp_flow_bridge(profile["bridge_flow_pct"]))
                actions.append("flow_bridge")
                flow_bridge = True
                out.append(pp_fan_bridge(profile["bridge_fan_pwm"]))
                actions.append("fan_bridge")
            elif not skip_overhang_fan:
                out.append(pp_fan_overhang(profile["overhang_fan_pwm"]))
                actions.append("fan_overhang")
            boost_fan = True
            cool_boost = True
            surface_kind = feat
            continue

        if feat is not None:
            if surface_kind in ("external", "perimeter") and feat not in ("external", "perimeter"):
                _end_seam_block()
            _reset_flow()
            surface_kind, boost_fan, cool_boost, flow_seam, seam_join_slow = _handle_type_feature(
                out, actions, feat, stripped, lines, i,
                layer_count=layer_count,
                layer_fan_cap=layer_fan_cap,
                skip_fan_at=skip_fan_at,
                cool_boost=cool_boost,
                profile=profile,
            )
            continue

        if seam_join_slow and upper.startswith("G1") and " E" in upper and G1_EXTRUDE_RE.match(stripped):
            new_line, capped, last_f = cap_f_line(stripped, profile["seam_join_f"], last_f)
            out.append(new_line)
            if capped:
                actions.append("seam_join_slow")
            seam_join_slow = False
            continue

        if surface_kind == "ironing" and fan_m and "postprocess" not in stripped.lower():
            pwm = int(fan_m.group(1))
            if pwm != profile["ironing_fan_pwm"]:
                out.append(pp_fan_ironing(profile["ironing_fan_pwm"]))
                actions.append("fan_ironing")
            else:
                out.append(stripped)
            continue

        if LAYER_BEFORE_MARKER in stripped or AFTER_LAYER_MARKER in stripped:
            if surface_kind in ("external", "perimeter"):
                _end_seam_block()
            in_startup = False
            if cool_boost:
                _restore_layer_fan(out, actions, layer_fan_cap)
            _reset_flow()
            if LAYER_BEFORE_MARKER in stripped and LAYER_RETRACT and layer_count >= 1 and not recent_retract(out):
                out.extend(layer_retract_lines(profile))
                actions.append("retract_layer")
            boost_fan = False
            cool_boost = False
            surface_kind = None
            flow_seam = False
            seam_join_slow = False
            layer_count, layer_fan_cap = _begin_layer(out, actions, stripped, layer_count, profile)
            continue

        if LAYER_CHANGE_MARKER in stripped:
            in_startup = False
            if layer_count == 0:
                if surface_kind in ("external", "perimeter"):
                    _end_seam_block()
                if cool_boost:
                    _restore_layer_fan(out, actions, layer_fan_cap)
                _reset_flow()
                boost_fan = False
                cool_boost = False
                surface_kind = None
                layer_count, layer_fan_cap = _begin_layer(out, actions, stripped, layer_count, profile)
            else:
                out.append(stripped)
            continue

        if (m204_m := M204_S_RE.match(stripped) if 1 <= layer_count <= M204_CAP_LAYERS else None):
            cap_accel = profile["first_layer_accel"]
            if int(m204_m.group(1)) > cap_accel:
                out.append(
                    re.sub(r"(M204\s+)S\d+", rf"\g<1>S{cap_accel}", stripped, count=1, flags=re.I)
                    + pp_cap_accel_suffix()
                )
                actions.append(f"m204_cap_l{layer_count}")
            else:
                out.append(stripped)
            continue

        if in_startup and fan_m and int(fan_m.group(1)) > 0:
            out.append(pp_fan_startup_off())
            actions.append("fan_off_startup")
            continue

        if layer_fan_cap is not None and fan_m and not boost_fan and int(fan_m.group(1)) > layer_fan_cap:
            out.append(pp_fan_capped(layer_fan_cap))
            actions.append("fan_cap")
            continue

        f_cap = speed_cap_for(surface_kind, layer_count, in_startup, profile)
        if (
            upper.startswith("G1")
            and " E" in upper
            and G1_EXTRUDE_RE.match(stripped)
            and not fan_m
            and f_cap is not None
        ):
            new_line, capped, last_f = cap_f_line(stripped, f_cap, last_f)
            out.append(new_line)
            if capped:
                actions.append(f"cap_f_l{layer_count or 'startup'}")
            continue

        out.append(stripped)

    out, repair_actions = repair_gcode(out, profile)
    actions.extend(repair_actions)
    out = strip_pp_lines(out)
    out, pa_action = inject_pa(out, pa_fw, profile["pa_k"])
    if pa_action:
        actions.append(pa_action)
    return out, actions
