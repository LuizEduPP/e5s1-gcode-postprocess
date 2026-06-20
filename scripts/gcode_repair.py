"""Structural G-code repair: startup, skirt, layer markers, PA injection."""
from __future__ import annotations

import re

from config import (
    LAYER_BEFORE_MARKER,
    LAYER_CHANGE_MARKER,
    PA_PROBE_LINES,
    Z_APPROACH_MAX,
    Z_MIN_WARN,
    AFTER_LAYER_MARKER,
    LAYER_N_MARKER,
)
from gcode_emit import (
    PP_SKIRT,
    pa_command,
    pp_homing,
    pp_layer_sync,
    pp_mesh_enable,
    pp_purge,
    pp_skirt_comment,
    pp_skirt_extrude,
    pp_skirt_reset_e,
    pp_skirt_travel,
    pp_skirt_z,
    pp_wait_hotend,
    pp_z_fix_suffix,
)
from gcode_patterns import (
    G1_EXTRUDE_RE,
    G28_RE,
    M104_RE,
    M109_RE,
    M420_RE,
    M900_RE,
    MOTION_RE,
    PA_KLIPPER_RE,
    Z_MOVE_RE,
    count_layers,
    has_skirt_or_brim,
)
from profile import E5S1Profile


def head_index(lines: list[str]) -> int:
    return next(
        (
            i
            for i, line in enumerate(lines)
            if LAYER_BEFORE_MARKER in line or LAYER_CHANGE_MARKER in line or AFTER_LAYER_MARKER in line
        ),
        min(len(lines), PA_PROBE_LINES),
    )


def skirt_gcode(profile: E5S1Profile, z: float | None = None) -> list[str]:
    z_val = z if z is not None else profile["first_layer_height_mm"]
    lines = [pp_skirt_comment()]
    for loop in range(profile["skirt_loops"]):
        offset_mm = loop * profile["skirt_loop_offset_mm"]
        x0 = profile["skirt_origin_x_mm"] + offset_mm
        y0 = profile["skirt_origin_y_mm"] + offset_mm
        x1 = x0 + profile["skirt_side_mm"]
        y1 = y0 + profile["skirt_side_mm"]
        segment_e = profile["skirt_side_mm"] * profile["skirt_extrusion_mm_per_mm"]
        lines.extend(
            [
                pp_skirt_z(z_val),
                pp_skirt_travel(x0, y0),
                pp_skirt_extrude(x1, y0, segment_e),
                pp_skirt_extrude(x1, y1, segment_e),
                pp_skirt_extrude(x0, y1, segment_e),
                pp_skirt_extrude(x0, y0, segment_e),
                pp_skirt_reset_e(),
            ]
        )
    return lines


def _fix_z_line(line: str, target: float) -> tuple[str, bool]:
    m = Z_MOVE_RE.match(line.strip())
    if not m:
        return line, False
    z = float(m.group(1))
    if Z_MIN_WARN < z < Z_APPROACH_MAX:
        return re.sub(r"(\bZ)([\d.]+)", rf"\g<1>{target}", line, count=1, flags=re.I) + pp_z_fix_suffix(), True
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
    lines.insert((idx + 1) if idx is not None else _comment_prefix_len(lines), line)


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
        if G28_RE.search(line.strip()):
            buckets["g28"].append(line)
        elif M420_RE.match(line.strip()) or "postprocess mesh" in low:
            buckets["mesh"].append(line)
        elif M109_RE.match(line.strip()) or M104_RE.match(line.strip()):
            buckets["heat"].append(line)
        elif "postprocess purge" in low:
            buckets["purge"].append(line)
        else:
            buckets["other"].append(line)
    return (
        comments
        + buckets["g28"]
        + buckets["mesh"]
        + buckets["heat"]
        + buckets["purge"]
        + buckets["skirt"]
        + buckets["other"]
    )


def repair_gcode(lines: list[str], profile: E5S1Profile) -> tuple[list[str], list[str]]:
    actions: list[str] = []
    head_end = head_index(lines)
    head = list(lines[:head_end])
    tail = lines[head_end:]
    head_text = "\n".join(head)

    if not G28_RE.search(head_text):
        head.insert(_comment_prefix_len(head), pp_homing())
        actions.append("g28_added")
        head_text = "\n".join(head)

    g28_idx = _line_index(head, G28_RE)
    head_join = head_text.upper()
    if g28_idx is not None and "M420" not in head_join and "G29" not in head_join:
        _insert_after(head, g28_idx, pp_mesh_enable())
        actions.append("mesh_enabled")
        head_text = "\n".join(head)

    if not M109_RE.search(head_text):
        hotend_c = profile["first_layer_temperature_c"]
        for line in head:
            if m := M104_RE.match(line.strip()):
                hotend_c = m.group(1)
        mesh_idx = _line_index(head, M420_RE)
        _insert_after(head, mesh_idx if mesh_idx is not None else g28_idx, pp_wait_hotend(hotend_c))
        actions.append("m109_added")
        head_text = "\n".join(head)

    if not any(G1_EXTRUDE_RE.match(line.strip()) for line in head):
        m109_idx = _line_index(head, M109_RE)
        _insert_after(head, m109_idx, pp_purge())
        actions.append("purge_added")

    fixed_head: list[str] = []
    for line in head:
        new_line, changed = _fix_z_line(line, profile["first_layer_height_mm"])
        fixed_head.append(new_line)
        if changed:
            actions.append("z_fix")
    head = fixed_head

    body_preview = "\n".join(head + tail)
    has_skirt, has_brim = has_skirt_or_brim(body_preview)
    if not has_skirt and not has_brim and PP_SKIRT not in body_preview:
        head = _insert_skirt_block(head, skirt_gcode(profile))
        actions.append(f"skirt_added×{profile['skirt_loops']}")

    head = _normalize_startup_order(head)

    out = head + tail
    body = "\n".join(out)
    if body.count(LAYER_BEFORE_MARKER) == 0 and body.count(AFTER_LAYER_MARKER) > 0:
        patched: list[str] = []
        for line in out:
            if AFTER_LAYER_MARKER in line:
                if not patched or patched[-1].strip() != LAYER_BEFORE_MARKER:
                    patched.append(LAYER_BEFORE_MARKER)
                    patched.append(pp_layer_sync())
                    actions.append("layer_marker")
            patched.append(line)
        out = patched
    elif count_layers(body) == 0:
        for i, line in enumerate(out):
            if LAYER_N_MARKER in line:
                out[i:i] = [LAYER_BEFORE_MARKER, pp_layer_sync()]
                actions.append("layer_marker")
                break

    return out, actions


def inject_pa(lines: list[str], pa_fw: str, pa_k: float) -> tuple[list[str], str | None]:
    if not pa_k or pa_fw == "none":
        return lines, None
    head = lines[:head_index(lines)]
    has_pa = any(PA_KLIPPER_RE.search(line) for line in head) if pa_fw == "klipper" else any(
        M900_RE.match(line.strip()) for line in head
    )
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
    cmd = pa_command(pa_fw, pa_k)
    return lines[:extrusion_idx + 1] + [cmd] + lines[extrusion_idx + 1:], f"pa_{pa_fw}_{pa_k}"
