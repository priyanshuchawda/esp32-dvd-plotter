# Building the ESP32 DVD pen plotter

This follows the same idea as the popular CD-ROM plotter tutorials, but three
of their five phases do not work on an ESP32 and are replaced here.

| Tutorial step | Why it does not apply | What we do instead |
| --- | --- | --- |
| Adafruit Motor Shield library | AVR-only: direct port and timer register access, will not compile for ESP32 | Custom firmware in `src/` |
| Inkscape 0.48 + Unicorn plugin | From 2011, 32-bit Windows only, uninstallable today | `tools/image2gcode.py`, calling potrace |
| Pronterface | GUI, not installed, no safe-abort | `tools/send_gcode.py` |
| Wiring through the shield headers | Signals pass through a 5 V 74HC595 the 3.3 V ESP32 cannot drive reliably | Bypass the '595, wire straight to the L293D |
| 7.5–9 V supply | Correct in principle, but the right voltage depends on your coil resistance | Measure, then compute (Phase 1) |

---

## Phase 0 — Confirm your motors are steppers

**Do not skip this. Everything else depends on it.**

Many DVD drives move the laser sled with a *brushed DC motor*, not a stepper.
They get away with it because the drive reads its position off the disc in a
closed loop. A brushed motor cannot be positioned open-loop, so if that is what
you have, no firmware or wiring will make this work.

Two tests:

1. **Turn the lead screw slowly by hand.** A stepper resists in distinct
   clicks, one detent at a time. A brushed motor turns smoothly with none.
   This is the more reliable test.
2. **Count the motor's wires.** Four means bipolar stepper. Two means brushed
   DC. Ignore the wide ribbon going to the laser pickup.

Then identify the coil pairs. Set your meter to resistance and measure all six
combinations of the four wires:

| Pair | Reading | Meaning |
| --- | --- | --- |
| 1-2, 1-3, 1-4, 2-3, 2-4, 3-4 | two pairs read 10–30 Ω | those two pairs are your coils |
| | the other four read `OL` | no connection, as expected |

Write down the resistance. Phase 1 needs it.

---

## Phase 1 — Power

Motors cannot run from the ESP32's USB. Two steppers plus a servo draw well
over an amp; USB gives you half that. The rail sags, the ESP32 brownout-resets
mid-plot, and you spend days chasing a firmware bug that is not there.

The L293D drops about 1.8 V internally, so the coil only sees
`V_supply − 1.8`. Coil current is therefore:

```
I = (V_supply − 1.8) / R_coil
```

Aim for **250–450 mA**. Above 600 mA the L293D exceeds its rating and
overheats; below about 200 mA there is not enough torque and the motor skips.

| Coil resistance | 5 V | 6 V | 7.5 V | 9 V | 12 V |
| --- | --- | --- | --- | --- | --- |
| 10 Ω | 320 mA | 420 mA | 570 mA | **720 mA** | **1020 mA** |
| 15 Ω | 213 mA | 280 mA | 380 mA | 480 mA | **680 mA** |
| 20 Ω | 160 mA | 210 mA | 285 mA | 360 mA | 510 mA |
| 30 Ω | 107 mA | 140 mA | 190 mA | 240 mA | 340 mA |

Bold values exceed the L293D's 600 mA limit. Pick the lowest voltage that
lands you in the 250–450 mA band. This is why a blanket "use 9 V" is wrong: at
10 Ω it destroys the chip, at 30 Ω it is barely adequate.

After a few minutes of running, touch the motors. If they are too hot to hold
comfortably, drop a volt. The coils stay energised during a plot.

### If you have not measured the coils

You do not have to. The firmware chops the L293D enable pins at 20 kHz, so the
average coil current is set in software rather than purely by Ohm's law. That
turns an irreversible hardware guess into an adjustable dial.

`$POWER=` takes 5 to 100 percent and defaults to a deliberately timid 45,
which is safe at any coil resistance you are realistically going to find.

Wire up a 6 V or 7.5 V supply, then walk it up:

```
> $POWER=45
> G1 X10 F200      # does it move cleanly?
> $POWER=55        # if it stalls or skips, raise and retry
```

Stop as soon as movement is reliable. Every extra percent is heat you do not
need. Give it a few minutes and feel the motors and the L293D chips; if either
is too hot to keep a finger on, come back down.

