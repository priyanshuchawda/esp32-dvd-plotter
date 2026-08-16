# Custom ESP32 firmware

> **Deferred.** The machine is running on [`src/uno_plotter`](src/uno_plotter)
> today. This document describes the ESP32 sketch for later use after the
> [`hardware/WIRING.md`](hardware/WIRING.md) bypass is built.

`esp32-dvd-plotter.ino` / `src/esp32_l293d_plotter.ino` replaces FluidNC for
this HW-130 shield; do not upload the old `config.yaml` to this firmware.

The plotter announces itself over:

- USB serial at `115200` baud;
- Bluetooth Classic Serial as `DVD_Plotter`.

It begins with motor outputs disabled. Connect via USB first and send:

```text
$HELP
$STATUS
```

The expected reply includes:

```text
<Idle|MPos:0.000,0.000|Pen:Up|Motors:Off>
```

## Supported commands

| Command | Effect |
| --- | --- |
| `G21`, `G20` | use millimetres or inches |
| `G90`, `G91` | absolute or relative coordinates |
| `G92 X0 Y0` | declare the current carriage location as a coordinate |
| `G0 X... Y...` | rapid move |
| `G1 X... Y... F...` | linear drawing move |
| `G0 Z5` | pen up |
| `G1 Z0` | pen down |
| `M3` / `M4` | pen down |
| `M5` | pen up |
| `M2` / `M30` | pen up and disable motors |
| `$STEPSX=value` | set X full-steps per millimetre |
| `$STEPSY=value` | set Y full-steps per millimetre |
| `$PENUP=value` | set pen-up pulse, 500–2500 microseconds |
| `$PENDOWN=value` | set pen-down pulse, 500–2500 microseconds |
| `$MOTORS=ON` / `$MOTORS=OFF` | explicitly energize/release coils |
| `$STATUS` | show current position and state |

Only `G0` and `G1` motion is currently implemented. Convert vector artwork
to line segments; do not send arc commands (`G2`/`G3`), homing commands, or
FluidNC/GRBL `$` settings.

## Commissioning commands

After the hardware continuity checks in
[`hardware/WIRING.md`](hardware/WIRING.md) pass, run these one line at a time:

```text
$MOTORS=ON
G92 X0 Y0
G91
G1 X1 F60
G1 Y1 F60
G90
$MOTORS=OFF
```

With the pen removed, measure a 20 mm move on each axis. Calculate and set:

```text
new_steps_per_mm = old_steps_per_mm × commanded_mm / measured_mm
```

The initial `6.667` value is only a typical DVD-drive estimate. For example,
if a commanded 20 mm X move measures 18.5 mm:

```text
$STEPSX=7.207
```

The settings are not yet persistent across an ESP32 reset. After final
calibration, update the four defaults near the top of
`src/esp32_l293d_plotter.ino`, compile, and flash again.

## Draw test

Run `test-square.gcode` with the pen lifted first. It includes only supported
linear moves and ends with `M2`, which releases the L293D outputs.
