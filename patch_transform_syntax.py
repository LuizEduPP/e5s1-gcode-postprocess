with open("scripts/gcode_transform.py", "r") as f:
    content = f.read()

content = content.replace("    return feat, boost_fan, cool_boostdef transform_gcode(", "    return feat, boost_fan, cool_boost\n\n\ndef transform_gcode(")

with open("scripts/gcode_transform.py", "w") as f:
    f.write(content)
