# Architecture

How the pieces connect on the **current Uno path**, and what is deferred.

## System overview

```mermaid
flowchart TB
  subgraph host [Laptop]
    T[text2gcode / handwriting2gcode / image2gcode]
    S[sim/simulate.py --paper]
    U[send_gcode.py]
    T --> S
    S -->|PNG looks good| U
  end

  subgraph controller [Arduino Uno]
    F[uno_plotter firmware]
    AF[AFMotor + 74HC595]
    F --> AF
  end

  subgraph machine [DVD frame]
    X[X sled M1/M2]
    Y[Y sled M3/M4]
    P[SG90 SERVO_1 optional]
  end

  U -->|USB 115200| F
  AF --> X
  AF --> Y
  F --> P
```

## Software pipeline

```mermaid
flowchart LR
  A[Text / image / strokes] --> B[G-code]
  B --> C{simulate.py}
  C -->|warnings| A
  C -->|ok| D[send_gcode.py]
  D --> E[Uno plotter]
  E --> F[Sleds move]
```

## Coordinate system

```text
Y 50 mm
^
|
|   paper / bed 55 × 50 mm
|
+--------------> X 55 mm
(0,0) = corner where sleds are parked at power-on / G92
```

Origin is a **corner**, not the middle of the rails.

## Firmware roles

| Sketch | Baud | Use |
| --- | --- | --- |
| `src/uno_motor_test` | 9600 | Manual jog / wiring bring-up |
| `src/uno/uno_plotter` | 115200 | Uno + stacked HW-130 |
| `src/esp32/esp32_plotter` | 115200 + WiFi | ESP32 jumpers → 74HC595 (no solder) |

## Deferred ESP32 path

```mermaid
flowchart TB
  Phone[Phone browser WiFi UI] --> ESP[ESP32 firmware]
  ESP -->|GPIO to L293D| DRV[HW-130 L293D]
  ESP -.->|D7 tied to 5V| OFF[74HC595 outputs Hi-Z]
  DRV --> MOTORS[X/Y steppers]
```

Do not start this until Uno ink plots are satisfactory. Tying `D7`→`5V`
disables the stock AFMotor path.

## CAD vs simulation

| Artifact | Answers |
| --- | --- |
| `cad/plotter.scad` | Will the frame / pen bracket fit? |
| `sim/simulate.py` | Will this G-code fit the bed and look right? |
| `sim/spice/` | Is coil current safe at a given step rate? |
| Watching sleds (no pen) | Do motors move / directions correct? |

Ink appearance without paper ≈ `simulate.py --paper`.
