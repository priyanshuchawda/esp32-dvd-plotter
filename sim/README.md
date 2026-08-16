# Simulation

Two independent layers. The first needs nothing but Python; the second emulates
the real ESP32 running the actual compiled binary.

## Layer 1: toolpath simulation (no hardware, no accounts)

`firmware_model.py` is a line-by-line port of the motion logic in
[`../src/esp32_l293d_plotter.ino`](../src/esp32_l293d_plotter.ino): the same
Bresenham interleave, the same `lroundf` step rounding, the same four-phase
coil table. The Uno plotter uses the same G-code dialect and Bresenham idea, so
the same preview works for Uno jobs if you pass the calibrated steps/mm.

**Uno defaults (measured):** bed 55×50 mm, **2.058** steps/mm on X and Y.

```bash
# Uno square (current hardware)
python3 sim/simulate.py test-square-uno.gcode \
  --envelope 55 --steps-x 2.058 --steps-y 2.058 \
  --out sim/out/uno_square.png

# Any job — always match firmware $STEPSX/$STEPSY and bed
python3 sim/simulate.py myart.gcode \
  --envelope 55 --steps-x 2.058 --steps-y 2.058 \
  --out sim/out/preview.png
```

It writes a PNG to `sim/out/` showing the drawn path, the pen-up travel moves,
the usable envelope, and the coil waveforms. It exits non-zero and prints
warnings when a job leaves the envelope, ends with the pen down, or uses a
command the firmware would reject.

Use it before sending any new artwork to real hardware. It costs nothing and
catches scaling and travel mistakes that would otherwise crash the carriage
into an end stop.

**Keep this file in sync with the firmware.** If the motion code changes, the
model must change too, or the simulation stops being meaningful.

## Layer 2: firmware emulation (Wokwi)

This runs the actual compiled binary on an emulated ESP32 and captures the real
GPIO transitions, so it validates the shipped firmware rather than a model of
it. Relevant once you leave the Uno path.

Install once:

```bash
curl -sSL https://wokwi.com/ci/install.sh | sh
```

It needs a free token from <https://wokwi.com/dashboard/ci>:

```bash
export WOKWI_CLI_TOKEN=your_token_here
```

Build, stage the binary, then run:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 --build-path /tmp/esp32-dvd-plotter-build .
mkdir -p build
cp /tmp/esp32-dvd-plotter-build/esp32-dvd-plotter.ino.{merged.bin,elf} build/
wokwi-cli . --timeout 10000 --serial-log-file build/serial.log
```

[`../diagram.json`](../diagram.json) wires a logic analyzer to the eight
direction GPIOs, so `--vcd-file` exports the real coil waveforms for inspection:

```bash
wokwi-cli . --timeout 20000 --vcd-file build/coils.vcd
```

`wokwi-cli lint` validates the diagram without a token. It already caught that
GPIO16 and GPIO17 are exposed as `RX2` and `TX2` on a 30-pin DevKit.
