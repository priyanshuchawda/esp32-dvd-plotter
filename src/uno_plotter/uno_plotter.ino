// Arduino Uno + HW-130 G-code pen plotter.
//
// Uses the stock Adafruit Motor Shield V1 / HW-130 path (74HC595 stays in
// place). Compatible with tools/send_gcode.py, tools/text2gcode.py, and
// tools/handwriting2gcode.py (M300 pen commands).
//
//   arduino-cli compile -b arduino:avr:uno src/uno_plotter
//   arduino-cli upload  -b arduino:avr:uno -p /dev/ttyACM0 src/uno_plotter
//   tools/send_gcode.py -p /dev/ttyACM0 -b 115200 test-square-uno.gcode
//
// Centre both sleds by hand before power-on (no endstops).
// Motors release after M18 / end of job so coils do not cook.

#include <AFMotor.h>
#include <Servo.h>
#include <math.h>

const int STEPS_PER_REV = 20;  // only used by AFMotor's rpm helper
AF_Stepper motorX(STEPS_PER_REV, 1);  // M1 + M2
AF_Stepper motorY(STEPS_PER_REV, 2);  // M3 + M4

Servo penServo;
const uint8_t SERVO_PIN = 10;  // shield SERVO_1 header

// Physical bed from your frame: ~55 mm X, ~70 mm Y. Tune steps/mm with
// $STEPSX= / $STEPSY= after a measured move.
float stepsPerMmX = 2.469f;
float stepsPerMmY = 2.469f;
float bedMaxX = 55.0f;
float bedMaxY = 50.0f;

float xMm = 0.0f;
float yMm = 0.0f;
int32_t xSteps = 0;
int32_t ySteps = 0;

bool absoluteMode = true;
float unitScaleMm = 1.0f;
float feedMmMin = 180.0f;
const float RAPID_MM_MIN = 300.0f;
const uint32_t MIN_STEP_US = 2000;  // ~500 step/s ceiling

int8_t dirX = 1;  // set to -1 with $INVERTX=1 if travel is mirrored
int8_t dirY = 1;

uint8_t stepStyle = SINGLE;
bool motorsOn = false;
bool penIsDown = false;
uint8_t penUpDeg = 60;
uint8_t penDownDeg = 20;
float penDownThresholdS = 40.0f;
uint16_t penSettleMs = 160;
bool servoAttached = false;

String lineBuf;

void reply(const String &s) {
  Serial.println(s);
}

void releaseMotors() {
  motorX.release();
  motorY.release();
  motorsOn = false;
}

void enableMotors() {
  motorsOn = true;
}

void setPen(bool down) {
  if (penIsDown == down) return;
  penIsDown = down;
  if (servoAttached) {
    penServo.write(down ? penDownDeg : penUpDeg);
    delay(penSettleMs);
  }
}

bool extractValue(const String &line, char key, float &out) {
  const int i = line.indexOf(key);
  if (i < 0) return false;
  out = line.substring(i + 1).toFloat();
  return true;
}

int extractCode(const String &line, char key) {
  const int i = line.indexOf(key);
  if (i < 0) return -1;
  return line.substring(i + 1).toInt();
}

void stepAxis(bool isX, int8_t signedStep) {
  if (signedStep == 0) return;
  enableMotors();
  if (isX) {
    const uint8_t d = (signedStep * dirX > 0) ? FORWARD : BACKWARD;
    motorX.step(1, d, stepStyle);
    xSteps += signedStep;
  } else {
    const uint8_t d = (signedStep * dirY > 0) ? FORWARD : BACKWARD;
    motorY.step(1, d, stepStyle);
    ySteps += signedStep;
  }
}

