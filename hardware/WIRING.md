# HW-130 socket-plug PCB and wiring

This wiring bypasses the shield's 74HC595 direction shift register. It is for
the photographed HW-130 shield carrying two L293D drivers and one 74HC595,
whether that chip is socketed or soldered down. It must not be used with an
A4988 driver board.

Identify the 74HC595 by reading the markings: the two chips marked `L293D` are
the motor drivers, and the remaining one is the shift register. Do not go by
position, since board revisions differ.

## 1. Safe power arrangement

Use one regulated 5 V, 3 A supply as three separate branches:

| Supply branch | Connect to | Do not connect to |
| --- | --- | --- |
| motor power + / - | shield `EXT_PWR` + / GND | ESP32 5 V pin |
| shield logic + / - | shield `5V` / `GND` header | ESP32 5 V pin |
| servo + / - | SG90 red / brown-black | ESP32 5 V pin |

Keep the shield's yellow `PWR` jumper **removed**. Power the ESP32 from USB
while commissioning. Connect the ESP32 GND, shield GND, supply negative, and
servo ground together.

The shield needs its separate `5V` logic connection because it is no longer
mounted on an Arduino. `EXT_PWR` alone powers the motor side; it does not
reliably provide the logic supply in this standalone setup.

## 2. Getting the 74HC595 out of the signal path

The eight direction lines reach the L293D inputs through the 74HC595. That
chip is powered at 5 V and needs about 3.5 V to register a HIGH, which the
ESP32's 3.3 V does not reliably reach. So we take it out of the path.

The pin mapping below is confirmed against Adafruit's own AFMotor library,
which this shield clones: shift-register bits 2, 3, 1, 4, 5, 7, 0, 6 drive
M1A, M1B, M2A, M2B, M3A, M3B, M4A, M4B respectively, and those bits appear on
QA..QH, which are chip pins 15, 1, 2, 3, 4, 5, 6, 7.

### If the chip is soldered down (most clones, including the photographed one)

Do not try to desolder it. Disable it instead.

**Wire the `D7` pad to the shield's `5V` pad before anything else.** `D7` is
the shift register's output-enable, which is active-low, so holding it high
forces all eight outputs to high-impedance. The chip stays physically in place
but electrically lets go of those lines, leaving them free for the ESP32.

This wire is mandatory, not a precaution. Sources disagree on which way the
pin idles: Adafruit's own documentation describes a pull-up that disables the
outputs, while at least one clone's parts list has a 10K pulldown that would
*enable* them. Tying the pad to 5 V overrides either, since a hard connection
beats a 10K resistor. Skip it and you risk the 74HC595 driving the same wires
as your ESP32 GPIOs, two push-pull outputs fighting, which can damage both.

Verify before going further: with logic power applied and nothing else
connected, measure 74HC595 pin 13 against ground. It must read close to 5 V.
If it reads near 0 V the outputs are still live; find and fix that first.

Then solder your ESP32 wires **onto the 74HC595's own output legs**. Those legs
are the same electrical nodes as the L293D inputs, so the pin numbers in the
table below apply unchanged. Use thin stranded wire and keep the iron brief.

> Check with a meter for solder bridges between adjacent legs before powering
> up. Two shorted direction lines will make a motor buzz and never turn.

### If the chip sits in a socket

Remove it with all power disconnected and store it. Its semicircular notch
points toward the top motor terminals. Wire into the empty socket contacts,
or fit a custom plug with the same notch orientation.

Viewed from above with the notch at the top:

```text
                 shield top / notch
     M2_A   GPIO18  1 o     o 16  +5V SHIELD RAIL — LEAVE OPEN
     M1_A   GPIO16  2 o     o 15  GPIO23  M4_A
     M1_B   GPIO17  3 o     o 14  unused
     M2_B   GPIO19  4 o     o 13  unused
     M3_A   GPIO21  5 o     o 12  unused
     M4_B   GPIO13  6 o     o 11  unused
     M3_B   GPIO22  7 o     o 10  unused
     GND             8 o     o  9  unused
```

Connect only these contacts, counting pins on the 74HC595 itself:

| 74HC595 pin | Shield direction line | ESP32 pin | Silkscreen on a 30-pin DevKit |
| --- | --- | --- | --- |
| 1 | M2 coil A | GPIO18 | `D18` |
| 2 | M1 coil A | GPIO16 | `RX2` |
| 3 | M1 coil B | GPIO17 | `TX2` |
| 4 | M2 coil B | GPIO19 | `D19` |
| 5 | M3 coil A | GPIO21 | `D21` |
| 6 | M4 coil B | GPIO13 | `D13` |
| 7 | M3 coil B | GPIO22 | `D22` |
| 8 | common ground | ESP32 GND | `GND` |
| 15 | M4 coil A | GPIO23 | `D23` |

Most 30-pin DevKit boards do not print "16" or "17" anywhere. Those two GPIOs
are the pins labelled `RX2` and `TX2`. They are ordinary GPIOs here and are not
used for serial, so using them is safe.

All other socket contacts, especially **pin 16**, remain electrically open on
the custom PCB. Pin 16 is the shield's 5 V rail; connecting it to an ESP32
GPIO or `3V3` will damage the ESP32.

## 3. Motor-enable and servo wiring

Run these five wires from ESP32 pins to the labelled Arduino-header pads on
the HW-130:

| ESP32 | HW-130 Arduino-header label | Function |
| --- | --- | --- |
| GPIO25 | D11 | M1 enable / PWM |
| GPIO26 | D3 | M2 enable / PWM |
| GPIO27 | D6 | M3 enable / PWM |
| GPIO32 | D5 | M4 enable / PWM |
| GPIO33 | SG90 signal wire | pen lift servo |

Use the shield terminals as complete H-bridges:

| Plotter axis | Shield terminals | DVD motor connection |
| --- | --- | --- |
| X | M1 + M2 | one verified coil pair in M1; the other pair in M2 |
| Y | M3 + M4 | one verified coil pair in M3; the other pair in M4 |

Identify each pair with a multimeter first. A coil pair has measurable
continuity/resistance. Do not attach a motor until its two pairs are known.

## 4. Mandatory continuity checks

With USB and 5 V power disconnected:

1. Check every GPIO-to-socket mapping in the table above.
2. Check `GPIO16`, `17`, `18`, `19`, `21`, `22`, `23`, and `13` have no
   continuity to socket pin 16 or the shield `5V` header.
3. Check socket pin 8, ESP32 GND, shield GND, supply negative, and servo
   ground are all continuous.
4. Check shield `5V` and GND are not shorted.
5. Verify no supply branch connects to the ESP32 `5V`/`VIN` pin.

Only after all five checks pass may the firmware be flashed and the motors
tested one at a time.
