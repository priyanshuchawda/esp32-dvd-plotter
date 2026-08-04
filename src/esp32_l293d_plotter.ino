#include <Arduino.h>
#include <BluetoothSerial.h>
#include <ctype.h>
#include <math.h>

BluetoothSerial SerialBT;

// Empty 74HC595 socket directions. Never connect an ESP32 GPIO to socket pin 16.
constexpr uint8_t X_M1_A = 16;  // Socket pin 2
constexpr uint8_t X_M1_B = 17;  // Socket pin 3
constexpr uint8_t X_M2_A = 18;  // Socket pin 1
constexpr uint8_t X_M2_B = 19;  // Socket pin 4
constexpr uint8_t Y_M3_A = 21;  // Socket pin 5
constexpr uint8_t Y_M3_B = 22;  // Socket pin 7
constexpr uint8_t Y_M4_A = 23;  // Socket pin 15
constexpr uint8_t Y_M4_B = 13;  // Socket pin 6

// HW-130 Arduino-header PWM/enable pads: D11, D3, D6, D5.
constexpr uint8_t ENABLE_M1 = 25;
constexpr uint8_t ENABLE_M2 = 26;
constexpr uint8_t ENABLE_M3 = 27;
constexpr uint8_t ENABLE_M4 = 32;
constexpr uint8_t SERVO_PIN = 33;

constexpr uint8_t FULL_SPEED_PWM = 255;
constexpr float RAPID_FEED_MM_MIN = 300.0f;
constexpr float DEFAULT_FEED_MM_MIN = 180.0f;
constexpr uint32_t MIN_STEP_INTERVAL_US = 2000;
constexpr uint16_t SERVO_FREQUENCY_HZ = 50;
constexpr uint8_t SERVO_RESOLUTION_BITS = 16;

struct FourWireStepper {
  uint8_t coil1A;
  uint8_t coil1B;
  uint8_t coil2A;
  uint8_t coil2B;
  int8_t phase = 0;
  int32_t positionSteps = 0;

  void begin() const {
    pinMode(coil1A, OUTPUT);
    pinMode(coil1B, OUTPUT);
    pinMode(coil2A, OUTPUT);
    pinMode(coil2B, OUTPUT);
    release();
  }

  void release() const {
    digitalWrite(coil1A, LOW);
    digitalWrite(coil1B, LOW);
    digitalWrite(coil2A, LOW);
    digitalWrite(coil2B, LOW);
  }

  void applyPhase() const {
    // Both coils energized: high torque, four full steps per electrical cycle.
    switch (phase & 0x03) {
      case 0:
        digitalWrite(coil1A, HIGH); digitalWrite(coil1B, LOW);
        digitalWrite(coil2A, HIGH); digitalWrite(coil2B, LOW);
        break;
      case 1:
        digitalWrite(coil1A, LOW); digitalWrite(coil1B, HIGH);
        digitalWrite(coil2A, HIGH); digitalWrite(coil2B, LOW);
        break;
      case 2:
        digitalWrite(coil1A, LOW); digitalWrite(coil1B, HIGH);
        digitalWrite(coil2A, LOW); digitalWrite(coil2B, HIGH);
        break;
      default:
        digitalWrite(coil1A, HIGH); digitalWrite(coil1B, LOW);
        digitalWrite(coil2A, LOW); digitalWrite(coil2B, HIGH);
        break;
    }
  }

  void step(int8_t direction) {
    phase = (phase + (direction > 0 ? 1 : 3)) & 0x03;
    positionSteps += direction > 0 ? 1 : -1;
    applyPhase();
  }
};

FourWireStepper xMotor {X_M1_A, X_M1_B, X_M2_A, X_M2_B};
FourWireStepper yMotor {Y_M3_A, Y_M3_B, Y_M4_A, Y_M4_B};

// These are estimates for common DVD mechanisms driven in full-step mode.
// Calibrate using $STEPSX= and $STEPSY= after measuring a move.
float stepsPerMmX = 6.667f;
float stepsPerMmY = 6.667f;
float feedRateMmMin = DEFAULT_FEED_MM_MIN;
float xPositionMm = 0.0f;
float yPositionMm = 0.0f;
float unitScaleMm = 1.0f;
bool absoluteMode = true;
bool motorsEnabled = false;
uint16_t penUpUs = 1000;
uint16_t penDownUs = 1600;
uint16_t penSettleMs = 250;
bool penIsDown = false;

String usbLine;
String bluetoothLine;

void reply(const String &message) {
  Serial.print(message);
  SerialBT.print(message);
}

void replyLine(const String &message) {
  reply(message + "\r\n");
}