Measuring still gives a better result, because it lets you pick the right
supply voltage instead of throwing away the excess as heat, and it makes the
step-rate figures below real rather than estimated. But it is no longer a
prerequisite for switching on.

> **Remove the power jumper on the shield.** The HW-130 has a jumper tying the
> motor supply to the logic 5 V rail. Leave it in with an external supply and
> you push 9 V into the ESP32's 5 V pin and destroy the board. Take it off
> before connecting anything.

Supply and ESP32 must share a common ground.

---

## Phase 2 — Wiring

The shield's Arduino headers route the four direction signals through an
onboard 74HC595 shift register running at 5 V. Its guaranteed HIGH threshold
is about 3.5 V and the ESP32 outputs 3.3 V. That is below spec: it often works
on the bench and then randomly drops steps or reverses a motor.

Bypassing it costs nothing, because the L293D itself only needs 2.3 V for a
HIGH. Pull the 74HC595 out of its socket and drive the socket contacts, which
connect straight to the L293D inputs.

| Signal | Socket pin | ESP32 GPIO | DevKit silkscreen |
| --- | --- | --- | --- |
| X coil 1 A | 2 | GPIO16 | `RX2` |
| X coil 1 B | 3 | GPIO17 | `TX2` |
| X coil 2 A | 1 | GPIO18 | `D18` |
| X coil 2 B | 4 | GPIO19 | `D19` |
| Y coil 1 A | 5 | GPIO21 | `D21` |
| Y coil 1 B | 7 | GPIO22 | `D22` |
| Y coil 2 A | 15 | GPIO23 | `D23` |
| Y coil 2 B | 6 | GPIO13 | `D13` |
| Ground | 8 | `GND` | |

**Never connect anything to socket pin 16** — that is the '595's Vcc.

Enable lines go to the shield's PWM pads, and the servo to any free pin:

| Function | Shield pad | ESP32 GPIO |
| --- | --- | --- |
| Enable M1 | D11 | GPIO25 |
| Enable M2 | D3 | GPIO26 |
| Enable M3 | D6 | GPIO27 |
| Enable M4 | D5 | GPIO32 |
| Servo signal | — | GPIO33 |

Motors go to the screw terminals: **X axis to M1 and M2, Y axis to M3 and M4**,
one coil pair per terminal block, centre pin unused. Servo brown to ground, red
to 5 V, orange to GPIO33. Reversing the servo's red and brown will destroy it.

Full detail is in [`hardware/WIRING.md`](hardware/WIRING.md).

---

## Phase 3 — Flash the firmware

WiFi and the web UI need the larger partition, so the `PartitionScheme`
argument is not optional.

```bash
arduino-cli core install esp32:esp32          # once
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=huge_app .
arduino-cli upload  --fqbn esp32:esp32:esp32:PartitionScheme=huge_app \
    -p /dev/ttyUSB0 .
```

If `/dev/ttyUSB0` is missing, check `lsusb` for a CP210x or CH340, and confirm
you are in the `dialout` group with `id -nG`.

Then open a console:

```bash
tools/send_gcode.py --console
> $HELP
> $STATUS
```

Motors start disabled deliberately, so nothing moves until you ask.

---

## Phase 4 — Calibrate

Do this with the pen removed or lifted.

**Check the wiring first.** Before commanding any movement:

```
> $COILTEST
```

This drives each of the eight H-bridge outputs alone for 600 ms. You should
feel exactly eight distinct twitches, four per motor. A missing twitch means
that half-bridge or its wire is dead. Two outputs moving the same coil means a
pair is split across the two terminal blocks, which is the usual reason a
motor buzzes without turning.

**Check direction.** Centre both carriages by hand, then:

```
> $MOTORS=ON
> G92 X0 Y0
> G1 X10 F200
```

X should move 10 mm in the direction you want to call positive. If it moves
backward, swap either coil pair of that motor at the screw terminal. If it
buzzes without moving, you have the pairs wrong: the two wires of one coil are
split across both terminals.

**Set steps per mm.** Command a known move and measure what you actually got
with a ruler:

```
> G92 X0 Y0
> G1 X20 F200
```

If 20 mm was commanded but you measured 18 mm, correct the current value:

```
new = old × (commanded ÷ measured) = 6.667 × (20 ÷ 18) = 7.41
> $STEPSX=7.41
```

