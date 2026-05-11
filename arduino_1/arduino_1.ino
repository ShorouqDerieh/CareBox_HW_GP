#include <Wire.h>
#include <RTClib.h>
#include <EEPROM.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>
#include <Servo.h>
#include <I2CKeyPad.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <string.h>
#include <stdio.h>

// ============================
// Pins
// ============================
#define STEP_PIN 3
#define DIR_PIN  4
#define HOME_IR_PIN 7
#define TAKE_IR_PIN 8
#define ENABLE_PIN 5

#define BACKWARD HIGH
#define FORWARD  LOW

#define STEPS_PER_SLOT 160
#define MAX_SLOTS 20
#define SERVO_PIN 9

// ============================
// Health Sensors
// ============================
// DS18B20 data pin
#define TEMP_PIN 2

// Pulse sensor signal pin
#define PULSE_PIN A1

#define PULSE_READ_TIME 5000
#define PULSE_DIFF_THRESHOLD 6
#define PULSE_MIN_AVG 20

Servo doorServo;

#define DOOR_CLOSED 140
#define DOOR_OPEN   40

// ============================
// Modes
// ============================
#define MODE_PRIMARY 1
#define MODE_BACKUP  2

RTC_DS3231 rtc;
hd44780_I2Cexp lcd(0x27);

// ============================
// Health objects
// ============================
OneWire oneWire(TEMP_PIN);
DallasTemperature tempSensor(&oneWire);

// ============================
// Keypad
// ============================
#define KEYPAD_ADDR 0x20

I2CKeyPad keyPad(KEYPAD_ADDR);

bool keypadReady = false;
unsigned long lastKeypadTime = 0;

// إذا الأزرار طالعة غلط، غيري هذا السطر فقط.
char keypadMap[17] = "D#0*C987B654A321";

// لو الترتيب العادي زبط معك استخدمي بدل السطر فوق:
// char keypadMap[17] = "123A456B789C*0#D";

// ============================
// State
// ============================
int currentMode = MODE_PRIMARY;
unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_TIMEOUT = 30000;

int stepDelay = 600;
int currentSlot = 0;
int lastMoveHour = -1;
int lastMoveMinute = -1;

int scheduleHours[MAX_SLOTS];
int scheduleMinutes[MAX_SLOTS];
int scheduleSlots[MAX_SLOTS];
int scheduleCount = 0;

// EEPROM layout
const int EEPROM_MAGIC_ADDR = 0;
const byte EEPROM_MAGIC = 0x42;
const int EEPROM_COUNT_ADDR = 1;
const int EEPROM_DATA_ADDR = 2;

// LCD state
unsigned long lastLcdUpdate = 0;

// Serial buffer without String
char serialBuffer[40];
byte serialIndex = 0;

// ============================
// Function prototypes
// ============================
void closeDoor();
void openDoor();
void handleSerialCommand(char *cmd);
void readSerialLines();
void updateIdleLCD();
void goToHome();
void moveOneSlot();
void moveToSlot(int targetSlot);
void executeDoseCycle(int targetSlot);
void executeMoveOnly(int targetSlot);
void runBackupScheduleCheck();
bool findNextDose(int &nextHour, int &nextMinute);

void initKeypad();
void checkKeypad();
void handleKeypadKey(char key);

void initHealthSensors();
void runHealthCheck();

// ============================
// LCD helpers
// ============================
void printLineChar(uint8_t row, const char *text) {
  lcd.setCursor(0, row);

  byte len = strlen(text);

  for (byte i = 0; i < 16; i++) {
    if (i < len) lcd.print(text[i]);
    else lcd.print(' ');
  }
}

void showScreen(const char *l1, const char *l2, const char *l3, const char *l4) {
  printLineChar(0, l1);
  printLineChar(1, l2);
  printLineChar(2, l3);
  printLineChar(3, l4);
}

void showStartupScreen() {
  showScreen("CARE BOX+ Sys", "Initializing...", "Loading modules", "Please wait");
}