void setMotorEnable(bool enabled) {
  motorsEnabled = enabled;
  const uint8_t duty = enabled ? FULL_SPEED_PWM : 0;
  analogWrite(ENABLE_M1, duty);
  analogWrite(ENABLE_M2, duty);
  analogWrite(ENABLE_M3, duty);
  analogWrite(ENABLE_M4, duty);
  if (!enabled) {
    xMotor.release();
    yMotor.release();
  }
}

uint32_t pulseToDuty(uint16_t pulseUs) {
  constexpr uint32_t maxDuty = (1UL << SERVO_RESOLUTION_BITS) - 1;
  return (static_cast<uint32_t>(pulseUs) * maxDuty) / 20000UL;
}

void setPen(bool down) {
  const bool changed = down != penIsDown;
  penIsDown = down;
  ledcWrite(SERVO_PIN, pulseToDuty(down ? penDownUs : penUpUs));
  // The SG90 needs time to travel; moving during it would drag the pen tip.
  if (changed) delay(penSettleMs);
}

void showStatus() {
  String state = "<Idle|MPos:";
  state += String(xPositionMm, 3) + "," + String(yPositionMm, 3);
  state += "|Pen:" + String(penIsDown ? "Down" : "Up");
  state += "|Motors:" + String(motorsEnabled ? "On" : "Off") + ">";
  replyLine(state);
}

bool extractValue(const String &line, char code, float &value) {
  for (size_t i = 0; i < line.length(); ++i) {
    if (line[i] != code) continue;
    if (i > 0 && isalpha(static_cast<unsigned char>(line[i - 1]))) continue;
    char *end = nullptr;
    const float parsed = strtof(line.c_str() + i + 1, &end);
    if (end != line.c_str() + i + 1) {
      value = parsed;
      return true;
    }
  }
  return false;
}

int extractIntegerCode(const String &line, char code) {
  float value = 0;
  return extractValue(line, code, value) ? static_cast<int>(lroundf(value)) : -1;
}

void moveLinear(float targetX, float targetY, float feedMmMin) {
  const int32_t targetXSteps = lroundf(targetX * stepsPerMmX);
  const int32_t targetYSteps = lroundf(targetY * stepsPerMmY);
  const int32_t deltaX = targetXSteps - xMotor.positionSteps;
  const int32_t deltaY = targetYSteps - yMotor.positionSteps;
  const int32_t absX = abs(deltaX);
  const int32_t absY = abs(deltaY);
  const int32_t majorSteps = max(absX, absY);

  if (majorSteps == 0) {
    xPositionMm = targetX;
    yPositionMm = targetY;
    return;
  }

  setMotorEnable(true);
  const float distanceMm = hypotf(targetX - xPositionMm, targetY - yPositionMm);
  const float safeFeed = max(feedMmMin, 1.0f);
  const uint32_t intervalUs = max(
      MIN_STEP_INTERVAL_US,
      static_cast<uint32_t>((distanceMm * 60000000.0f) / (safeFeed * majorSteps)));

  int32_t error = absX - absY;
  const int8_t signX = deltaX >= 0 ? 1 : -1;
  const int8_t signY = deltaY >= 0 ? 1 : -1;

  for (;;) {
    if (xMotor.positionSteps == targetXSteps && yMotor.positionSteps == targetYSteps) break;
    const int32_t twiceError = 2 * error;
    if (twiceError > -absY && xMotor.positionSteps != targetXSteps) {
      error -= absY;
      xMotor.step(signX);
    }
    if (twiceError < absX && yMotor.positionSteps != targetYSteps) {
      error += absX;
      yMotor.step(signY);
    }
    delayMicroseconds(intervalUs);
  }

  xPositionMm = targetX;
  yPositionMm = targetY;
}

bool setSetting(const String &line, const char *prefix, float &setting) {
  if (!line.startsWith(prefix)) return false;
  const float candidate = line.substring(strlen(prefix)).toFloat();
  if (candidate <= 0.0f) {
    replyLine("error: value must be positive");
  } else {
    setting = candidate;
    replyLine("ok");
  }
  return true;
}

void handleSystemCommand(const String &line) {
  if (line == "$HELP") {
    replyLine("$STATUS, $STEPSX=value, $STEPSY=value, $PENUP=us, $PENDOWN=us, "
              "$PENSETTLE=ms, $MOTORS=ON|OFF");
    return;
  }
  if (line == "$STATUS" || line == "?") {
    showStatus();
    return;
  }
  if (setSetting(line, "$STEPSX=", stepsPerMmX) || setSetting(line, "$STEPSY=", stepsPerMmY)) return;

  if (line.startsWith("$PENUP=") || line.startsWith("$PENDOWN=")) {
    const bool isUp = line.startsWith("$PENUP=");
    const uint16_t pulse = static_cast<uint16_t>(line.substring(isUp ? 7 : 9).toInt());
    if (pulse < 500 || pulse > 2500) {
      replyLine("error: servo pulse must be 500..2500us");
      return;
    }
    if (isUp) penUpUs = pulse; else penDownUs = pulse;
    setPen(penIsDown);
    replyLine("ok");
    return;
  }

  if (line.startsWith("$PENSETTLE=")) {
    const long settle = line.substring(11).toInt();
    if (settle < 0 || settle > 2000) {
      replyLine("error: pen settle must be 0..2000ms");
      return;
    }
    penSettleMs = static_cast<uint16_t>(settle);
    replyLine("ok");
    return;
  }

  if (line == "$MOTORS=ON") {
    setMotorEnable(true);
    replyLine("ok");
    return;
  }
  if (line == "$MOTORS=OFF") {
    setMotorEnable(false);
    replyLine("ok");
    return;
  }
  replyLine("error: unsupported system command");
}

