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

`config.yaml` and `upload-fluidnc-file.py` are retained only as history from
the earlier A4988/FluidNC approach. They must not be used with this L293D
shield.
