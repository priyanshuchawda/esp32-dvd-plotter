#include <Arduino.h>
#include <ctype.h>
#include <math.h>

// ESP32 + HW-130 (L293D) via the stock 74HC595 path — no soldering.
// Jumpers from ESP32 GPIOs into the shield's Arduino female headers.
// Uno firmware stays in src/uno/; swap boards by unplugging jumpers / restacking.
//
//   arduino-cli compile -b esp32:esp32:esp32 src/esp32/esp32_plotter
//   arduino-cli upload  -b esp32:esp32:esp32 -p /dev/ttyUSB0 src/esp32/esp32_plotter
//
// Power: shield 5V + GND from a regulated 5 V supply (logic).
//        motors on EXT_PWR (yellow PWR jumper OFF). ESP32 from USB.
//        Common GND between ESP32, shield, and supply.

#define ENABLE_WIFI 1
#define ENABLE_BLUETOOTH 0

#if ENABLE_BLUETOOTH
#include <BluetoothSerial.h>
BluetoothSerial SerialBT;
#endif

#if ENABLE_WIFI
#include <WiFi.h>
#include <WebServer.h>
#include "web_ui.h"

const char *WIFI_SSID = "";
const char *WIFI_PASSWORD = "";
const char *AP_SSID = "DVD-Plotter";
const char *AP_PASSWORD = "plotter123";

constexpr float BED_W_MM = 55.0f;
constexpr float BED_H_MM = 50.0f;
constexpr size_t MAX_JOB_BYTES = 60000;

WebServer server(80);
String jobBuffer;
size_t jobCursor = 0;
bool jobActive = false;
#endif

// Shield Arduino-header labels → ESP32 GPIOs (jumper wires only).
// Same four control lines AFMotor uses on an Uno.
constexpr uint8_t PIN_MOTOR_LATCH = 18;   // D12
constexpr uint8_t PIN_MOTOR_CLK = 19;     // D4
constexpr uint8_t PIN_MOTOR_ENABLE = 23;  // D7  (74HC595 OE, active LOW)
constexpr uint8_t PIN_MOTOR_DATA = 13;    // D8

constexpr uint8_t PIN_PWM_M1 = 25;  // D11
constexpr uint8_t PIN_PWM_M2 = 26;  // D3
constexpr uint8_t PIN_PWM_M3 = 27;  // D6
constexpr uint8_t PIN_PWM_M4 = 32;  // D5
constexpr uint8_t PIN_SERVO = 33;   // SERVO_1 signal (or D9/D10 pad)

// AFMotor bit positions inside the 74HC595 latch byte.
constexpr uint8_t BIT_M1_A = 2;
constexpr uint8_t BIT_M1_B = 3;
constexpr uint8_t BIT_M2_A = 1;
constexpr uint8_t BIT_M2_B = 4;
constexpr uint8_t BIT_M3_A = 5;
constexpr uint8_t BIT_M3_B = 7;
constexpr uint8_t BIT_M4_A = 0;
constexpr uint8_t BIT_M4_B = 6;

constexpr uint8_t FULL_SPEED_PWM = 255;
constexpr uint32_t ENABLE_PWM_HZ = 20000;
constexpr float RAPID_FEED_MM_MIN = 300.0f;
constexpr float DEFAULT_FEED_MM_MIN = 180.0f;
constexpr uint32_t MIN_STEP_INTERVAL_US = 2000;
constexpr uint16_t SERVO_FREQUENCY_HZ = 50;
constexpr uint8_t SERVO_RESOLUTION_BITS = 16;

uint8_t latchState = 0;

void latchTx() {
  digitalWrite(PIN_MOTOR_LATCH, LOW);
  for (uint8_t i = 0; i < 8; ++i) {
    digitalWrite(PIN_MOTOR_CLK, LOW);
    digitalWrite(PIN_MOTOR_DATA, (latchState & (1u << (7 - i))) ? HIGH : LOW);
    digitalWrite(PIN_MOTOR_CLK, HIGH);
  }
  digitalWrite(PIN_MOTOR_LATCH, HIGH);
  digitalWrite(PIN_MOTOR_LATCH, LOW);
}

