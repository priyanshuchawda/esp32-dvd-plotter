// Bring-up test for the DVD sleds on an Arduino Uno + HW-130 shield.
//
// The Uno drives this shield natively at 5 V, so no rewiring is needed to run
// it. Prove the mechanics here first; move to the ESP32 afterwards, when the
// only new variable is the ESP32 itself.
//
// Nothing moves at power-on, and both motors are released after every command,
// because a stationary energised coil is what cooks these little motors.
//
//   arduino-cli compile -b arduino:avr:uno src/uno_motor_test
//   arduino-cli upload  -b arduino:avr:uno -p /dev/ttyACM0 src/uno_motor_test
//
// Then open a serial monitor at 9600 and type '?' for the command list.

#include <AFMotor.h>

// The step count only scales the rpm figure; it does not affect correctness.
// DVD sled motors are typically 20 full steps per revolution.
const int STEPS_PER_REV = 20;

AF_Stepper motorX(STEPS_PER_REV, 1);  // screw terminals M1 + M2
AF_Stepper motorY(STEPS_PER_REV, 2);  // screw terminals M3 + M4

// SINGLE energises one coil at a time and draws approximately half the current
// of DOUBLE. Start here; only move to DOUBLE if the sled lacks torque.
uint8_t stepStyle = SINGLE;
int speedRpm = 10;

void help() {
  Serial.println(F("commands:"));
  Serial.println(F("  x <n>   step X by n (negative reverses)"));
  Serial.println(F("  y <n>   step Y by n"));
  Serial.println(F("  s <rpm> set speed, default 10"));
  Serial.println(F("  1       single-coil drive (low current, default)"));
  Serial.println(F("  2       double-coil drive (more torque, ~2x current)"));
  Serial.println(F("  r       release both motors"));
  Serial.println(F("  ?       this list"));
  Serial.println(F("Motors release automatically after each move."));
  Serial.println(F("Stop immediately if anything gets hot."));
}

void setup() {
  Serial.begin(9600);
  motorX.release();
  motorY.release();
  Serial.println(F("DVD sled test ready. Motors released."));
  help();
}

void runAxis(AF_Stepper &motor, const char *name, long count) {
  if (count == 0) {
    Serial.println(F("zero steps, nothing to do"));
    return;
  }
  uint8_t direction = (count > 0) ? FORWARD : BACKWARD;
  long magnitude = (count > 0) ? count : -count;

  Serial.print(F("stepping "));
  Serial.print(name);
  Serial.print(' ');
  Serial.print(count);
  Serial.println(F("..."));

  motor.setSpeed(speedRpm);
  // Stepped one at a time so a jam is interruptible by cutting power rather
  // than having to wait out a long blocking call.
  for (long i = 0; i < magnitude; i++) {
    motor.step(1, direction, stepStyle);
  }
  motor.release();
  Serial.println(F("done, released"));
}

void loop() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  char command = line.charAt(0);
  long value = line.substring(1).toInt();

  switch (command) {
    case 'x': case 'X': runAxis(motorX, "X", value); break;
    case 'y': case 'Y': runAxis(motorY, "Y", value); break;
    case 's': case 'S':
      if (value > 0) speedRpm = value;
      Serial.print(F("speed "));
      Serial.println(speedRpm);
      break;
    case '1':
      stepStyle = SINGLE;
      Serial.println(F("single-coil drive"));
      break;
    case '2':
      stepStyle = DOUBLE;
      Serial.println(F("double-coil drive, watch the temperature"));
      break;
    case 'r': case 'R':
      motorX.release();
      motorY.release();
      Serial.println(F("both released"));
      break;
    default:
      help();
      break;
  }
}