void showHomingScreen() {
  showScreen("CARE BOX+ Sys", "Homing tray...", "Finding marker", "Please wait");
}

void showDispensingScreen() {
  DateTime now = rtc.now();
  char line1[17];

  snprintf(line1, sizeof(line1), "Time: %02d:%02d", now.hour(), now.minute());

  showScreen(
    line1,
    "Dispensing dose",
    "Rotating tray...",
    "Please wait"
  );
}

void showWaitingTakeScreen() {
  DateTime now = rtc.now();
  char line1[17];

  snprintf(line1, sizeof(line1), "Time: %02d:%02d", now.hour(), now.minute());

  showScreen(
    line1,
    "Medicine ready",
    "Take your pill",
    "Sensor waiting"
  );
}

void showTakenScreen() {
  DateTime now = rtc.now();
  char line1[17];

  snprintf(line1, sizeof(line1), "Time: %02d:%02d", now.hour(), now.minute());

  showScreen(
    line1,
    "Dose taken",
    "Confirmed by IR",
    "Thank you"
  );
}

void showMissedScreen() {
  DateTime now = rtc.now();
  char line1[17];

  snprintf(line1, sizeof(line1), "Time: %02d:%02d", now.hour(), now.minute());

  showScreen(
    line1,
    "Dose missed",
    "No hand detect",
    "Check patient"
  );
}

void showRtcErrorScreen() {
  showScreen("System error", "RTC not found", "Check wiring", "Restart device");
}

// ============================
// Health functions
// ============================
void initHealthSensors() {
  pinMode(PULSE_PIN, INPUT);
  tempSensor.begin();

  Serial.println(F("HEALTH_READY"));
}

void runHealthCheck() {
  showScreen(
    "Health Check",
    "Place finger",
    "Reading...",
    "Please wait"
  );

  // Read temperature
  tempSensor.requestTemperatures();
  float tempC = tempSensor.getTempCByIndex(0);

  // Read pulse signal for 5 seconds
  unsigned long start = millis();

  int minVal = 1023;
  int maxVal = 0;
  long sum = 0;
  int count = 0;

  while (millis() - start < PULSE_READ_TIME) {
    int value = analogRead(PULSE_PIN);

    if (value < minVal) minVal = value;
    if (value > maxVal) maxVal = value;

    sum += value;
    count++;

    delay(10);
  }

  int avg = 0;
  if (count > 0) {
    avg = sum / count;
  }

  int diff = maxVal - minVal;

  const char *pulseStatus;

  if (avg >= PULSE_MIN_AVG && diff >= PULSE_DIFF_THRESHOLD) {
    pulseStatus = "DETECTED";
  } else {
    pulseStatus = "WEAK";
  }

  const char *healthStatus = "NORMAL";

  if (tempC == DEVICE_DISCONNECTED_C || tempC < -100) {
    healthStatus = "TEMP ERROR";
  } else if (tempC >= 38.0) {
    healthStatus = "ALERT";
  }

  char tempStr[8];
  char line1[17];
  char line2[17];
  char line3[17];

  if (tempC == DEVICE_DISCONNECTED_C || tempC < -100) {
    snprintf(line1, sizeof(line1), "Temp: ERROR");
  } else {
    dtostrf(tempC, 4, 1, tempStr);
    snprintf(line1, sizeof(line1), "Temp:%s C", tempStr);
  }

  snprintf(line2, sizeof(line2), "Pulse:%s", pulseStatus);
  snprintf(line3, sizeof(line3), "Status:%s", healthStatus);

  showScreen(
    "Health Result",
    line1,
    line2,
    line3
  );

  Serial.print(F("HEALTH TEMP="));

  if (tempC == DEVICE_DISCONNECTED_C || tempC < -100) {
    Serial.print(F("ERROR"));
  } else {
    Serial.print(tempC, 1);
  }

  Serial.print(F(" PULSE_AVG="));
  Serial.print(avg);

  Serial.print(F(" PULSE_DIFF="));
  Serial.print(diff);

  Serial.print(F(" PULSE_STATUS="));
  Serial.print(pulseStatus);

  Serial.print(F(" STATUS="));
  Serial.println(healthStatus);

  delay(3000);
}

