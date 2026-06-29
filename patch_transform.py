import re

with open("scripts/gcode_transform.py", "r") as f:
    content = f.read()

# Remove imports
content = re.sub(r'    apply_seam_block_start,\n', '', content)
content = re.sub(r'    seam_end_line,\n', '', content)

# Remove _end_seam_block function definition completely (from def _end_seam_block to the next blank line before def _reset_flow)
content = re.sub(r'    def _end_seam_block\(\) -> None:.*?(?=    def _reset_flow)', '', content, flags=re.DOTALL)

# Remove calls to _end_seam_block()
content = re.sub(r'            if surface_kind in \("external", "perimeter"\):\n                _end_seam_block\(\)\n', '', content)
content = re.sub(r'            if surface_kind in \("external", "perimeter"\) and feat not in \("external", "perimeter"\):\n                _end_seam_block\(\)\n', '', content)

# Remove seam variables from transform_gcode initialization
content = re.sub(r'    flow_seam = False\n', '', content)
content = re.sub(r'    seam_join_slow = False\n', '', content)

# Update _handle_type_feature to remove seam logic
def replace_handle_type(match):
    return """def _handle_type_feature(
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
) -> tuple[str | None, bool, bool]:
    if cool_boost:
        _restore_layer_fan(out, actions, layer_fan_cap)
        cool_boost = False

    boost_fan = feat in (
        "top", "ironing", "interface", "support", "bottom", "external", "perimeter", "brim", "bridge", "overhang"
    )

    if feat in ("external", "perimeter"):
        out.append(stripped)
        if skip_idx := apply_feature_fan_tune(
            out, actions, feat, lines, idx,
            layer_count=layer_count,
            layer_fan_cap=layer_fan_cap,
            profile=profile,
        ):
            skip_fan_at.add(skip_idx)
        return feat, boost_fan, cool_boost

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
        return feat, boost_fan, cool_boost

    if feat == "other":
        return None, False, cool_boost

    out.append(stripped)
    return feat, boost_fan, cool_boost"""

content = re.sub(r'def _handle_type_feature\(.*?(?=def transform_gcode\()', replace_handle_type, content, flags=re.DOTALL)

# Update usages of _handle_type_feature return
content = re.sub(r'surface_kind, boost_fan, cool_boost, flow_seam, seam_join_slow = _handle_type_feature\(', r'surface_kind, boost_fan, cool_boost = _handle_type_feature\(', content)

# Remove the seam_join_slow block in transform_gcode loop
content = re.sub(r'        if seam_join_slow and upper\.startswith\("G1"\) and " E" in upper and G1_EXTRUDE_RE\.match\(stripped\):\n            new_line, capped, last_f = cap_f_line\(stripped, profile\["seam_join_f"\], last_f\)\n            out\.append\(new_line\)\n            if capped:\n                actions\.append\("seam_join_slow"\)\n            seam_join_slow = False\n            continue\n\n', '', content)

with open("scripts/gcode_transform.py", "w") as f:
    f.write(content)
