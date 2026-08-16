# ESP32 + HW-130 wiring (no soldering)

Two firmwares, two folders — swap by unplugging:

| Folder | Board | Shield |
| --- | --- | --- |
| [`src/uno/`](../src/uno/) | Arduino Uno | Stacked on Uno (stock AFMotor) |
| [`src/esp32/esp32_plotter/`](../src/esp32/esp32_plotter/) | ESP32 DevKit | Jumpers into shield headers |

Nothing is removed from the HW-130. The 74HC595 stays. ESP32 bit-bangs the
same four control lines the Uno uses.

> Legacy solder-bypass notes live at the bottom. Prefer this jumper path.

## 1. Power (shield off the Uno)

| Branch | Connect | Do not |
| --- | --- | --- |
| Logic 5 V | shield `5V` + `GND` | ESP32 `5V` / `VIN` |
| Motors | shield `EXT_PWR` + / − | ESP32 |
| ESP32 | USB only while testing | — |

Remove the yellow `PWR` jumper on the shield. Tie **all grounds** together
(ESP32 GND, shield GND, supply −).

## 2. Jumper map (ESP32 → shield Arduino headers)

Plug DuPont wires into the **female** Arduino pin headers on top of the shield
(the same pads labelled D3, D4, …). Leave the 74HC595 untouched.

| Shield label | Function | ESP32 GPIO |
| --- | --- | --- |
| D12 | MOTORLATCH | **18** |
| D4 | MOTORCLK | **19** |
| D7 | MOTORENABLE (OE, active low) | **23** |
| D8 | MOTORDATA | **13** |
| D11 | M1 PWM enable | **25** |
| D3 | M2 PWM enable | **26** |
| D6 | M3 PWM enable | **27** |
| D5 | M4 PWM enable | **32** |
| SERVO_1 (signal) | pen servo (optional) | **33** |
| GND | common ground | **GND** |

Motors stay on the same terminals as the Uno path:

| Axis | Terminals |
| --- | --- |
| X | M1 + M2 |
| Y | M3 + M4 |

## 3. Bring-up

```bash
arduino-cli compile -b esp32:esp32:esp32 src/esp32/esp32_plotter
arduino-cli upload  -b esp32:esp32:esp32 -p /dev/ttyUSB0 src/esp32/esp32_plotter

# Serial (USB) — motors start disabled
# $COILTEST
# $POWER=70
# then stream G-code:
tools/send_gcode.py -p /dev/ttyUSB0 -b 115200 test-square-uno.gcode
```

Wi-Fi: board hosts hotspot `DVD-Plotter` / `plotter123` → open `http://192.168.4.1`.

If 3.3 V into the 74HC595 is flaky (missed steps / no motion), add a cheap
**4-channel level shifter** on D12/D4/D7/D8 only. PWM enables are fine at 3.3 V
(L293D VIH ≈ 2.3 V). That still needs **zero** changes to the shield.

## 5. Custom PCB (Uno-style stack)

A fabricated adapter lives in [`cad/pcb/`](../cad/pcb/):

- HW-130 stacks on Arduino R3 male headers (same as Uno)
- ESP32-DevKit plugs into a **side wing** (avoids crashing into the shield)
- Same pin map as the jumper table above
- Gerbers: `cad/pcb/out/gerbers.zip`

Until that board is made, use the jumpers in §2.

## 6. Switching back to Uno

1. Power off.
2. Unplug ESP32 (or the whole adapter).
3. Stack shield on Uno.
4. Use [`src/uno/uno_plotter`](../src/uno/uno_plotter/).

---

## Appendix: legacy solder bypass (not recommended)

Older notes that disable the 74HC595 and solder onto its legs live in git
history and [`src/esp32/legacy_bypass/`](../src/esp32/legacy_bypass/). That path
breaks Uno compatibility until rewired. Use jumpers instead.