// ============================
// Keypad functions
// ============================
void initKeypad() {
  if (keyPad.begin()) {
    keypadReady = true;
    Serial.println(F("KEYPAD_READY"));
  } else {
    keypadReady = false;
    Serial.println(F("KEYPAD_ERROR"));
  }
}

void handleKeypadKey(char key) {
  Serial.print(F("KEY_"));
  Serial.println(key);

  if (key == 'A') {
    Serial.println(F("KEY_START_REFILL"));
  }
  else if (key == '#') {
    Serial.println(F("KEY_CONFIRM_LOADED"));
  }
  else if (key == 'B') {
    Serial.println(F("KEY_SKIP_SLOT"));
  }
  else if (key == 'D') {
    Serial.println(F("KEY_FINISH_REFILL"));
  }
  else if (key == 'C') {
    Serial.println(F("KEY_HEALTH_CHECK"));
    runHealthCheck();
  }
  else if (key == '*') {
    Serial.println(F("KEY_SCAN_QR"));
  }
}

void checkKeypad() {
  if (!keypadReady) return;

  uint8_t index = keyPad.getKey();

  if (index < 16) {
    if (millis() - lastKeypadTime < 300) {
      return;
    }

    char key = keypadMap[index];

    handleKeypadKey(key);

    lastKeypadTime = millis();

    while (keyPad.getKey() < 16) {
      delay(20);
    }
  }
}

// ============================
// EEPROM
// ============================
void saveSchedulesToEEPROM() {
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC);
  EEPROM.update(EEPROM_COUNT_ADDR, scheduleCount);

  for (int i = 0; i < scheduleCount; i++) {
    EEPROM.update(EEPROM_DATA_ADDR + i * 3, scheduleHours[i]);
    EEPROM.update(EEPROM_DATA_ADDR + i * 3 + 1, scheduleMinutes[i]);
    EEPROM.update(EEPROM_DATA_ADDR + i * 3 + 2, scheduleSlots[i]);
  }

  Serial.println(F("SAVED"));
}

void loadSchedulesFromEEPROM() {
  if (EEPROM.read(EEPROM_MAGIC_ADDR) != EEPROM_MAGIC) {
    scheduleCount = 0;
    return;
  }

  scheduleCount = EEPROM.read(EEPROM_COUNT_ADDR);

  if (scheduleCount < 0 || scheduleCount > MAX_SLOTS) {
    scheduleCount = 0;
    return;
  }

  for (int i = 0; i < scheduleCount; i++) {
    scheduleHours[i] = EEPROM.read(EEPROM_DATA_ADDR + i * 3);
    scheduleMinutes[i] = EEPROM.read(EEPROM_DATA_ADDR + i * 3 + 1);
    scheduleSlots[i] = EEPROM.read(EEPROM_DATA_ADDR + i * 3 + 2);
  }
}

// ============================
// Find next dose
// ============================
bool findNextDose(int &nextHour, int &nextMinute) {
  if (scheduleCount == 0) {
    nextHour = -1;
    nextMinute = -1;
    return false;
  }

  DateTime now = rtc.now();
  int nowMinutes = now.hour() * 60 + now.minute();

  int bestDiff = 100000;
  int bestIndex = -1;

  for (int i = 0; i < scheduleCount; i++) {
    int h = scheduleHours[i];
    int m = scheduleMinutes[i];

    if (h < 0 || h > 23 || m < 0 || m > 59) {
      continue;
    }

    if (h == lastMoveHour && m == lastMoveMinute &&
        now.hour() == h && now.minute() == m) {
      continue;
    }

    int schedMinutes = h * 60 + m;
    int diff = schedMinutes - nowMinutes;

    if (diff <= 0) {
      diff += 24 * 60;
    }

    if (bestIndex == -1 || diff < bestDiff) {
      bestDiff = diff;
      bestIndex = i;
    }
  }

  if (bestIndex == -1) {
    nextHour = -1;
    nextMinute = -1;
    return false;
  }

  nextHour = scheduleHours[bestIndex];
  nextMinute = scheduleMinutes[bestIndex];
  return true;
}

