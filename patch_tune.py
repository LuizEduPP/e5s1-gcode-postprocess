with open("scripts/gcode_tune.py", "r") as f:
    content = f.read()

import re

# Remove seam_end_line
content = re.sub(r'def seam_end_line.*?return lines\n\n\n', '', content, flags=re.DOTALL)

# Remove apply_seam_block_start
content = re.sub(r'def apply_seam_block_start.*?return flow_seam, join_slow\n\n\n', '', content, flags=re.DOTALL)

# Remove sanitize_startup_line G29 removal
content = re.sub(r'    if G29_RE.match\(stripped\.strip\(\)\):\n        return None, "g29_removed"\n', '', content)

# Remove imports
content = re.sub(r'    pp_seam_end,\n', '', content)
content = re.sub(r'    pp_seam_retract,\n', '', content)
content = re.sub(r'    pp_seam_deretract,\n', '', content)

with open("scripts/gcode_tune.py", "w") as f:
    f.write(content)
