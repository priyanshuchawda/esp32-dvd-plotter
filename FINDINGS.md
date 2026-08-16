# Findings (Uno + HW-130 build)

Status as of the working bring-up on this frame. ESP32 + 74HC595 bypass is
deferred; finish drawing on the Uno first.

## Hardware that works

| Item | Result |
| --- | --- |
| Controllers | Arduino Uno + HW-130 (L293D) motor shield |
| Motors | DVD sled bipolar steppers (4 wires each) |
| Coil pairs (example motor) | Yellow–Green ~13.5 Ω, Blue–Purple ~13.3 Ω |
| Axes | X = shield M1+M2, Y = shield M3+M4 |
| Speed | Proven through **150 rpm** (AFMotor SINGLE) in square loops |
| Pen | Optional SG90 on shield **SERVO_1** (Arduino pin 10) — not required for dry-runs |
| Power for early tests | USB + yellow **PWR** jumper on (weak but OK unloaded) |

## Geometry

| Axis | Usable travel |
| --- | --- |
| X | **55 mm** (5.5 cm) |
| Y | **50 mm** (5.0 cm) |

Software origin is a **corner**, not the middle of the rails. Park both sleds
at the bottom-left of the paper, then `G92 X0 Y0` (or power-cycle with them
already there). G-code then lives in `0…55 × 0…50` mm.

## Calibration (steps/mm)

Default guess `6.667` was wrong for this pitch. Iterative `$CALX=10` / `$CALY=10`
with a ruler:

| Commanded | Measured | New steps/mm |
| --- | --- | --- |
| 10 mm | 18 mm | 3.704 |
| 10 mm | 15 mm | 2.469 |
| 10 mm | 12 mm | 2.058 |
| 10 mm | **10 mm** | **2.058** (kept) |

Firmware defaults in `src/uno_plotter` are therefore:

```text
$STEPSX=2.058
$STEPSY=2.058
bed 55 x 50 mm
```

Resolution is about **0.49 mm per full step**. Fine handwriting will look
blocky; prefer larger characters or accept coarse strokes.

Formula if you recalibrate:  
`new = current × (commanded_mm / measured_mm)`.

## Firmware / tools

| Piece | Role |
| --- | --- |
| `src/uno_motor_test` | Manual `x`/`y` jog for wiring bring-up |
| `src/uno_plotter` | G-code plotter @ **115200** baud (M300, G0/G1, `$…`) |
| `tools/uno_console.py` | Multi-command jog helper for the motor-test sketch |
| `tools/send_gcode.py` | Stream jobs: `-p /dev/ttyACM0 -b 115200` |
| `tools/text2gcode.py` | Hershey single-stroke text → G-code |
| `tools/handwriting2gcode.py` | Neural strokes → G-code (`setup_handwriting.sh` first) |
| `tools/image2gcode.py` | Bitmap → outlines → G-code |
| `sim/simulate.py` | Offline path preview (use before paper) |

## Simulation (no hardware)

Until pen and paper exist, treat `sim/simulate.py --paper` as the stand-in for a finished page. Defaults are already the measured 55×50 mm bed and 2.058 steps/mm.

## Simulation commands

Always pass the calibrated bed and steps:

```bash
python3 sim/simulate.py test-square-uno.gcode \
  --envelope 55 --steps-x 2.058 --steps-y 2.058 \
  --out sim/out/preview.png
```

OpenSCAD (`cad/plotter.scad`) and Blender are for **mechanical design**, not
for checking whether a plot looks right. Use `sim/simulate.py` for that.

## ESP32 (later)

Do not solder the `D7`→`5V` 74HC595 disable while finishing Uno plots — that
disables the stock AFMotor path. When ready: `hardware/WIRING.md` and
`src/esp32_l293d_plotter.ino`.
