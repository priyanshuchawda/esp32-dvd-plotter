# Project status

Last updated for the **Uno + HW-130** path. Full measurements live in
[`FINDINGS.md`](../FINDINGS.md).

## Done

| Area | Status |
| --- | --- |
| Motors identified as bipolar steppers | Done (~13 Ω coils) |
| Uno + HW-130 wiring / motion | Done (X=M1/M2, Y=M3/M4) |
| Speed test through 150 rpm | Done |
| Bed measured | Done — **55 × 50 mm** |
| steps/mm calibrated | Done — **2.058** both axes (10 mm → 10 mm) |
| Uno G-code firmware | Done — `src/uno_plotter` @ 115200 |
| Laptop G-code tools (text / image / handwriting) | Done |
| Path simulator + paper preview | Done — `sim/simulate.py --paper` |
| Coil SPICE sweep | Done — `sim/spice/` |
| OpenSCAD frame model | Done — `cad/plotter.scad` (bed sized to measurements) |
| Architecture / workflow diagrams | Done — `docs/` |
| GitHub docs (README, FINDINGS, wiring) | Done |
| Dry-run square + “hi” on hardware (no ink) | Done |

## Not done (needs parts or a decision)

| Item | Why it waits | When |
| --- | --- | --- |
| SG90 pen lift | No servo on hand | Plug into shield `SERVO_1`, tune `$PENUP`/`$PENDOWN` |
| Real ink on paper | No pen/paper | Same G-code you already simulated |
| External 5 V / higher current supply | USB OK for unloaded tests | Before long plots or servo |
| ESP32 + 74HC595 bypass | Uno path works; soldering breaks AFMotor | After ink plots are good — see `hardware/WIRING.md` |
| Fine handwriting quality | ~0.5 mm/step is coarse | Larger letters, or finer mechanics later |
| Your-style handwriting fine-tune | Needs online stroke samples | Optional; neural model already runs |

## Ready-to-run checklist (software)

```bash
# 1. Preview any job (no hardware)
python3 sim/simulate.py test-square-uno.gcode --paper -o sim/out/page.png

# 2. Flash Uno plotter
arduino-cli compile -b arduino:avr:uno src/uno_plotter
arduino-cli upload  -b arduino:avr:uno -p /dev/ttyACM0 src/uno_plotter

# 3. Park sleds at paper corner, then plot
tools/send_gcode.py -p /dev/ttyACM0 -b 115200 test-square-uno.gcode

# 4. CAD render
openscad -D 'part="assembly"' --imgsize=1100,850 \
  -o cad/out/assembly.png cad/plotter.scad
```

## Verdict

**Software + simulation + CAD + docs are ready** for the Uno machine you have.
What is left is **physical consumables** (pen, paper, optional servo) and the
optional ESP32 migration — not missing code for the current path.
