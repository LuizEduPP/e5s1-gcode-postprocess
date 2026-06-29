import re

with open("scripts/gcode_transform.py", "r") as f:
    content = f.read()

# Fix remnants manually
content = content.replace("                    _end_seam_block()\n", "")
content = content.replace("                _end_seam_block()\n", "")
content = re.sub(r'        if seam_join_slow.*?continue\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'            flow_seam = False\n', '', content)
content = re.sub(r'            seam_join_slow = False\n', '', content)

with open("scripts/gcode_transform.py", "w") as f:
    f.write(content)
