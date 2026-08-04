# HW-130 socket-plug PCB and wiring

This wiring bypasses the shield's 74HC595 direction shift register. It is for
the photographed HW-130 shield with two L293D chips and one socketed 74HC595.
It must not be used with an A4988 driver board.

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

## 2. 74HC595 socket plug

Remove the upper 74HC595 with all power disconnected. Its small semicircular
notch points toward the top motor terminals. Put the custom PCB's male
16-pin plug into that empty socket with the same notch orientation.

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

The custom board connects only these socket contacts:

| Socket contact | Shield direction line | ESP32 pin | Silkscreen on a 30-pin DevKit |
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
