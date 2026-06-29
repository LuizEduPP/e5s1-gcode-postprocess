with open("scripts/config.py", "r") as f:
    content = f.read()

new_purge = """STARTUP_PURGE = \"\"\"G1 X2.0 Y20 F5000.0 ; postprocess purge
G1 Z0.28 F1500.0 ; postprocess purge
G1 X2.0 Y145.0 Z0.28 F1500.0 E15 ; postprocess purge
G1 X2.3 Y145.0 Z0.28 F5000.0 ; postprocess purge
G1 X2.3 Y20 Z0.28 F1500.0 E30 ; postprocess purge
G92 E0 ; postprocess purge\"\"\""""

content = content.replace('STARTUP_PURGE = "G1 X3 Y200 E20 F600 ; postprocess purge"', new_purge)

with open("scripts/config.py", "w") as f:
    f.write(content)
