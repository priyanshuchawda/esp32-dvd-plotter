# ESP32 ↔ HW-130 adapter PCB

Uno-form adapter so the **HW-130 stacks like on an Arduino Uno**, while the
**ESP32-DevKit** plugs in beside it (right wing — not under the shield).

| | |
| --- | --- |
| KiCad project | [`esp32_hw130_adapter/`](esp32_hw130_adapter/) |
| Regenerator | [`generate_adapter.py`](generate_adapter.py) |
| Gerbers | [`out/gerbers.zip`](out/gerbers.zip) |
| Preview | [`out/adapter_top.png`](out/adapter_top.png) |
| Pin map | [`out/pinmap.md`](out/pinmap.md) |
| BOM | [`BOM.md`](BOM.md) |

**Board size ≈ 121 × 94 mm · 2-layer · DRC clean (0 errors)**

## How it works

```text
┌─────────────────────────────┬──────────────────────┐
│  Arduino R3 male headers    │  ESP32 DevKit        │
│  HW-130 stacks here         │  2×15 female sockets │
│  (same as Uno)              │  USB ↑               │
│                             │                      │
│  J_5V ── external 5 V       │                      │
└─────────────────────────────┴──────────────────────┘
```

Traces match firmware [`src/esp32/esp32_plotter`](../../src/esp32/esp32_plotter/):

| Shield | ESP32 |
| --- | --- |
| D12 | GPIO18 |
| D4 | GPIO19 |
| D7 | GPIO23 |
| D8 | GPIO13 |
| D11 | GPIO25 |
| D3 | GPIO26 |
| D6 | GPIO27 |
| D5 | GPIO32 |
| D10 (SERVO_1) | GPIO33 |
| 5V / GND | J_5V only |

## Open / rebuild

```bash
# GUI
kicad cad/pcb/esp32_hw130_adapter/esp32_hw130_adapter.kicad_pro

# Regenerate PCB from script (needs KiCad’s python3.14 + pcbnew)
python3.14 cad/pcb/generate_adapter.py
```

## Order / assemble

1. Upload [`out/gerbers.zip`](out/gerbers.zip) to any PCB fab (JLCPCB, PCBWay, …).
2. Solder parts from [`BOM.md`](BOM.md).
3. Plug ESP32 into the wing; stack HW-130 on the left headers.
4. Remove yellow **PWR** jumper; motors on `EXT_PWR`; logic 5 V into **J_5V**.
5. Flash `src/esp32/esp32_plotter` and run `$COILTEST`.

Until the PCB arrives, use Dupont jumpers — same nets — see
[`hardware/WIRING.md`](../../hardware/WIRING.md).