void moveLinear(float targetX, float targetY, float feed) {
  if (targetX < 0) targetX = 0;
  if (targetY < 0) targetY = 0;
  if (targetX > bedMaxX) targetX = bedMaxX;
  if (targetY > bedMaxY) targetY = bedMaxY;

  const int32_t tx = lround(targetX * stepsPerMmX);
  const int32_t ty = lround(targetY * stepsPerMmY);
  int32_t dx = tx - xSteps;
  int32_t dy = ty - ySteps;
  const int32_t adx = abs(dx);
  const int32_t ady = abs(dy);
  const int32_t sx = dx >= 0 ? 1 : -1;
  const int32_t sy = dy >= 0 ? 1 : -1;

  const float distMm = sqrtf((targetX - xMm) * (targetX - xMm) +
                             (targetY - yMm) * (targetY - yMm));
  const int32_t steps = adx > ady ? adx : ady;
  if (steps == 0) {
    xMm = targetX;
    yMm = targetY;
    return;
  }

  float f = feed > 1.0f ? feed : feedMmMin;
  // time for the path at feed (mm/min) → µs per Bresenham tick
  uint32_t stepUs = (uint32_t)((distMm / f) * 60000000.0f / (float)steps);
  if (stepUs < MIN_STEP_US) stepUs = MIN_STEP_US;

  int32_t err = adx - ady;
  int32_t cx = xSteps;
  int32_t cy = ySteps;
  while (cx != tx || cy != ty) {
    const uint32_t t0 = micros();
    const int32_t e2 = err * 2;
    if (e2 > -ady) {
      err -= ady;
      stepAxis(true, (int8_t)sx);
      cx += sx;
    }
    if (e2 < adx) {
      err += adx;
      stepAxis(false, (int8_t)sy);
      cy += sy;
    }
    while ((uint32_t)(micros() - t0) < stepUs) {
      // wait
    }
  }
  xMm = targetX;
  yMm = targetY;
}

bool setSetting(const String &line, const char *prefix, float &dest) {
  if (!line.startsWith(prefix)) return false;
  dest = line.substring(strlen(prefix)).toFloat();
  reply("ok");
  return true;
}

void handleSystem(String line) {
  if (line == "?" || line == "$") {
    reply("steps/mm X:" + String(stepsPerMmX, 3) + " Y:" + String(stepsPerMmY, 3));
    reply("bed " + String(bedMaxX, 1) + " x " + String(bedMaxY, 1) + " mm");
    reply("pos X:" + String(xMm, 2) + " Y:" + String(yMm, 2) +
          (penIsDown ? " pen:down" : " pen:up"));
    reply("style:" + String(stepStyle == SINGLE ? "SINGLE" : "DOUBLE") +
          " invert X:" + String(dirX) + " Y:" + String(dirY));
    reply("ok");
    return;
  }
  if (setSetting(line, "$STEPSX=", stepsPerMmX) ||
      setSetting(line, "$STEPSY=", stepsPerMmY) ||
      setSetting(line, "$BEDX=", bedMaxX) ||
      setSetting(line, "$BEDY=", bedMaxY) ||
      setSetting(line, "$PENTHRESH=", penDownThresholdS)) {
    return;
  }
  if (line.startsWith("$INVERTX=")) {
    dirX = line.substring(9).toInt() ? -1 : 1;
    reply("ok");
    return;
  }
  if (line.startsWith("$INVERTY=")) {
    dirY = line.substring(9).toInt() ? -1 : 1;
    reply("ok");
    return;
  }
  if (line.startsWith("$STYLE=")) {
    stepStyle = (line.substring(7).toInt() >= 2) ? DOUBLE : SINGLE;
    reply("ok");
    return;
  }
  if (line.startsWith("$PENUP=")) {
    penUpDeg = (uint8_t)constrain(line.substring(7).toInt(), 0, 180);
    if (!penIsDown && servoAttached) penServo.write(penUpDeg);
    reply("ok");
    return;
  }
  if (line.startsWith("$PENDOWN=")) {
    penDownDeg = (uint8_t)constrain(line.substring(9).toInt(), 0, 180);
    if (penIsDown && servoAttached) penServo.write(penDownDeg);
    reply("ok");
    return;
  }
  // Move N mm on one axis so you can measure and set steps/mm.
  // After "$CALX=10" and measuring D mm of travel: $STEPSX=(10/D)*current
  if (line.startsWith("$CALX=")) {
    float mm = line.substring(6).toFloat();
    reply("echo:cal X " + String(mm, 2) + " mm — measure travel, then set $STEPSX=");
    moveLinear(xMm + mm, yMm, 120.0f);
    reply("ok");
    return;
  }
  if (line.startsWith("$CALY=")) {
    float mm = line.substring(6).toFloat();
    reply("echo:cal Y " + String(mm, 2) + " mm — measure travel, then set $STEPSY=");
    moveLinear(xMm, yMm + mm, 120.0f);
    reply("ok");
    return;
  }
  reply("echo:ignored " + line);
  reply("ok");
}

