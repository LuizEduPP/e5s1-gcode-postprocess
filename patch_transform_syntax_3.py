with open("scripts/gcode_transform.py", "r") as f:
    content = f.read()

content = content.replace("                            layer_count, layer_fan_cap = _begin_layer(out, actions, stripped, layer_count, profile)", "            layer_count, layer_fan_cap = _begin_layer(out, actions, stripped, layer_count, profile)")

with open("scripts/gcode_transform.py", "w") as f:
    f.write(content)
