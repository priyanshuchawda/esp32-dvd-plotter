# ESP32 DVD Pen Plotter

This project controls two DVD-drive bipolar steppers through the existing
HW-130 L293D motor shield and an ESP32. The shield is not an A4988 board, so
it uses custom coil-sequencing firmware instead of FluidNC.

## Current state

- Custom USB/Bluetooth firmware is compiled, flashed, and responds on
  `/dev/ttyUSB0`.
- The ESP32 reports `ESP32 L293D DVD Plotter ready`.
- Motors are disabled by default.
- The physical socket-plug PCB, power wiring, motor-coil identification, and
  calibration remain to be performed with the hardware.

## Build order

1. Build and continuity-check the custom socket plug using
   [`hardware/WIRING.md`](hardware/WIRING.md).
2. Connect the 5 V, 3 A supply and identify the two coil pairs on each DVD
   motor. Do not apply motor power until the continuity checks pass.
3. Follow [`CUSTOM_FIRMWARE.md`](CUSTOM_FIRMWARE.md) to test one axis at a
   time, set safe servo endpoints, and calibrate steps/mm.
4. Run [`test-square.gcode`](test-square.gcode) with the pen lifted, then on
   paper.

## Making G-code

| Tool | Use it for |
| --- | --- |
| [`tools/text2gcode.py`](tools/text2gcode.py) | Writing text with single-stroke Hershey fonts |
| [`tools/image2gcode.py`](tools/image2gcode.py) | Tracing a bitmap into outlines |
| [`tools/handwriting2gcode.py`](tools/handwriting2gcode.py) | Generating handwriting with a neural model |
| [`tools/send_gcode.py`](tools/send_gcode.py) | Streaming a job over USB serial |

Use `text2gcode.py` for text rather than tracing a rendered font. Tracing
follows the *outline* of each letter, so the pen draws each stroke as a hollow
loop, which is unreadable at the size this machine works at. Hershey fonts
store stroke centrelines, so the pen follows the same path a hand would.

```bash
tools/text2gcode.py "hello world" -o hello.gcode
tools/text2gcode.py --font cursive --char-height 3 "your text" -o note.gcode
python3 sim/simulate.py note.gcode --envelope 35 --out preview.png
```

`futural` is a plain sans face and `cursive` is joined handwriting; `timesr`,
`futuram`, and `gothiceng` are also included. Default characters are 4 mm tall,
which fits roughly 7 per line. Dropping to 3 mm fits about 11 characters across
4 lines, which is close to the practical limit of a 35 mm bed.

## Neural handwriting

Hershey `cursive` is joined but mechanical — every `o` is identical. For output
with real variation, a Graves-style LSTM predicts pen trajectories directly, so
there is no image or vectorisation step between the model and the G-code.

```bash
./tools/setup_handwriting.sh          # clones the model, builds ext/venv
ext/venv/bin/python tools/handwriting2gcode.py "hello world" -o hw.gcode --seed 7
python3 sim/simulate.py hw.gcode --envelope 35 --out preview.png
```

Sampling runs on the CPU in about ten seconds a line; no GPU is needed. `--bias`
trades variation for legibility, and higher is usually right at this size.
`--seed` fixes the style so a result can be reproduced. `--wrap` sets characters
per line, which is what actually controls how large the writing ends up.

The model is not perfectly accurate — it occasionally malforms a letter, so
check the preview before plotting. Verifying output with a handwriting
recogniser would catch this automatically and is the obvious next addition.

Everything lands in `ext/`, which is gitignored; delete it to start over.

## Size limits

DVD sleds give about 35 mm of travel per axis, so the whole page is smaller
than a postage stamp — around 40 characters of 3 mm cursive. Nothing in
software changes that. Writing longer passages needs either a paper-feed axis
or a machine with longer rails.

`config.yaml` and `upload-fluidnc-file.py` are retained only as history from
the earlier A4988/FluidNC approach. They must not be used with this L293D
shield.
