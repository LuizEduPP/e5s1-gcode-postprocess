with open("scripts/gcode_repair.py", "r") as f:
    content = f.read()

import re

# We need to change _insert_after to handle multiline blocks.
# The original:
# def _insert_after(lines: list[str], idx: int | None, line: str) -> None:
#     lines.insert((idx + 1) if idx is not None else _comment_prefix_len(lines), line)

def replace_insert_after(match):
    return """def _insert_after(lines: list[str], idx: int | None, line: str) -> None:
    insert_idx = (idx + 1) if idx is not None else _comment_prefix_len(lines)
    for part in reversed(line.split("\\n")):
        lines.insert(insert_idx, part)"""

content = re.sub(r'def _insert_after.*?lines\.insert.*?\n', replace_insert_after, content, flags=re.DOTALL)

with open("scripts/gcode_repair.py", "w") as f:
    f.write(content)
