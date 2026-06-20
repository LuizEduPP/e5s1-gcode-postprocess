#!/usr/bin/env python3
"""Entrada do PrusaSlicer (post_process) — nao remover este arquivo."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcode_pipeline import run_postprocess

if __name__ == "__main__":
    argv = sys.argv[1:]
    sys.exit(
        run_postprocess(
            [Path(p) for p in argv],
            quiet=True,
            argv=argv,
        )
    )