Repeat until they agree, then do Y. These settings live in RAM, so note them
down and edit the defaults in `src/esp32_l293d_plotter.ino`.

**Set the pen servo.** `$PENUP=` and `$PENDOWN=` take microseconds, 500–2500:

```
> $PENDOWN=1600
> M300 S30
> $PENUP=1000
> M300 S50
```

The pen should just kiss the paper when down, not press. `$PENSETTLE=250` is
how long movement pauses for the servo to travel; raise it if the pen drags a
line as it lifts.

---

## Phase 5 — Turn an image into G-code

```bash
tools/image2gcode.py drawing.png -o drawing.gcode
```

It thresholds the image, traces it with potrace (the same engine behind
Inkscape's Trace Bitmap), reduces the points, orders the paths to cut pen-up
travel, and fits everything to the bed.

Useful options:

| Option | Purpose |
| --- | --- |
| `--width`, `--height` | bed size in mm, default 35 |
| `--threshold` | 0–255; raise it to capture more of the image as ink |
| `--invert` | for light drawings on dark backgrounds |
| `--simplify` | higher means fewer points and faster plots |
| `--feed` | drawing speed, mm/min |

Line art and high-contrast logos work well. Photographs do not: tracing gives
thousands of nested outlines.

**Always simulate before plotting.** It costs a second and catches mistakes
while they are still free:

```bash
python3 sim/simulate.py drawing.gcode --out preview.png
```

Check the drawing fits the envelope and that the reported runtime is sane.

---

## Drawing from your phone

The firmware serves its own web page, so there is no app to install and it
works on Android, iOS, or a laptop equally.

By default the ESP32 hosts a hotspot. Connect your phone to **DVD-Plotter**
with password `plotter123`, then open **http://192.168.4.1**. Draw with your
finger and press Plot.

The drawback is that your phone loses its internet connection while joined to
the plotter. To avoid that, have the ESP32 join your own network instead by
filling in the credentials near the top of `src/esp32_l293d_plotter.ino`:

```cpp
const char *WIFI_SSID = "your-network";
const char *WIFI_PASSWORD = "your-password";
```

It then prints its address over USB serial at boot; browse to that instead.

The page simplifies each stroke before sending, because a finger drag produces
hundreds of nearly collinear points and every one would otherwise become a
separate move for the board to chew through. Stop halts the plot, lifts the
pen, and releases the motors.

Bluetooth is compiled out by default. Both radios do fit together, but they
share one antenna and coexistence costs stability, and the drawing UI only
needs WiFi. Set `ENABLE_BLUETOOTH` to 1 in the firmware if you also want
serial-terminal control.

---

## Phase 6 — Plot

Centre both carriages by hand, because there are no endstops and the firmware
treats the power-on position as the origin.

```bash
tools/send_gcode.py drawing.gcode
```

Scribble on scrap paper first to get the ink flowing. Start with the pen lifted
for a dry run, then fit paper and run it for real.

Ctrl-C aborts safely: the pen lifts and the motors release. Never kill it any
other way, or the pen sits bleeding into the paper while the coils cook.

---

## Speed limits

The coil is an inductor, so current needs roughly three time constants to build
after the driver switches. Past that, faster stepping means less current and
less torque. From `sim/spice/`:

| Step rate | Torque available |
| --- | --- |
| 200–500 /s | 100% |
| 1000 /s | 98% |
| 2000 /s | 88% |
| 4000 /s | 73% |
| 8000 /s | 59% |

Stay near or below 1000 steps/s. Pushing past it does not draw faster, it skips
steps and shifts the drawing. Re-run `sim/spice/sweep.sh` once you know your
real coil resistance.

---

## When something goes wrong

| Symptom | Likely cause |
| --- | --- |
| Motor buzzes, does not turn | coil pairs split across terminals; re-check with the meter |
| Moves the wrong way | swap one coil pair on that motor |
| Drawing is skewed or short | steps per mm wrong, or stepping too fast for the torque |
| ESP32 resets mid-plot | motors drawing from USB, or the shield power jumper is still fitted |
| Pen drags on lift | raise `$PENSETTLE` |
| Everything freezes part-way | a line was never acknowledged; the sender prints which one |
| Motors very hot | supply voltage too high for your coil resistance, see Phase 1 |
