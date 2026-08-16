# BOM — ESP32 ↔ HW-130 adapter

| Ref | Qty | Part |
| --- | --- | --- |
| J_SHIELD | 1 | Arduino R3 male header set (1×8 + 1×10 + 1×8 + 1×6) soldered into Uno footprint |
| J_ESP_L / J_ESP_R | 2 | 1×15 female pin socket 2.54 mm (ESP32-DevKit V1) |
| J_5V | 1 | 2-pin screw terminal 5.08 mm |
| H1–H4 | 0 | Optional M3 holes (add in pcbnew if you want standoffs) |
| — | 1 | PCB (this design) |
| — | 1 | ESP32-DevKit V1 / DOIT 30-pin |
| — | 1 | HW-130 L293D shield |
| — | 1 | Regulated 5 V supply (≥2 A recommended) |

## Assembly

1. Solder female sockets for ESP32 on the **right wing** (USB toward silk arrow).
2. Solder **male** Arduino headers pointing **up** on the left footprint.
3. Solder J_5V.
4. Plug ESP32 into wing sockets; stack HW-130 on male headers.
5. Wire motors as on Uno (X=M1+M2, Y=M3+M4). Remove yellow PWR jumper.
6. Feed J_5V from external 5 V; common GND with ESP32 USB GND / supply −.