void updateIdleLCD() {
  if (millis() - lastLcdUpdate < 1000) return;
  lastLcdUpdate = millis();

  DateTime now = rtc.now();

  char line1[17];
  char line2[17];
  char line3[17];
  char line4[17];

  int nh = -1;
  int nm = -1;

  snprintf(line1, sizeof(line1), "Time: %02d:%02d", now.hour(), now.minute());
  snprintf(line2, sizeof(line2), "Mode: %s", currentMode == MODE_PRIMARY ? "PRIMARY" : "BACKUP");
  snprintf(line3, sizeof(line3), "Count: %d", scheduleCount);

  if (findNextDose(nh, nm)) {
    snprintf(line4, sizeof(line4), "Next %02d:%02d", nh, nm);
  } else {
    snprintf(line4, sizeof(line4), "Next --:--");
  }

  printLineChar(0, line1);
  printLineChar(1, line2);
  printLineChar(2, line3);
  printLineChar(3, line4);
}

// ============================
// Door control
// ============================
void closeDoor() {
  doorServo.write(DOOR_CLOSED);
  Serial.println(F("DOOR_CLOSED"));
  delay(400);
}

void openDoor() {
  doorServo.write(DOOR_OPEN);
  Serial.println(F("DOOR_OPEN"));
  delay(400);
}

// ============================
// Homing
// ============================
void goToHome() {
  closeDoor();

  Serial.println(F("HOMING_START"));
  showHomingScreen();

  digitalWrite(DIR_PIN, BACKWARD);
  delay(100);

  while (digitalRead(HOME_IR_PIN) == LOW) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(stepDelay + 300);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(stepDelay + 300);
  }

  currentSlot = 0;
  Serial.println(F("HOMED"));
}

// ============================
// Movement
// ============================
void moveOneSlot() {
  digitalWrite(DIR_PIN, FORWARD);
  delay(50);

  for (int i = 0; i < STEPS_PER_SLOT; i++) {
    int dynamicDelay = stepDelay;

    if (i < 30) {
      dynamicDelay = stepDelay + (30 - i) * 10;
    }

    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(dynamicDelay);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(dynamicDelay);
  }

  currentSlot = (currentSlot + 1) % MAX_SLOTS;
  Serial.println(F("DONE"));
}

void moveToSlot(int targetSlot) {
  int diff = (targetSlot - currentSlot + MAX_SLOTS) % MAX_SLOTS;

  Serial.print(F("Moving to slot "));
  Serial.println(targetSlot);

  for (int i = 0; i < diff; i++) {
    moveOneSlot();
  }

  currentSlot = targetSlot;
}

// ============================
// Hand detection
// ============================
bool isHandDetected() {
  return digitalRead(TAKE_IR_PIN) == LOW;
}

// ============================
// Wait for patient to take pill
// ============================
bool waitForHandToTakePill(unsigned long timeout = 60000) {
  unsigned long start = millis();

  showWaitingTakeScreen();

  while (millis() - start < timeout) {
    if (isHandDetected()) {
      delay(300);

      if (isHandDetected()) {
        Serial.println(F("TAKEN"));
        showTakenScreen();
        delay(2000);
        return true;
      }
    }

    delay(50);
  }

  Serial.println(F("MISSED"));
  showMissedScreen();
  delay(2000);
  return false;
}

// ============================
// Schedule functions
// ============================
void addSchedule(int h, int m, int s) {
  if (scheduleCount < MAX_SLOTS) {
    scheduleHours[scheduleCount] = h;
    scheduleMinutes[scheduleCount] = m;
    scheduleSlots[scheduleCount] = s;
    scheduleCount++;

    Serial.print(F("ADDED "));
    Serial.print(h);
    Serial.print(F(":"));
    if (m < 10) Serial.print(F("0"));
    Serial.print(m);
    Serial.print(F(" SLOT "));
    Serial.println(s);
  } else {
    Serial.println(F("ERROR: Schedule Full"));
  }
}

