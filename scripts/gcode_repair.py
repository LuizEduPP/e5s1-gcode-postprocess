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
    BED_X_MIN,
    BED_X_MAX,
    BED_Y_MIN,
    BED_Y_MAX,
    SKIRT_OFFSET_MM,
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


def find_print_bounding_box(lines: list[str]) -> tuple[float, float, float, float] | None:
    """Scan print movements to find print bounding box (X/Y min/max)."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    has_moves = False

    x_re = re.compile(r"\b[Xx]([\d.-]+)")
    y_re = re.compile(r"\b[Yy]([\d.-]+)")
    e_re = re.compile(r"\b[Ee]([\d.-]+)")

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue

        if stripped.upper().startswith(("G1", "G2", "G3")):
            e_match = e_re.search(stripped)
            if e_match:
                e_val = e_match.group(1)
                # Ensure it's not a retraction move (E-...) or zero extrusion
                if not e_val.startswith("-") and e_val != "0":
                    x_match = x_re.search(stripped)
                    y_match = y_re.search(stripped)
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


def skirt_gcode(
    profile: E5S1Profile,
    z: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[str]:
    z_val = z if z is not None else profile["first_layer_height_mm"]
    lines = [pp_skirt_comment(), pp_skirt_z(z_val)]

    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox
        base_x0 = max(BED_X_MIN, min_x - SKIRT_OFFSET_MM)
        base_y0 = max(BED_Y_MIN, min_y - SKIRT_OFFSET_MM)
        base_x1 = min(BED_X_MAX, max_x + SKIRT_OFFSET_MM)
        base_y1 = min(BED_Y_MAX, max_y + SKIRT_OFFSET_MM)
    else:
        # Fallback to corner square
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
                pp_skirt_travel(x0, y0),
                pp_skirt_extrude(x1, y0, segment_e_x),
                pp_skirt_extrude(x1, y1, segment_e_y),
                pp_skirt_extrude(x0, y1, segment_e_x),
                pp_skirt_extrude(x0, y0, segment_e_y),
            ]
        )
    lines.append(pp_skirt_reset_e())
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
        + buckets["g28"]
        + buckets["mesh"]
        + buckets["heat"]
        + buckets["purge"]
        + buckets["skirt"]
        + buckets["other"]
    )


def repair_gcode(lines: list[str], profile: E5S1Profile, pa_fw: str = "marlin") -> tuple[list[str], list[str]]:
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
    if g28_idx is not None and "M420" not in head_join and "G29" not in head_join and "BED_MESH" not in head_join:
        _insert_after(head, g28_idx, pp_mesh_enable(pa_fw))
        actions.append("mesh_enabled")
        head_text = "\n".join(head)

    if not M109_RE.search(head_text):
        hotend_c = profile["first_layer_temperature_c"]
        for line in head:
            if m := M104_RE.match(line.strip()):
                hotend_c = m.group(1)
        mesh_idx = _line_index(head, M420_RE) or _line_index(head, re.compile(r"BED_MESH", re.I))
        _insert_after(head, mesh_idx if mesh_idx is not None else g28_idx, pp_wait_hotend(hotend_c))
        actions.append("m109_added")
        head_text = "\n".join(head)

    if not any(G1_EXTRUDE_RE.match(line.strip()) for line in head):
        m109_idx = _line_index(head, M109_RE)
        nozzle_diameter = profile.get("nozzle_diameter_mm", 0.8)
        first_layer_height = profile["first_layer_height_mm"]
        _insert_after(head, m109_idx, pp_purge(nozzle_diameter, first_layer_height))
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
        bbox = find_print_bounding_box(tail)
        head = _insert_skirt_block(head, skirt_gcode(profile, bbox=bbox))
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
