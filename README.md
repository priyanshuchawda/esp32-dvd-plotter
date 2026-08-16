# ESP32 / Uno DVD Pen Plotter

DVD-drive sleds on an **HW-130 L293D** shield. The active path is **Arduino Uno
+ AFMotor**. ESP32 custom firmware is in the tree for later (the shield’s
74HC595 is 5 V and needs a bypass for 3.3 V logic).

## Current state

See [`FINDINGS.md`](FINDINGS.md) for measured bed size, coil ohms, speed tests,
and the steps/mm calibration trail.

- **Firmware (use this):** [`src/uno_plotter`](src/uno_plotter) @ 115200 baud  
- **Bring-up jog:** [`src/uno_motor_test`](src/uno_motor_test) @ 9600 baud  
- **Bed:** 55 × 50 mm · **steps/mm:** 2.058 on both axes (ruler-verified)  
- **ESP32 sketch:** [`src/esp32_l293d_plotter.ino`](src/esp32_l293d_plotter.ino) (deferred)

## Uno quick start

1. Shield on Uno, motors on M1/M2 (X) and M3/M4 (Y), yellow `PWR` on for USB tests.
2. Park sleds at the **paper corner** (software origin), then:

```bash
arduino-cli compile -b arduino:avr:uno src/uno_plotter
arduino-cli upload  -b arduino:avr:uno -p /dev/ttyACM0 src/uno_plotter
```

3. Preview, then plot:

```bash
python3 sim/simulate.py test-square-uno.gcode \
  --envelope 55 --steps-x 2.058 --steps-y 2.058 -o sim/out/square.png

tools/send_gcode.py -p /dev/ttyACM0 -b 115200 test-square-uno.gcode
```

4. Optional SG90 on shield **SERVO_1** (pin 10): tune `$PENUP=` / `$PENDOWN=`.

## Making G-code

| Tool | Use |
| --- | --- |
| [`tools/text2gcode.py`](tools/text2gcode.py) | Single-stroke Hershey text |
| [`tools/handwriting2gcode.py`](tools/handwriting2gcode.py) | Neural handwriting (CPU) |
| [`tools/image2gcode.py`](tools/image2gcode.py) | Bitmap → outlines |
| [`tools/send_gcode.py`](tools/send_gcode.py) | USB stream to plotter |

```bash
tools/text2gcode.py --width 55 --height 50 --char-height 8 "hi" -o hi.gcode
python3 sim/simulate.py hi.gcode --envelope 55 --steps-x 2.058 --steps-y 2.058 -o sim/out/hi.png
```

Prefer Hershey / online strokes over tracing a normal TTF (outlines look hollow
at this scale). Step size is ~0.5 mm, so keep letters large.

## Simulation vs CAD

| Tool | What it’s for |
| --- | --- |
| `sim/simulate.py` | Toolpath / pen / envelope check before paper |
| `sim/spice/` | Coil current vs step rate (ngspice) |
| `cad/plotter.scad` | Frame / bracket geometry (OpenSCAD CLI) |
| Blender | Mesh / visuals if needed — not for G-code |

## ESP32 (later)

When leaving the Uno path: remove the yellow `PWR` jumper, tie shield `D7` to
`5V` to tri-state the 74HC595, and follow [`hardware/WIRING.md`](hardware/WIRING.md).
That change breaks AFMotor until the wire is removed again.

`config.yaml` / FluidNC files are historical only — do not use them with this
L293D shield.
