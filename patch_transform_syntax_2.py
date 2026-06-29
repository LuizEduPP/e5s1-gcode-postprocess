with open("scripts/gcode_transform.py", "r") as f:
    content = f.read()

content = content.replace("surface_kind, boost_fan, cool_boost = _handle_type_feature\\(", "surface_kind, boost_fan, cool_boost = _handle_type_feature(")

with open("scripts/gcode_transform.py", "w") as f:
    f.write(content)
