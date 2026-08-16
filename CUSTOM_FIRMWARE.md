# Custom ESP32 firmware

> **Active sketch:** [`src/esp32/esp32_plotter`](src/esp32/esp32_plotter/) —
> drives the HW-130 **74HC595 with jumper wires** (no soldering).  
> Uno stays in [`src/uno/`](src/uno/). Wiring: [`hardware/WIRING.md`](hardware/WIRING.md).

The sketch announces itself over:

- USB serial at `115200` baud;
- Wi-Fi AP `DVD-Plotter` / `plotter123` (drawing UI);
- optional Bluetooth Classic as `DVD_Plotter` (`ENABLE_BLUETOOTH 1`).

Motors start disabled. First commands:

```text
$HELP
$STATUS
$COILTEST
$POWER=70
```

Then stream G-code with `tools/send_gcode.py` or the phone UI.

## Settings

| Command | Meaning |
| --- | --- |
| `$STEPSX=` / `$STEPSY=` | steps per mm (default 2.058 from Uno cal) |
| `$POWER=` | PWM duty on L293D enables (5–100) |
| `$INVERTX=` / `$INVERTY=` | flip axis direction |
| `$PENUP=` / `$PENDOWN=` | servo pulse µs |
| `$MOTORS=ON\|OFF` | enable / release |

## Flash

```bash
arduino-cli compile -b esp32:esp32:esp32 src/esp32/esp32_plotter
arduino-cli upload  -b esp32:esp32:esp32 -p /dev/ttyUSB0 src/esp32/esp32_plotter
```

Archived solder-bypass firmware: [`src/esp32/legacy_bypass/`](src/esp32/legacy_bypass/).