void shiftBegin() {
  pinMode(PIN_MOTOR_LATCH, OUTPUT);
  pinMode(PIN_MOTOR_CLK, OUTPUT);
  pinMode(PIN_MOTOR_ENABLE, OUTPUT);
  pinMode(PIN_MOTOR_DATA, OUTPUT);
  latchState = 0;
  latchTx();
  digitalWrite(PIN_MOTOR_ENABLE, LOW);  // enable 74HC595 outputs
}

// AFMotor SINGLE-style bipolar sequence (matches Uno calibration).
struct ShieldStepper {
  uint8_t bitA;  // coil 1 A
  uint8_t bitB;  // coil 2 A
  uint8_t bitC;  // coil 1 B
  uint8_t bitD;  // coil 2 B
  uint8_t phase = 0;
  int32_t positionSteps = 0;

  void clearBits() {
    latchState &= ~((1u << bitA) | (1u << bitB) | (1u << bitC) | (1u << bitD));
  }

  void release() {
    clearBits();
    latchTx();
  }

  void applyPhase() {
    clearBits();
    switch (phase & 0x03) {
      case 0: latchState |= (1u << bitA); break;
      case 1: latchState |= (1u << bitB); break;
      case 2: latchState |= (1u << bitC); break;
      default: latchState |= (1u << bitD); break;
    }
    latchTx();
  }

  void step(int8_t direction) {
    phase = (phase + (direction > 0 ? 1 : 3)) & 0x03;
    positionSteps += direction > 0 ? 1 : -1;
    applyPhase();
  }
};

ShieldStepper xMotor {BIT_M1_A, BIT_M2_A, BIT_M1_B, BIT_M2_B};  // M1+M2
ShieldStepper yMotor {BIT_M3_A, BIT_M4_A, BIT_M3_B, BIT_M4_B};  // M3+M4

// Same calibration as Uno (FINDINGS.md). Re-check after swapping boards.
float stepsPerMmX = 2.058f;
float stepsPerMmY = 2.058f;
float bedMaxX = 55.0f;
float bedMaxY = 50.0f;
float feedRateMmMin = DEFAULT_FEED_MM_MIN;
float xPositionMm = 0.0f;
float yPositionMm = 0.0f;
float unitScaleMm = 1.0f;
bool absoluteMode = true;
bool motorsEnabled = false;
uint8_t motorPowerPercent = 70;
uint16_t penUpUs = 1000;
uint16_t penDownUs = 1600;
uint16_t penSettleMs = 250;
bool penIsDown = false;
float penDownThresholdS = 40.0f;
int8_t dirX = 1;
int8_t dirY = 1;

String usbLine;
String bluetoothLine;

void reply(const String &message) {
  Serial.print(message);
#if ENABLE_BLUETOOTH
  SerialBT.print(message);
#endif
}

void replyLine(const String &message) {
  reply(message + "\r\n");
}

void setMotorEnable(bool enabled) {
  motorsEnabled = enabled;
  const uint8_t duty =
      enabled ? static_cast<uint8_t>((FULL_SPEED_PWM * motorPowerPercent) / 100) : 0;
  analogWrite(PIN_PWM_M1, duty);
  analogWrite(PIN_PWM_M2, duty);
  analogWrite(PIN_PWM_M3, duty);
  analogWrite(PIN_PWM_M4, duty);
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
  ledcWrite(PIN_SERVO, pulseToDuty(down ? penDownUs : penUpUs));
  if (changed) delay(penSettleMs);
}

void coilTest() {
  struct Pulse { const char *name; uint8_t bit; };
  const Pulse pulses[] = {
      {"X M1A", BIT_M1_A}, {"X M1B", BIT_M1_B},
      {"X M2A", BIT_M2_A}, {"X M2B", BIT_M2_B},
      {"Y M3A", BIT_M3_A}, {"Y M3B", BIT_M3_B},
      {"Y M4A", BIT_M4_A}, {"Y M4B", BIT_M4_B},
  };

  replyLine("Coil test: 8 pulses via 74HC595. Expect one twitch each.");
  xMotor.release();
  yMotor.release();
  setMotorEnable(true);
  for (const Pulse &p : pulses) {
    replyLine(String("  ") + p.name);
    latchState = (1u << p.bit);
    latchTx();
    delay(600);
    latchState = 0;
    latchTx();
    delay(250);
  }
  setMotorEnable(false);
  replyLine("Test finished, motors released.");
}

