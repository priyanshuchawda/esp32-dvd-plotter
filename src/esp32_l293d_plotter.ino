#include <Arduino.h>
#include <ctype.h>
#include <math.h>

// Both radios fit in huge_app together (52% of flash), but Bluetooth Classic
// and WiFi share one antenna and coexistence costs throughput and stability.
// The phone drawing UI only needs WiFi, so Bluetooth stays off unless you
// specifically want to drive the plotter from a serial terminal as well.
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

// Leave the SSID empty to host a hotspot instead of joining a network.
// Joining your own network is nicer: the phone keeps its internet connection.
const char *WIFI_SSID = "";
const char *WIFI_PASSWORD = "";
const char *AP_SSID = "DVD-Plotter";
const char *AP_PASSWORD = "plotter123";  // must be at least 8 characters

constexpr float BED_SIZE_MM = 35.0f;
constexpr size_t MAX_JOB_BYTES = 60000;

WebServer server(80);
String jobBuffer;
size_t jobCursor = 0;
bool jobActive = false;
#endif

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
// SVG-to-G-code tools raise and lower the pen with M300 S<angle> rather than
// Z moves. Unicorn emits S30 for down and S50 for up, so anything at or below
// this threshold counts as pen down.
float penDownThresholdS = 40.0f;

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

// Drives one H-bridge output at a time. Its partner is held low, so current
// flows through just that coil in one direction and the motor gives a single
// clear twitch. If a twitch is missing, or two outputs move the same coil,
// the pairs are split across the terminal blocks.
void coilTest() {
  struct Output { const char *name; uint8_t pin; };
  const Output outputs[] = {
      {"X coil 1, forward", X_M1_A}, {"X coil 1, reverse", X_M1_B},
      {"X coil 2, forward", X_M2_A}, {"X coil 2, reverse", X_M2_B},
      {"Y coil 1, forward", Y_M3_A}, {"Y coil 1, reverse", Y_M3_B},
      {"Y coil 2, forward", Y_M4_A}, {"Y coil 2, reverse", Y_M4_B},
  };

  replyLine("Coil test: 8 pulses, each 600 ms. Expect one twitch per pulse.");
  xMotor.release();
  yMotor.release();
  setMotorEnable(true);
  for (const Output &output : outputs) {
    replyLine(String("  ") + output.name);
    digitalWrite(output.pin, HIGH);
    delay(600);
    digitalWrite(output.pin, LOW);
    delay(250);
  }
  setMotorEnable(false);
  replyLine("Test finished, motors released.");
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
    replyLine("$STATUS, $COILTEST, $STEPSX=value, $STEPSY=value, $PENUP=us, "
              "$PENDOWN=us, $PENSETTLE=ms, $PENTHRESH=value, $MOTORS=ON|OFF");
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
  // M300 (Unicorn) and M280 (generic servo) both carry the pen angle in S.
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
  // Pronterface polls temperature on a timer. Answering keeps it from
  // reporting the printer as unresponsive part-way through a plot.
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
  // There are no endstops, so "home" can only mean returning to where the
  // carriages sat at power-on. Centre them by hand before switching on.
  if (gCode == 28) {
    setPen(false);
    moveLinear(0.0f, 0.0f, RAPID_FEED_MM_MIN);
    replyLine("ok");
    return;
  }
  if (gCode != 0 && gCode != 1) {
    // A host expects exactly one ok per line and will stall forever if an
    // unknown command is answered with an error alone, so acknowledge it and
    // report what was skipped.
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
  // Substituted here so the page can never disagree with the firmware.
  page.replace("__BED__", String(BED_SIZE_MM, 1));
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

// One line per loop pass, so the web server stays responsive between moves
// and Stop actually gets a chance to be heard mid-plot.
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

  pinMode(ENABLE_M1, OUTPUT);
  pinMode(ENABLE_M2, OUTPUT);
  pinMode(ENABLE_M3, OUTPUT);
  pinMode(ENABLE_M4, OUTPUT);
  xMotor.begin();
  yMotor.begin();
  setMotorEnable(false);

  ledcAttach(SERVO_PIN, SERVO_FREQUENCY_HZ, SERVO_RESOLUTION_BITS);
  setPen(false);

#if ENABLE_WIFI
  startNetwork();
#endif

  replyLine("ESP32 L293D DVD Plotter ready");
  replyLine("Use $HELP before moving; motors begin disabled.");
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