void executeGcode(String line) {
  line.trim();
  const int comment = line.indexOf(';');
  if (comment >= 0) line.remove(comment);
  line.toUpperCase();
  line.trim();
  if (line.isEmpty()) return;

  if (line[0] == '$' || line == "?") {
    handleSystemCommand(line);
    return;
  }

  const int gCode = extractIntegerCode(line, 'G');
  const int mCode = extractIntegerCode(line, 'M');
  if (mCode == 3 || mCode == 4) {
    setPen(true);
    replyLine("ok");
    return;
  }
  if (mCode == 5) {
    setPen(false);
    replyLine("ok");
    return;
  }
  if (mCode == 2 || mCode == 30) {
    setPen(false);
    setMotorEnable(false);
    replyLine("ok");
    return;
  }
  if (gCode == 20) {
    unitScaleMm = 25.4f;
    replyLine("ok");
    return;
  }
  if (gCode == 21) {
    unitScaleMm = 1.0f;
    replyLine("ok");
    return;
  }
  if (gCode == 90) {
    absoluteMode = true;
    replyLine("ok");
    return;
  }
  if (gCode == 91) {
    absoluteMode = false;
    replyLine("ok");
    return;
  }
  if (gCode == 92) {
    float value = 0;
    if (extractValue(line, 'X', value)) xPositionMm = value * unitScaleMm;
    if (extractValue(line, 'Y', value)) yPositionMm = value * unitScaleMm;
    xMotor.positionSteps = lroundf(xPositionMm * stepsPerMmX);
    yMotor.positionSteps = lroundf(yPositionMm * stepsPerMmY);
    replyLine("ok");
    return;
  }
  if (gCode != 0 && gCode != 1) {
    replyLine("error: supported G-codes are G0, G1, G20, G21, G90, G91, G92");
    return;
  }

  float xValue = 0;
  float yValue = 0;
  float z = 0;
  float feed = feedRateMmMin;
  const bool hasX = extractValue(line, 'X', xValue);
  const bool hasY = extractValue(line, 'Y', yValue);
  const bool hasZ = extractValue(line, 'Z', z);
  if (extractValue(line, 'F', feed)) feedRateMmMin = feed * unitScaleMm;
  float x = hasX ? xValue * unitScaleMm : xPositionMm;
  float y = hasY ? yValue * unitScaleMm : yPositionMm;
  if (!absoluteMode) {
    if (hasX) x += xPositionMm;
    if (hasY) y += yPositionMm;
  }
  if (hasZ) setPen(z * unitScaleMm <= 0.0f);
  if (hasX || hasY) moveLinear(x, y, gCode == 0 ? RAPID_FEED_MM_MIN : feedRateMmMin);
  replyLine("ok");
}

void consumeInput(Stream &input, String &buffer) {
  while (input.available()) {
    const char character = static_cast<char>(input.read());
    if (character == '\r' || character == '\n') {
      if (!buffer.isEmpty()) {
        executeGcode(buffer);
        buffer = "";
      }
    } else if (buffer.length() < 120) {
      buffer += character;
    } else {
      buffer = "";
      replyLine("error: line too long");
    }
  }
}

void setup() {
  Serial.begin(115200);
  SerialBT.begin("DVD_Plotter");

  pinMode(ENABLE_M1, OUTPUT);
  pinMode(ENABLE_M2, OUTPUT);
  pinMode(ENABLE_M3, OUTPUT);
  pinMode(ENABLE_M4, OUTPUT);
  xMotor.begin();
  yMotor.begin();
  setMotorEnable(false);

  ledcAttach(SERVO_PIN, SERVO_FREQUENCY_HZ, SERVO_RESOLUTION_BITS);
  setPen(false);

  replyLine("ESP32 L293D DVD Plotter ready");
  replyLine("Use $HELP before moving; motors begin disabled.");
}

void loop() {
  consumeInput(Serial, usbLine);
  consumeInput(SerialBT, bluetoothLine);
}
