# Project status

Last updated for the **ESP32 jumper path** (74HC595 kept; Uno folder still works).

## Done

| Area | Status |
| --- | --- |
| Motors identified as bipolar steppers | Done (~13 Ω coils) |
| Uno + HW-130 motion + calibration | Done — bed **55 × 50 mm**, steps/mm **2.058** |
| Uno G-code firmware | Done — `src/uno/uno_plotter` |
| ESP32 folder split | Done — `src/esp32/` vs `src/uno/` |
| ESP32 74HC595 jumper firmware | Done — `src/esp32/esp32_plotter` (no soldering) |
| Laptop G-code tools + simulator | Done |
| CAD / docs / diagrams | Done |

## In progress / next on hardware

| Item | What to do |
| --- | --- |
| ESP32 jumpers + 5 V logic supply | Follow [`hardware/WIRING.md`](../hardware/WIRING.md) |
| `$COILTEST` on ESP32 | Confirm each coil twitches |
| Dry-run square over USB / Wi-Fi | Same `test-square-uno.gcode` |
| Level shifter (only if flaky) | 4 channels on D12/D4/D7/D8 |

## Still waiting on parts

| Item | Why |
| --- | --- |
| SG90 pen lift | No servo yet — wire to SERVO_1 / GPIO33 |
| Real ink on paper | No pen/paper yet |

## Commands

```bash
# ESP32
arduino-cli compile -b esp32:esp32:esp32 src/esp32/esp32_plotter
arduino-cli upload  -b esp32:esp32:esp32 -p /dev/ttyUSB0 src/esp32/esp32_plotter

# Uno (anytime)
arduino-cli compile -b arduino:avr:uno src/uno/uno_plotter
arduino-cli upload  -b arduino:avr:uno -p /dev/ttyACM0 src/uno/uno_plotter
```
