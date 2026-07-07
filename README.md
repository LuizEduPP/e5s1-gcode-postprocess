# E5S1 G-code Post-Process

Pós-processador de G-code calibrado para a **Creality Ender-5 S1** com bico **0.8 mm high-flow** (hotend Spider). Não é um perfil genérico de fatiador — limites de velocidade, curvas de ventoinha, retração, pressure advance e geometria de saia assumem esta impressora e este diâmetro de bico.

O PrusaSlicer fornece a geometria fatiada; este pipeline injeta rampas de fan, ajuste de fluxo, tratamento de costura, PA, reparo de startup e saia de adesão específicos da máquina.

Nenhuma config externa é necessária — todo o tuning está no bloco de constantes no topo de `scripts/gcode_postprocess.py`. Edite esses valores para alterar o comportamento. O bloco opcional `; prusaslicer_config` no final do G-code é lido **somente para análise** (contagem de camadas, layer height, logs) — **não** sobrescreve o perfil hardcoded.

## Stack

- Python 3.11+ (stdlib only — sem dependências de terceiros)
- PrusaSlicer 2.x (hook `post_process`)
- Impressora alvo: **Creality Ender-5 S1**, bico **0.8 mm**
- Firmware alvo: **Marlin** (linear advance via `M900 K`)

## Setup rápido

```bash
git clone https://github.com/LuizEduPP/e5s1-gcode-postprocess.git
cd e5s1-gcode-postprocess
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

No PrusaSlicer → **Print Settings → Output options → Post-processing scripts**, adicione:

```ini
python3 /caminho/absoluto/para/scripts/gcode_postprocess.py
```

Use o caminho absoluto para `gcode_postprocess.py`. O PrusaSlicer passa o caminho do G-code exportado como primeiro argumento a cada fatiamento.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `E5S1_EXPORT_DIR` | Não | Pasta extra para buscar exports recentes pós-processados (padrão: `~/Downloads`, `~/Documents`, `~/Documentos`) |

Tuning da Ender-5 S1 / 0.8 mm: constantes no topo de `scripts/gcode_postprocess.py` (`PA_K`, `FLOW_RAMP`, `FAN_*`, `RETRACT_*`, `SEAM_*`, `SKIRT_*`, etc.). Contratos tipados: `E5S1Profile`, `GcodeAnalysis`, `GcodeStats` (`TypedDict`).

## Comandos

Pós-processar um ou mais arquivos manualmente (saída verbosa):

```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from gcode_postprocess import run_postprocess
sys.exit(run_postprocess([Path('model.gcode')], quiet=False))
"
```

Ponto de entrada do PrusaSlicer (silencioso, após cada export):

```bash
python3 scripts/gcode_postprocess.py /path/to/model.gcode
```

Logs e estado da última execução: `logs/` (gitignored).

## Arquitetura

Pipeline monolítico em `scripts/gcode_postprocess.py` (~1900 linhas):

```
PostProcessApp.run()
  → parse_prusa_config (1× por arquivo)
  → analyze → GcodeAnalysis
  → strip_pp_lines (dedupe PA se reprocessamento)
  → transform_gcode
       · transformadores por linha (fan, flow, caps, seams, bridges, camadas)
       · repair_startup (G28, mesh, M109/M190, purge, Z-fix, saia)
       · repair_small_perimeters (loops fechados, arcos G2/G3)
       · repair_coast (anti-fiapo antes da retração de camada)
       · repair_layer_marker
       · inject_pa
  → validate → write in place
  → analysis_after_transform (cache) + stats em logs/e5s1_state.json
```

**Transformadores** (ordem fixa): tracking de F, macro de startup, cabeçalho/marcador, `;TYPE:` features, fan de ironing, fronteira de camada, cap de aceleração, cap de fan, cap de velocidade/volumétrico, cap de travel.

**Reparos pós-transform:**
- **Startup** — homing, mesh, M109, **M190** (se só M140), purge, Z-fix (ignora `G91`), `G90` antes de purge/saia
- **Overhangs sem suporte** — **max part cooling** (fan máximo por camada + PWM max em overhang/perímetro); action `max_part_cooling`
- **Perímetros / loops pequenos** — arcos G2/G3; loop &lt; 25 mm ou raio &lt; 12 mm: boost 108% nos primeiros ~2 mm, slow fechamento nos últimos 3 mm, fan off em loops &lt; 15 mm (camadas 1–3)
- **Coast + wipe + deretract** — coast antes de retração de camada e travel &gt; 5 mm; wipe 2 mm após retração; deretract lento F700
- **Marcadores de camada** — normaliza `;BEFORE_LAYER_CHANGE` / sync quando ausentes

**Idempotência:** arquivos com `; --- E5S1 postprocess ---` são ignorados, salvo `force=True` em `run_postprocess()`.

**Análise vs tuning:** `parse_prusa_config` alimenta contagem de camadas e metadados; `build_e5s1_profile()` define PWM, retract, PA e limites de velocidade.

## Perfil de hardware (padrões)

Calibrado para **Ender-5 S1 + bico 0.8 mm** (constantes em `gcode_postprocess.py`):

| Parâmetro | Valor |
|-----------|-------|
| Impressora | Creality Ender-5 S1 |
| Bico | 0.8 mm (high-flow / Spider) |
| Altura 1ª camada | 0.24 mm |
| Camadas sem fan | 2 |
| Camada fan pleno | 5 |
| Pressure advance (`PA_K`) | 0.03 |
| Fluxo volumétrico máx. | 24 mm³/s |
| Paredes / infill (cap) | 38 / 75 mm/s |
| Rampa fluxo camada 2 | 93% |
| Saia | 3 loops, 40 mm lado |
| Skirt offset pequena | 2,5 mm (bbox &lt; 45 mm) |
| Fluxo / join de costura | 96% / 18 mm/s |

## Licença

MIT — veja [LICENSE](LICENSE).