void clearSchedules() {
  scheduleCount = 0;
  lastMoveHour = -1;
  lastMoveMinute = -1;
  Serial.println(F("CLEARED"));
}

void listSchedules() {
  Serial.print(F("COUNT "));
  Serial.println(scheduleCount);

  for (int i = 0; i < scheduleCount; i++) {
    Serial.print(F("ITEM "));
    Serial.print(i);
    Serial.print(F(" "));
    Serial.print(scheduleHours[i]);
    Serial.print(F(":"));
    if (scheduleMinutes[i] < 10) Serial.print(F("0"));
    Serial.print(scheduleMinutes[i]);
    Serial.print(F(" SLOT "));
    Serial.println(scheduleSlots[i]);
  }
}

// ============================
// Dose cycle
// ============================
void executeDoseCycle(int targetSlot) {
  Serial.println(F("DISPENSE_START"));
  showDispensingScreen();

  closeDoor();
  moveToSlot(targetSlot);
  openDoor();

  Serial.println(F("Please take medicine..."));

  bool taken = waitForHandToTakePill(60000);

  closeDoor();

  if (taken) {
    Serial.println(F("DOSE_CONFIRMED"));
  } else {
    Serial.println(F("DOSE_NOT_TAKEN"));
  }
}

void executeMoveOnly(int targetSlot) {
  Serial.println(F("MOVE_ONLY"));

  closeDoor();
  moveToSlot(targetSlot);

  Serial.println(F("ARRIVED"));
}

// ============================
// Backup mode RTC check
// ============================
void runBackupScheduleCheck() {
  DateTime now = rtc.now();

  for (int i = 0; i < scheduleCount; i++) {
    if (now.hour() == scheduleHours[i] && now.minute() == scheduleMinutes[i]) {
      if (now.hour() != lastMoveHour || now.minute() != lastMoveMinute) {
        executeDoseCycle(scheduleSlots[i]);
        lastMoveHour = now.hour();
        lastMoveMinute = now.minute();
      }
    }
  }
}

// ============================
// Trim serial command
// ============================
void trimCommand(char *cmd) {
  char *start = cmd;

  while (*start == ' ' || *start == '\t') start++;

  if (start != cmd) {
    memmove(cmd, start, strlen(start) + 1);
  }

  int len = strlen(cmd);

  while (len > 0 && (cmd[len - 1] == ' ' || cmd[len - 1] == '\t')) {
    cmd[len - 1] = '\0';
    len--;
  }
}

