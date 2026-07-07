# E5S1 / E3 Pro G-code Post-Process

G-code post-processor tuned for **Creality Ender-5 S1** or **Ender-3 Pro**, both with **0.8 mm** nozzle. This is not a generic slicer profile — speed caps, fan curves, retraction, pressure advance, and skirt geometry assume the selected printer and nozzle size.

PrusaSlicer supplies sliced geometry; this pipeline injects machine-specific fan ramps, flow tuning, seam handling, pressure advance, startup repair, and adhesion skirt logic.

No external config bundle is required. Printer presets live in `scripts/gcode_postprocess.py` (`PRINTER_PRESETS`). The optional `; prusaslicer_config` block at the end of exported G-code is read **for analysis only** (layer count, layer height, logs) — it does **not** override the hardcoded profile from `build_printer_profile()`.

## Stack

- Python 3.11+ (stdlib only — no third-party dependencies)
- PrusaSlicer 2.x (`post_process` hook)
- Target printers:
  - **E5S1** (`e5s1`, default): Creality Ender-5 S1, 0.8 mm high-flow Spider, direct drive
  - **E3 Pro** (`e3pro`): Creality Ender-3 Pro, 0.8 mm stock hotend, bowden
- Target firmware: **Marlin** (linear advance via `M900 K`; requires `LIN_ADVANCE` enabled in firmware)

## Quick setup

```bash
git clone https://github.com/LuizEduPP/e5s1-gcode-postprocess.git
cd e5s1-gcode-postprocess
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

In PrusaSlicer → **Print Settings → Output options → Post-processing scripts**, add:

**Ender-5 S1 (default):**

```ini
python3 /absolute/path/to/scripts/gcode_postprocess.py
```

**Ender-3 Pro 0.8 mm** — set `GCODE_PRINTER` in the environment (wrapper script or system env):

```ini
GCODE_PRINTER=e3pro python3 /absolute/path/to/scripts/gcode_postprocess.py
```

Use the **absolute** path to `gcode_postprocess.py`. PrusaSlicer appends the `.gcode` file path as the last argument automatically — do **not** add the file path or extra flags in that field.

### Windows (PrusaSlicer)

On Windows, **do not** point post-processing at the `.py` file alone — PrusaSlicer will try to run it as an executable and fail with **Win32 error 193**. Also avoid `python3` (often missing) and Linux-only syntax like `GCODE_PRINTER=e3pro python3 ...`.

1. Copy `scripts/gcode_postprocess.py` and the matching `.bat` wrapper to the same folder (e.g. `C:\Users\Pichau\Documents\`).
2. Install [Python 3.11+](https://www.python.org/downloads/) and tick **“Add python.exe to PATH”**.
3. In PrusaSlicer → **Print Settings → Output options → Post-processing scripts**, use the **full path to the `.bat`**:

**E5S1:**

```ini
C:\Users\Pichau\Documents\gcode_postprocess_e5s1.bat
```

**E3 Pro:**

```ini
C:\Users\Pichau\Documents\gcode_postprocess_e3pro.bat
```

Test in `cmd`:

```bat
py -3 C:\Users\Pichau\Documents\gcode_postprocess.py
C:\Users\Pichau\Documents\gcode_postprocess_e5s1.bat C:\path\to\test.gcode
```

If `py` is not found, use `python` instead (the `.bat` tries both).

**Logs (standalone copy):** with only `gcode_postprocess.py` in e.g. `C:\Users\Pichau\Documents\`, logs are written to `C:\Users\Pichau\Documents\logs\` (`e5s1_events.log`, `e5s1_state.json`). No repo folder required.

**Important:** the in-slicer G-code preview shows the file **before** post-processing ([official docs](https://help.prusa3d.com/article/post-processing-scripts_283913)). To verify processing, open the exported `.gcode` (Downloads, SD card, etc.) in a text editor: line 3 should be `; --- E5S1 postprocess ---` or `; --- E3PRO postprocess ---` depending on the preset.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GCODE_PRINTER` | No | Printer preset: `e5s1` (default), `e3pro` / `ender3pro` |
| `GCODE_POSTPROCESS_LOG_DIR` | No | Override log folder (default: `logs/` beside script, or repo `logs/` in dev) |
| `E5S1_EXPORT_DIR` | No | Extra folder to search for recent post-processed exports (default: `~/Downloads`) |

## Tuning

Edit constants at the top of `scripts/gcode_postprocess.py` for the E5S1 baseline, or extend `E3PRO_08_OVERRIDES` in `PRINTER_PRESETS` for the Ender-3 Pro preset (`PA_K`, `FLOW_RAMP`, `FAN_*`, `RETRACT_*`, `SEAM_*`, `SKIRT_*`, `NOZZLE_*_MM_S`, etc.). Typed contracts: `PrinterProfile` (`E5S1Profile` alias), `GcodeAnalysis`, `GcodeStats` (`TypedDict`).

Linear speed caps (`NOZZLE_WALL_MM_S`, `NOZZLE_INFILL_MM_S`, etc.) are in **mm/s** and converted to G-code `F` (mm/min) via `mm_s_to_f()` — they are **not** multiplied by nozzle diameter.

## Commands

Manual run (verbose logging to `logs/` and stdout):

```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from gcode_postprocess import run_postprocess
sys.exit(run_postprocess([Path('model.gcode')], quiet=False))
"
```

PrusaSlicer entry point (quiet; PrusaSlicer passes the path):

```bash
python3 scripts/gcode_postprocess.py /path/to/model.gcode
```