void showStatus() {
  String state = "<Idle|MPos:";
  state += String(xPositionMm, 3) + "," + String(yPositionMm, 3);
  state += "|Pen:" + String(penIsDown ? "Down" : "Up");
  state += "|Motors:" + String(motorsEnabled ? "On" : "Off");
  state += "|Pwr:" + String(motorPowerPercent) + "%>";
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
  targetX = constrain(targetX, 0.0f, bedMaxX);
  targetY = constrain(targetY, 0.0f, bedMaxY);

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
  const int8_t logicalX = deltaX >= 0 ? 1 : -1;
  const int8_t logicalY = deltaY >= 0 ? 1 : -1;

  for (;;) {
    if (xMotor.positionSteps == targetXSteps && yMotor.positionSteps == targetYSteps) break;
    const int32_t twiceError = 2 * error;
    if (twiceError > -absY && xMotor.positionSteps != targetXSteps) {
      error -= absY;
      // dirX/dirY only flip the physical coil sequence; software steps stay logical.
      xMotor.phase = (xMotor.phase + ((logicalX * dirX > 0) ? 1 : 3)) & 0x03;
      xMotor.positionSteps += logicalX;
      xMotor.applyPhase();
    }
    if (twiceError < absX && yMotor.positionSteps != targetYSteps) {
      error += absX;
      yMotor.phase = (yMotor.phase + ((logicalY * dirY > 0) ? 1 : 3)) & 0x03;
      yMotor.positionSteps += logicalY;
      yMotor.applyPhase();
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
    replyLine("$STATUS $COILTEST $POWER=pct $STEPSX= $STEPSY= "
              "$INVERTX=0|1 $INVERTY=0|1 $PENUP=us $PENDOWN=us "
              "$PENSETTLE=ms $PENTHRESH= $MOTORS=ON|OFF");
    return;
  }
  if (line == "$STATUS" || line == "?") {
    showStatus();
    return;
  }
  if (line == "$COILTEST") {
    coilTest();
    replyLine("ok");
    return;
  }
  if (setSetting(line, "$STEPSX=", stepsPerMmX) || setSetting(line, "$STEPSY=", stepsPerMmY) ||
      setSetting(line, "$PENTHRESH=", penDownThresholdS)) return;

  if (line.startsWith("$INVERTX=")) {
    dirX = line.substring(9).toInt() ? -1 : 1;
    replyLine("ok");
    return;
  }
  if (line.startsWith("$INVERTY=")) {
    dirY = line.substring(9).toInt() ? -1 : 1;
    replyLine("ok");
    return;
  }

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

  if (line.startsWith("$POWER=")) {
    const long percent = line.substring(7).toInt();
    if (percent < 5 || percent > 100) {
      replyLine("error: power must be 5..100 percent");
      return;
    }
    motorPowerPercent = static_cast<uint8_t>(percent);
    if (motorsEnabled) setMotorEnable(true);
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
  if (mCode == 300 || mCode == 280) {
    float sValue = 0;
    if (extractValue(line, 'S', sValue)) setPen(sValue <= penDownThresholdS);
    replyLine("ok");
    return;
  }
  if (mCode == 18 || mCode == 84) {
    setMotorEnable(false);
    replyLine("ok");
    return;
  }
  if (mCode == 105) {
    replyLine("ok T:0.0 /0.0 B:0.0 /0.0");
    return;
  }
  if (mCode == 114) {
    replyLine("X:" + String(xPositionMm, 2) + " Y:" + String(yPositionMm, 2) +
              " Z:0.00 E:0.00");
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
  if (gCode == 28) {
    setPen(false);
    moveLinear(0.0f, 0.0f, RAPID_FEED_MM_MIN);
    replyLine("ok");
    return;
  }
  if (gCode != 0 && gCode != 1) {
    replyLine("echo:ignored " + line);
    replyLine("ok");
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

#if ENABLE_WIFI
void handleRoot() {
  String page = FPSTR(WEB_UI);
  page.replace("__BED_W__", String(BED_W_MM, 1));
  page.replace("__BED_H__", String(BED_H_MM, 1));
  server.send(200, "text/html", page);
}

void handlePlot() {
  if (jobActive) {
    server.send(409, "text/plain", "already plotting");
    return;
  }
  const String body = server.arg("plain");
  if (body.isEmpty()) {
    server.send(400, "text/plain", "empty drawing");
    return;
  }
  if (body.length() > MAX_JOB_BYTES) {
    server.send(413, "text/plain", "drawing too large");
    return;
  }
  jobBuffer = body;
  jobCursor = 0;
  jobActive = true;
  server.send(200, "text/plain", "plotting");
}

void handleStatus() {
  const int percent = (jobActive && jobBuffer.length() > 0)
                          ? static_cast<int>((100 * jobCursor) / jobBuffer.length())
                          : 0;
  String json = "{\"active\":";
  json += jobActive ? "true" : "false";
  json += ",\"pct\":" + String(percent);
  json += ",\"x\":" + String(xPositionMm, 2);
  json += ",\"y\":" + String(yPositionMm, 2);
  json += ",\"pen\":";
  json += penIsDown ? "true" : "false";
  json += "}";
  server.send(200, "application/json", json);
}

void endJob() {
  jobActive = false;
  jobBuffer = "";
  jobCursor = 0;
  setPen(false);
  setMotorEnable(false);
}

void handleStop() {
  endJob();
  server.send(200, "text/plain", "stopped");
}

void serviceJob() {
  if (!jobActive) return;
  if (jobCursor >= jobBuffer.length()) {
    endJob();
    return;
  }
  int newline = jobBuffer.indexOf('\n', jobCursor);
  if (newline < 0) newline = jobBuffer.length();
  const String line = jobBuffer.substring(jobCursor, newline);
  jobCursor = newline + 1;
  executeGcode(line);
}

void startNetwork() {
  if (strlen(WIFI_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; ++i) delay(250);
  }
  if (WiFi.status() == WL_CONNECTED) {
    replyLine("WiFi joined " + String(WIFI_SSID));
    replyLine("Open http://" + WiFi.localIP().toString());
  } else {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    replyLine("WiFi hotspot \"" + String(AP_SSID) + "\" password " + String(AP_PASSWORD));
    replyLine("Open http://" + WiFi.softAPIP().toString());
  }
  server.on("/", handleRoot);
  server.on("/plot", HTTP_POST, handlePlot);
  server.on("/status", handleStatus);
  server.on("/stop", HTTP_POST, handleStop);
  server.begin();
}
#endif

void setup() {
  Serial.begin(115200);
#if ENABLE_BLUETOOTH
  SerialBT.begin("DVD_Plotter");
#endif

  shiftBegin();

  pinMode(PIN_PWM_M1, OUTPUT);
  pinMode(PIN_PWM_M2, OUTPUT);
  pinMode(PIN_PWM_M3, OUTPUT);
  pinMode(PIN_PWM_M4, OUTPUT);
  for (uint8_t pin : {PIN_PWM_M1, PIN_PWM_M2, PIN_PWM_M3, PIN_PWM_M4}) {
    analogWriteFrequency(pin, ENABLE_PWM_HZ);
  }
  setMotorEnable(false);

  ledcAttach(PIN_SERVO, SERVO_FREQUENCY_HZ, SERVO_RESOLUTION_BITS);
  setPen(false);

#if ENABLE_WIFI
  startNetwork();
#endif

  replyLine("ESP32 HW-130 plotter ready (74HC595 jumper path)");
  replyLine("Use $HELP; motors start disabled. $COILTEST then $POWER=70");
}

void loop() {
  consumeInput(Serial, usbLine);
#if ENABLE_BLUETOOTH
  consumeInput(SerialBT, bluetoothLine);
#endif
#if ENABLE_WIFI
  server.handleClient();
  serviceJob();
#endif
}
