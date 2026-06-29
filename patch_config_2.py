with open("scripts/config.py", "r") as f:
    content = f.read()

content = content.replace('ENABLE_MESH_ON_START = "M420 S1 ; postprocess mesh"', 'ENABLE_MESH_ON_START = "M420 S1 Z10 ; postprocess mesh"')

with open("scripts/config.py", "w") as f:
    f.write(content)