Reprocess ignoring the idempotency marker:

```bash
python3 scripts/gcode_postprocess.py -f /path/to/model.gcode
```

Ender-3 Pro preset (manual CLI):

```bash
GCODE_PRINTER=e3pro python3 scripts/gcode_postprocess.py /path/to/model.gcode
# or
python3 scripts/gcode_postprocess.py --printer e3pro /path/to/model.gcode
```

Logs and last-run state: `logs/e5s1_events.log`, `logs/e5s1_state.json` (gitignored).

## Architecture

Monolithic pipeline in `scripts/gcode_postprocess.py` (~2750 lines):

```
PostProcessApp.run()
  → parse_prusa_config (once per file)
  → analyze → GcodeAnalysis
  → skip if marker present (unless force=True)
  → strip_pp_lines (on reprocess: dedupe prior M900 PA lines)
  → transform_gcode
       · per-line transformers (fan, flow, caps, seams, bridges, layers)
       · repair_startup (G28, mesh, M109/M190, purge, Z-fix, skirt)
       · repair_perimeter_seam_join (closed loops: join speed + seam flow at close)
       · repair_small_perimeter_speed (tiered caps: loops + open segments, all layers)
       · repair_coast / repair_travel_coast / repair_travel_retract
       · repair_travel_start_boost / repair_deretract
       · repair_stale_layer_wipe / repair_stale_layer_gap
       · repair_layer_marker
       · strip_pp_lines (remove in-body M900 PA before final inject)
       · inject_pa
  → validate → write in place
  → analysis_after_transform + stats → logs/e5s1_state.json
```

**Per-line transformers** (fixed order): F tracking, startup macro fix, header/marker, `;TYPE:` features, ironing fan, layer boundary, `M204` accel cap (`P` and legacy `S`), fan cap, extrusion speed/volumetric cap, travel cap.

**Post-transform repairs**

| Repair | Behavior |
|--------|----------|
| **Startup** | `G28` if missing; `M420 S1` + `M420 Z10` after homing if no mesh/`G29`; `M190` if only `M140`; `M109` if missing; purge block if no startup extrusion; Z-fix on postprocess lines; `G90` before purge/skirt when head is in `G91` |
| **Overhangs without support** | `max_part_cooling`: full fan PWM on overhang/perimeter features |
| **Small perimeters** | Tiered speed on full segment — loops (circles/squares/tubes) and open walls; all layers |
| **Perimeter seam join** | Closed loops: join speed cap; small loops (&lt;55 mm): 105% flow + 4% E on last point; external+internal |
| **Coast + wipe + deretract** | Coast before layer retract; 2 mm wipe after layer retract; slow deretract (`F700`) on small positive E-only moves |
| **Travel (infill only)** | Coast/retract/boost only on long infill→infill travels (&gt; 5 mm), never on walls |
| **Layer markers** | Normalizes `;BEFORE_LAYER_CHANGE` / `G92 E0` sync when absent |

**Idempotency:** files containing `; --- E5S1 postprocess ---` are skipped unless `force=True` / `-f`.

**Analysis vs tuning:** `parse_prusa_config` feeds layer count and metadata; `build_e5s1_profile()` defines PWM, retract, PA, and speed limits.

**Pressure advance:** `apply_pa()` emits per-feature `M900` during transform (scaled K for infill, perimeter, bridge, ironing). Before write, `strip_pp_lines()` removes those in-body `M900` lines; `inject_pa()` inserts a single `M900 K{PA_K}` in the startup head (after last extrusion or `M109`) if none is present. Exported G-code therefore carries one global PA value unless the slicer already placed `M900` in the head.

## Default hardware profile

Calibrated for **Ender-5 S1 + 0.8 mm nozzle** (constants in `gcode_postprocess.py`):

| Parameter | Value |
|-----------|-------|
| Printer | Creality Ender-5 S1 |
| Nozzle | 0.8 mm (high-flow / Spider) |
| Build volume margins (skirt) | 2–218 mm (X/Y) |
| First layer height (profile default) | 0.24 mm |
| Fan off layers | 1 |
| Full fan layer | 4 |
| Pressure advance (`PA_K`) | 0.034 |
| Max volumetric flow | 30 mm³/s |
| External / internal wall cap | 52 / 62 mm/s |
| Infill speed cap | 105 mm/s |
| Early-layer extrusion cap (layer 2 only) | 40 mm/s |
| Travel speed cap | 150 mm/s |
| First-layer print speed | 26 mm/s |
| Flow ramp (layers 1–4) | 100%, 97%, 98%, 100% |
| Layer accel (layers 1–3 / 4+) | 800 / 4000 mm/s² (`M204 P`) |
| Retraction | 1.2 mm @ 50 mm/s, Z-hop 0.4 mm |
| Skirt (if injected) | 3 loops, 40 mm side, origin (3, 3) mm |
| Small-part skirt offset | 2.5 mm (bbox &lt; 45 mm) |
| Seam flow / join speed | small loop: 105% + E×1.04 / 18 mm/s close cap |
| Small loops L2+ (perimeter) | tiny &lt;30 mm → 20 / small &lt;55 → 26 mm/s; ≥55 mm → perfil rápido |
| Small loops L1 (perimeter) | tiny &lt;35 mm → 14 / loop &lt;100 mm → 16 / open &lt;30 → 14 mm/s |
| Mesh on start (if injected) | `M420 S1` + `M420 Z10` fade |

## License

MIT — see [LICENSE](LICENSE).
