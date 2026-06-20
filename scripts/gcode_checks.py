"""G-code analysis and validation — read-only inspection of slicer output."""
from __future__ import annotations

from typing import TypedDict

from config import (
    HEAD_SCAN_BYTES,
    INVALID_MACRO_SNIPPET,
    LAYER_BEFORE_MARKER,
    LAYER_CHANGE_MARKER,
    LARGE_GCODE_BYTES,
    MARKER,
    PP_FAN_TAGS,
    SLICER_META_SCAN_BYTES,
    SUPPORT_OVERHANG_MIN,
    Z_MIN_WARN,
    AFTER_LAYER_MARKER,
    METADATA_SCAN_BYTES,
    THUMBNAIL_BEGIN,
    THUMBNAIL_END,
    TYPE_INTERFACE,
    TYPE_IRONING,
    TYPE_OVERHANG,
    TYPE_SUPPORT,
    TYPE_SUPPORT_MAT,
    TYPE_TOP_SOLID,
)
from gcode_patterns import (
    FAN_ON_RE,
    G1_EXTRUDE_RE,
    G28_RE,
    G29_RE,
    LAYER_H_PATH_RE,
    LAYER_H_RE,
    M109_RE,
    M900_RE,
    PA_KLIPPER_RE,
    PP_FAN_RE,
    SLICER_TIME_RE,
    Z_MOVE_RE,
    count_layers,
    has_skirt_or_brim,
)
from profile import parse_prusa_config, resolve_pa_firmware

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


def slicer_print_time(text: str) -> str | None:
    m = SLICER_TIME_RE.search(text)
    return m.group(1).strip() if m else None


def _slicer_metadata(text: str) -> tuple[str | None, float | None]:
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
        est_raw = slicer_print_time(text[-SLICER_META_SCAN_BYTES:])
    return est_raw, layer_h


def is_postprocessed(text: str) -> bool:
    return MARKER in text


def path_hint(*paths) -> str:
    return " ".join(str(p) for p in paths if p)


def layer_h_from_hint(hint: str) -> float | None:
    m = LAYER_H_PATH_RE.search(hint)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_slicer_seconds(time_str: str | None) -> int | None:
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


def _startup_text(text: str) -> str:
    for marker in (LAYER_CHANGE_MARKER, LAYER_BEFORE_MARKER, AFTER_LAYER_MARKER):
        if marker in text:
            return text.split(marker, 1)[0]
    return text


def count_type_markers(text: str, tag: str) -> int:
    return text.count(tag)


def is_large_gcode(text: str) -> bool:
    return len(text) > LARGE_GCODE_BYTES


def needs_support(overhang_markers: int, has_support: bool) -> bool:
    return overhang_markers >= SUPPORT_OVERHANG_MIN and not has_support


def count_pp_fan_lines(text: str, large: bool) -> int:
    if large:
        return sum(text.count(tag) for tag in PP_FAN_TAGS)
    return len(PP_FAN_RE.findall(text))


def analyze_gcode(text: str, hint: str = "") -> GcodeAnalysis:
    large = is_large_gcode(text)
    prusa_cfg = parse_prusa_config(text)
    has_sup = TYPE_SUPPORT in text or TYPE_SUPPORT_MAT in text or TYPE_INTERFACE in text
    has_skirt, has_brim = has_skirt_or_brim(text)
    overhang = count_type_markers(text, TYPE_OVERHANG)
    top_lines = count_type_markers(text, TYPE_TOP_SOLID)
    ironing_lines = count_type_markers(text, TYPE_IRONING)
    interface_lines = count_type_markers(text, TYPE_INTERFACE)
    cfg_ironing = prusa_cfg.get("ironing", "0") not in ("0", "false", "")
    has_ironing = ironing_lines > 0 or cfg_ironing
    top_pattern = prusa_cfg.get("top_solid_infill_pattern") or None
    if large:
        extrude_lines = max(text.count("\nG1"), top_lines * 50, 1)
    else:
        extrude_lines = sum(1 for ln in text.splitlines() if G1_EXTRUDE_RE.match(ln.strip()))
    est_raw, layer_h = _slicer_metadata(text)
    if layer_h is None:
        lh = prusa_cfg.get("layer_height") or prusa_cfg.get("first_layer_height")
        if lh:
            try:
                layer_h = float(lh.replace(",", "."))
            except ValueError:
                pass
    if layer_h is None and hint:
        layer_h = layer_h_from_hint(hint)
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return {
        "overhang_markers": overhang,
        "has_support": has_sup,
        "has_skirt": has_skirt,
        "has_brim": has_brim,
        "needs_support": needs_support(overhang, has_sup),
        "layers": count_layers(text, prusa_cfg),
        "top_lines": top_lines,
        "ironing_lines": ironing_lines,
        "interface_lines": interface_lines,
        "has_ironing": has_ironing,
        "top_pattern": top_pattern,
        "extrude_lines": extrude_lines,
        "layer_h": layer_h,
        "est_seconds": parse_slicer_seconds(est_raw),
        "slicer_time": est_raw,
        "lines": line_count,
        "large": large,
    }


def analysis_for_state(analysis: GcodeAnalysis, **extra: str) -> dict:
    return {
        **{k: v for k, v in analysis.items() if v is not None and k != "large"},
        **extra,
    }


def _has_pressure_advance(text: str) -> bool:
    pa_fw = resolve_pa_firmware(text[:HEAD_SCAN_BYTES])
    if pa_fw == "none":
        return True
    return bool(PA_KLIPPER_RE.search(text)) if pa_fw == "klipper" else bool(M900_RE.search(text))


def gcode_stats(text: str, analysis: GcodeAnalysis | None = None, fan_pp: int | None = None) -> dict:
    a = analysis or analyze_gcode(text)
    return {
        "layers": a["layers"],
        "lines": a["lines"],
        "fan_pp": fan_pp if fan_pp is not None else count_pp_fan_lines(text, a["large"]),
        "postprocessed": is_postprocessed(text),
        "pressure_advance": _has_pressure_advance(text[:HEAD_SCAN_BYTES]),
        **{k: a[k] for k in _STAT_FIELDS},
    }


def validate_text(
    text: str,
    expect_postprocess: bool = False,
    analysis: GcodeAnalysis | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    analysis = analysis or analyze_gcode(text)
    startup = _startup_text(text)
    large = analysis["large"]
    pp = is_postprocessed(text)

    if INVALID_MACRO_SNIPPET in text[:HEAD_SCAN_BYTES] and not pp:
        errors.append("Invalid macro first_layer_height[0] in gcode")

    if expect_postprocess and not pp:
        warnings.append("Missing E5S1 marker — post-process not applied")
    elif expect_postprocess and count_pp_fan_lines(text, large) == 0:
        warnings.append("Marker present but no post-process M106 fan commands")

    if not pp:
        if not _has_pressure_advance(text[:HEAD_SCAN_BYTES]):
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
