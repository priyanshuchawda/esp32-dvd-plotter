# Firmware layout

| Path | Board | Notes |
| --- | --- | --- |
| [`uno/uno_plotter`](uno/uno_plotter/) | Arduino Uno | Stock AFMotor + HW-130 (stacked) |
| [`uno/uno_motor_test`](uno/uno_motor_test/) | Arduino Uno | Jog / bring-up |
| [`esp32/esp32_plotter`](esp32/esp32_plotter/) | ESP32 | 74HC595 via jumpers — **active ESP path** |
| [`esp32/legacy_bypass`](esp32/legacy_bypass/) | ESP32 | Old solder-bypass firmware (archived) |

Wiring for ESP32 jumpers: [`../hardware/WIRING.md`](../hardware/WIRING.md).
