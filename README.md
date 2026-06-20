# E5S1 G-code Post-Process

G-code post-processor tuned for the **Creality Ender-5 S1** with a **0.8 mm high-flow nozzle** (Spider hotend). Not a generic slicer profile — speed caps, fan curves, retraction, pressure advance, and skirt geometry assume this printer and nozzle size.

PrusaSlicer supplies sliced geometry; this pipeline injects machine-specific fan ramps, flow tuning, seam handling, pressure advance, startup repair, and skirt adhesion.

No external config bundle required — defaults live in code for **Ender-5 S1 @ 0.8 mm**, with optional overrides from the `prusaslicer_config` block embedded in exported G-code.

## Stack

- Python 3.11+ (stdlib only — no third-party dependencies)
- PrusaSlicer 2.x (`post_process` hook)
- Target printer: **Creality Ender-5 S1**, **0.8 mm nozzle**
- Target firmware: Marlin (Klipper auto-detected when present)

## Quick setup

```bash
git clone https://github.com/LuizEduPP/e5s1-gcode-postprocess.git
cd e5s1-gcode-postprocess
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

In PrusaSlicer → **Print Settings → Output options → Post-processing scripts**, add:

```ini
python3 /absolute/path/to/scripts/gcode_postprocess.py
```

Use the absolute path to `gcode_postprocess.py`. PrusaSlicer passes the exported G-code file path as the first argument on every slice.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `E5S1_EXPORT_DIR` | No | Extra folder to scan for recent post-processed exports (default: `~/Downloads`, `~/Documents`, `~/Documentos`) |

Machine tuning for the Ender-5 S1 / 0.8 mm setup is in `scripts/profile.py` (retraction, fan curves, PA, skirt, seam). Slicer-exported values override defaults when present in the G-code tail block. Other printers or nozzle sizes require editing those constants.

## Commands

Post-process one or more files manually (verbose output):

```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from gcode_pipeline import run_postprocess
sys.exit(run_postprocess([Path('model.gcode')], quiet=False))
"
```

PrusaSlicer entry point (quiet, used automatically after each export):

```bash
python3 scripts/gcode_postprocess.py /path/to/model.gcode
```

Logs and last-run state are written to `logs/` (gitignored).

## Architecture

```
gcode_postprocess.py     PrusaSlicer entry — forwards to pipeline
        │
gcode_pipeline.py        File I/O, skip-if-processed, validation, logging
        │
        ├── gcode_checks.py      Analysis (layers, support, overhangs) + validation
        ├── gcode_export.py      Recent export discovery for state hints
        └── gcode_transform.py   Main line-by-line transform loop
                │
                ├── profile.py           E5S1 defaults + prusaslicer_config merge
                ├── gcode_tune.py          Fan / seam / speed / retraction tuning
                ├── gcode_repair.py        Startup fix, skirt injection, PA (M900)
                ├── gcode_features.py      ;TYPE feature classification
                ├── gcode_emit.py          Injected G-code line builders
                ├── gcode_patterns.py      Shared regex + strip helpers
                └── config.py              Markers, TYPE tags, scan limits
```

**Flow:** read G-code → parse optional `; prusaslicer_config` tail → build runtime profile → transform (fan ramp, flow, caps, seams, bridges) → repair startup/skirt/PA → validate → write in place.

**Idempotency:** files containing `; --- E5S1 postprocess ---` are skipped unless re-run with `force=True` in the pipeline API.

## Hardware profile (defaults)

Calibrated for **Ender-5 S1 + 0.8 mm nozzle**. Values below are the built-in baseline in `profile.py`:

| Parameter | Value |
|-----------|-------|
| Printer | Creality Ender-5 S1 |
| Nozzle | 0.8 mm (high-flow / Spider) |
| First layer height | 0.24 mm |
| Fan off layers | 2 |
| Full fan layer | 5 |
| Pressure advance (`pa_k`) | 0.08 |
| Skirt | 3 loops, 40 mm side, origin (3, 3) mm |

## License

MIT — see [LICENSE](LICENSE).