// ============================
// Serial command parser
// ============================
void handleSerialCommand(char *cmd) {
  trimCommand(cmd);

  if (strcmp(cmd, "PING") == 0) {
    lastHeartbeat = millis();

    if (currentMode != MODE_PRIMARY) {
      currentMode = MODE_PRIMARY;
      Serial.println(F("MODE PRIMARY"));
    }

    Serial.println(F("PONG"));
    return;
  }

  if (strcmp(cmd, "STATUS") == 0) {
    Serial.print(F("STATUS "));
    Serial.print(currentMode == MODE_PRIMARY ? F("PRIMARY ") : F("BACKUP "));
    Serial.print(F("SLOT "));
    Serial.print(currentSlot);
    Serial.print(F(" COUNT "));
    Serial.println(scheduleCount);
    return;
  }

  if (strcmp(cmd, "HEALTH_CHECK") == 0) {
    runHealthCheck();
    return;
  }

  if (strcmp(cmd, "HOME") == 0) {
    goToHome();
    return;
  }

  if (strcmp(cmd, "TEST") == 0) {
    executeDoseCycle((currentSlot + 1) % MAX_SLOTS);
    return;
  }

  if (strcmp(cmd, "DISPENSE") == 0) {
    executeDoseCycle((currentSlot + 1) % MAX_SLOTS);
    return;
  }

  if (strcmp(cmd, "CLEAR") == 0) {
    clearSchedules();
    return;
  }

  if (strcmp(cmd, "LIST") == 0) {
    listSchedules();
    return;
  }

  if (strcmp(cmd, "SAVE") == 0) {
    saveSchedulesToEEPROM();
    return;
  }

  if (strcmp(cmd, "SET_MODE PRIMARY") == 0) {
    currentMode = MODE_PRIMARY;
    Serial.println(F("MODE PRIMARY"));
    return;
  }

  if (strcmp(cmd, "SET_MODE BACKUP") == 0) {
    currentMode = MODE_BACKUP;
    Serial.println(F("MODE BACKUP"));
    return;
  }

  if (strncmp(cmd, "ADD ", 4) == 0) {
    int h, m, s;

    if (sscanf(cmd, "ADD %d %d %d", &h, &m, &s) == 3) {
      if (h >= 0 && h <= 23 && m >= 0 && m <= 59 && s >= 0 && s < MAX_SLOTS) {
        addSchedule(h, m, s);
      } else {
        Serial.println(F("ERROR: Invalid ADD values"));
      }
    } else {
      Serial.println(F("ERROR: Bad ADD format"));
    }

    return;
  }

  if (strncmp(cmd, "DISPENSE_SLOT ", 14) == 0) {
    int slot;

    if (sscanf(cmd, "DISPENSE_SLOT %d", &slot) == 1 && slot >= 0 && slot < MAX_SLOTS) {
      executeDoseCycle(slot);
    } else {
      Serial.println(F("ERROR: Invalid slot"));
    }

    return;
  }

  if (strncmp(cmd, "MOVE_SLOT ", 10) == 0) {
    int slot;

    if (sscanf(cmd, "MOVE_SLOT %d", &slot) == 1 && slot >= 0 && slot < MAX_SLOTS) {
      executeMoveOnly(slot);
    } else {
      Serial.println(F("ERROR: Invalid slot"));
    }

    return;
  }

  Serial.print(F("UNKNOWN "));
  Serial.println(cmd);
}

// ============================
// Serial line reader
// ============================
void readSerialLines() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      serialBuffer[serialIndex] = '\0';

      if (serialIndex > 0) {
        handleSerialCommand(serialBuffer);
      }

      serialIndex = 0;
    }
    else if (c != '\r') {
      if (serialIndex < sizeof(serialBuffer) - 1) {
        serialBuffer[serialIndex++] = c;
      } else {
        serialIndex = 0;
        Serial.println(F("ERROR: CMD TOO LONG"));
      }
    }
  }
}

// ============================
// Setup
// ============================
void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, LOW);

  digitalWrite(STEP_PIN, LOW);
  digitalWrite(DIR_PIN, BACKWARD);

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(HOME_IR_PIN, INPUT);
  pinMode(TAKE_IR_PIN, INPUT);

  Serial.begin(9600);
  delay(1000);

  int lcdStatus = lcd.begin(16, 4);

  if (lcdStatus) {
    Serial.print(F("LCD_ERROR "));
    Serial.println(lcdStatus);
    while (1);
  }

  lcd.backlight();
  lcd.clear();
  showStartupScreen();

  if (!rtc.begin()) {
    Serial.println(F("RTC_ERROR"));
    showRtcErrorScreen();
    while (1);
  }

  initHealthSensors();
  initKeypad();

  doorServo.attach(SERVO_PIN);
  closeDoor();

  delay(300);
  doorServo.write(DOOR_CLOSED);
  delay(500);
  // rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));

  loadSchedulesFromEEPROM();

  goToHome();

  lastHeartbeat = millis();

  Serial.println(F("READY"));
}

// ============================
// Loop
// ============================
void loop() {
  readSerialLines();

  checkKeypad();

  if (millis() - lastHeartbeat > HEARTBEAT_TIMEOUT) {
    if (currentMode != MODE_BACKUP) {
      currentMode = MODE_BACKUP;
      Serial.println(F("MODE BACKUP"));
    }
  }

  if (currentMode == MODE_BACKUP) {
    runBackupScheduleCheck();
  }

  updateIdleLCD();

  delay(50);
}