void executeGcode(String line) {
  line.trim();
  const int cmt = line.indexOf(';');
  if (cmt >= 0) line.remove(cmt);
  line.toUpperCase();
  line.trim();
  if (line.length() == 0) return;

  if (line[0] == '$' || line == "?") {
    handleSystem(line);
    return;
  }

  const int gCode = extractCode(line, 'G');
  const int mCode = extractCode(line, 'M');

  if (mCode == 3 || mCode == 4) {
    setPen(true);
    reply("ok");
    return;
  }
  if (mCode == 5) {
    setPen(false);
    reply("ok");
    return;
  }
  if (mCode == 2 || mCode == 30) {
    setPen(false);
    releaseMotors();
    reply("ok");
    return;
  }
  if (mCode == 300 || mCode == 280) {
    float s = 0;
    if (extractValue(line, 'S', s)) setPen(s <= penDownThresholdS);
    reply("ok");
    return;
  }
  if (mCode == 18 || mCode == 84) {
    releaseMotors();
    reply("ok");
    return;
  }
  if (mCode == 105) {
    reply("ok T:0.0 /0.0 B:0.0 /0.0");
    return;
  }
  if (mCode == 114) {
    reply("X:" + String(xMm, 2) + " Y:" + String(yMm, 2) + " Z:0.00 E:0.00");
    reply("ok");
    return;
  }
  if (gCode == 20) {
    unitScaleMm = 25.4f;
    reply("ok");
    return;
  }
  if (gCode == 21) {
    unitScaleMm = 1.0f;
    reply("ok");
    return;
  }
  if (gCode == 90) {
    absoluteMode = true;
    reply("ok");
    return;
  }
  if (gCode == 91) {
    absoluteMode = false;
    reply("ok");
    return;
  }
  if (gCode == 92) {
    float v = 0;
    if (extractValue(line, 'X', v)) xMm = v * unitScaleMm;
    if (extractValue(line, 'Y', v)) yMm = v * unitScaleMm;
    xSteps = lround(xMm * stepsPerMmX);
    ySteps = lround(yMm * stepsPerMmY);
    reply("ok");
    return;
  }
  if (gCode == 28) {
    setPen(false);
    moveLinear(0.0f, 0.0f, RAPID_MM_MIN);
    reply("ok");
    return;
  }
  if (gCode != 0 && gCode != 1) {
    reply("echo:ignored " + line);
    reply("ok");
    return;
  }

  float xv = 0, yv = 0, z = 0, feed = feedMmMin;
  const bool hasX = extractValue(line, 'X', xv);
  const bool hasY = extractValue(line, 'Y', yv);
  const bool hasZ = extractValue(line, 'Z', z);
  if (extractValue(line, 'F', feed)) feedMmMin = feed * unitScaleMm;

  float x = hasX ? xv * unitScaleMm : xMm;
  float y = hasY ? yv * unitScaleMm : yMm;
  if (!absoluteMode) {
    if (hasX) x = xMm + xv * unitScaleMm;
    if (hasY) y = yMm + yv * unitScaleMm;
  }
  if (hasZ) setPen(z * unitScaleMm <= 0.0f);
  if (hasX || hasY) {
    moveLinear(x, y, gCode == 0 ? RAPID_MM_MIN : feedMmMin);
  }
  reply("ok");
}

void setup() {
  Serial.begin(115200);
  releaseMotors();
  // Attach servo if present; harmless if nothing is plugged in.
  penServo.attach(SERVO_PIN);
  servoAttached = true;
  penServo.write(penUpDeg);
  penIsDown = false;

  reply("Uno HW-130 DVD Plotter ready");
  reply("bed " + String(bedMaxX, 0) + "x" + String(bedMaxY, 0) +
        " mm — centre sleds, then send G-code");
}

void loop() {
  while (Serial.available()) {
    const char ch = (char)Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (lineBuf.length() > 0) {
        executeGcode(lineBuf);
        lineBuf = "";
      }
    } else if (lineBuf.length() < 100) {
      lineBuf += ch;
    } else {
      lineBuf = "";
      reply("error: line too long");
    }
  }
}
