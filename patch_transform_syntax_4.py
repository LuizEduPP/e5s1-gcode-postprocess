with open("scripts/gcode_transform.py", "r") as f:
    content = f.read()

# Fix the stray line 261: `if surface_kind in ("external", "perimeter"):`
content = content.replace('                if surface_kind in ("external", "perimeter"):\n                if cool_boost:', '                if cool_boost:')

with open("scripts/gcode_transform.py", "w") as f:
    f.write(content)
