# E5S1 G-code Post-Process

G-code post-processor tuned for the **Creality Ender-5 S1** with a **0.8 mm high-flow nozzle** (Spider hotend). Not a generic slicer profile — speed caps, fan curves, retraction, pressure advance, and skirt geometry assume this printer and nozzle size.

PrusaSlicer supplies sliced geometry; this pipeline injects machine-specific fan ramps, flow tuning, seam handling, pressure advance, startup repair, and skirt adhesion.

No external config required — all tuning lives in the constants block at the top of `scripts/gcode_postprocess.py` (lines ~16–275). Edit those values to change behavior. The optional `; prusaslicer_config` tail in exported G-code is read **only for analysis** (layer count, layer height, logs) — it does not override tuning.

## Stack

- Python 3.11+ (stdlib only — no third-party dependencies)
- PrusaSlicer 2.x (`post_process` hook)
- Target printer: **Creality Ender-5 S1**, **0.8 mm nozzle**
- Target firmware: **Marlin** (linear advance via `M900 K`)

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

Machine tuning for the Ender-5 S1 / 0.8 mm setup is in the consolidated constants block at the top of `scripts/gcode_postprocess.py` (`PA_K`, `FLOW_RAMP`, `FAN_*`, `RETRACT_*`, `SEAM_*`, `SKIRT_*`, etc.).

## Commands

Post-process one or more files manually (verbose output):

```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from gcode_postprocess import run_postprocess
sys.exit(run_postprocess([Path('model.gcode')], quiet=False))
"
```

PrusaSlicer entry point (quiet, used automatically after each export):

```bash
python3 scripts/gcode_postprocess.py /path/to/model.gcode
```

Logs and last-run state are written to `logs/` (gitignored).

## Architecture

Single-file pipeline in `scripts/gcode_postprocess.py`:

```
read G-code → analyze (metadata from prusaslicer_config tail) → build hardcoded E5S1 profile
    → transform (fan ramp, flow, caps, seams, bridges) → repair startup/skirt/PA → validate → write in place
```

**Idempotency:** files containing `; --- E5S1 postprocess ---` are skipped unless re-run with `force=True` via `run_postprocess()`.

## Hardware profile (defaults)

Calibrated for **Ender-5 S1 + 0.8 mm nozzle**. Values below match the constants block in `scripts/gcode_postprocess.py`:

| Parameter | Value |
|-----------|-------|
| Printer | Creality Ender-5 S1 |
| Nozzle | 0.8 mm (high-flow / Spider) |
| First layer height | 0.24 mm |
| Fan off layers | 2 |
| Full fan layer | 5 |
| Pressure advance (`PA_K`) | 0.03 |
| Max volumetric flow | 15 mm³/s |
| Skirt | 3 loops, 40 mm side, origin (3, 3) mm |
| Seam flow / join | 96% / 18 mm/s |

## License

MIT — see [LICENSE](LICENSE).
