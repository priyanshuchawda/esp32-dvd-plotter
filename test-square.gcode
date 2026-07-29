; Initial 10 mm square test for the ESP32 DVD pen plotter.
; Run once with the pen lifted/removed, then with paper installed.
G21
G90
G0 Z5
G0 X5 Y5
G1 Z0 F150
G1 X15 Y5 F300
G1 X15 Y15 F300
G1 X5 Y15 F300
G1 X5 Y5 F300
G0 Z5
M2
