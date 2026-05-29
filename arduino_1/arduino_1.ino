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
// Pins
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
// Health Sensors
#define TEMP_PIN 2
#define PULSE_PIN A1

#define HEART_MEASURE_TIME     15000UL
#define HEART_CALIBRATION_TIME  2000UL
#define HEART_MIN_INTERVAL       350
#define HEART_MAX_INTERVAL      2000
#define HEART_MIN_INTERVALS        3

Servo doorServo;

#define DOOR_CLOSED 140
#define DOOR_OPEN    40
// Modes
#define MODE_PRIMARY 1
#define MODE_BACKUP  2

RTC_DS3231 rtc;
hd44780_I2Cexp lcd(0x27);
// Health objects
OneWire oneWire(TEMP_PIN);
DallasTemperature tempSensor(&oneWire);
// Keypad
#define KEYPAD_ADDR 0x20

I2CKeyPad keyPad(KEYPAD_ADDR);

bool keypadReady = false;
unsigned long lastKeypadTime = 0;

char keypadMap[17] = "147*2580369#ABCD";
// Health Menu State
bool healthMenuActive = false;
unsigned long healthMenuStart = 0;
const unsigned long HEALTH_MENU_TIMEOUT = 15000UL;
// State
int currentMode = MODE_PRIMARY;
unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_TIMEOUT = 30000;

int stepDelay =1800 ;
int currentSlot = 0;
int lastMoveHour = -1;
int lastMoveMinute = -1;

byte scheduleHours[MAX_SLOTS];
byte scheduleMinutes[MAX_SLOTS];
byte scheduleSlots[MAX_SLOTS];
int scheduleCount = 0;

// EEPROM layout
const int  EEPROM_MAGIC_ADDR = 0;
const byte EEPROM_MAGIC      = 0x42;
const int  EEPROM_COUNT_ADDR = 1;
const int  EEPROM_DATA_ADDR  = 2;

// LCD state
unsigned long lastLcdUpdate = 0;
unsigned long lcdHoldUntil = 0;
// Serial buffer
char serialBuffer[64];
byte serialIndex = 0;
char lcdBuf[17];
// Function prototypes
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
void showHealthMenu();
void processHealthMenuKey(char key);
void measureTemperatureOnly();
void measureHeartRateOnly();
void holdLCD(unsigned long durationMs);
void holdLCDLong();
void releaseLCDHold();

// LCD UI state screens
void lcdSystemReadyScreen();
void lcdPiOfflineScreen();
void lcdRefillStartScreen();
void lcdWaitRFIDScreen();
void lcdRFIDOkScreen();
void lcdRFIDDeniedScreen();
void lcdMovingToFillSlot(int slot);
void lcdFillSlotScreen(int slot);
void lcdFillSlotMedicineScreen(int slot, const char *medicine);
void lcdQRScanningScreen();
void lcdQROkScreen();
void lcdQRWrongScreen();
void lcdQRRequiredScreen();
void lcdSlotLoadedScreen();
void lcdSlotSkippedScreen();
void lcdRefillFinishScreen();
void lcdRefillDoneScreen();
void lcdSOSAlertScreen();
void lcdSOSSentScreen();
void lcdCameraErrorScreen();
void lcdHomeErrorScreen();
// LCD helpers
void printLineChar(uint8_t row, const char *text) {
  lcd.setCursor(0, row);
  byte len = strlen(text);
  for (byte i = 0; i < 16; i++) {
    lcd.print(i < len ? text[i] : ' ');
  }
}
void printLineF(uint8_t row, const __FlashStringHelper *fsh) {
  lcd.setCursor(0, row);
  PGM_P p = reinterpret_cast<PGM_P>(fsh);
  byte i = 0;
  while (i < 16) {
    char c = pgm_read_byte(p++);
    if (!c) break;
    lcd.print(c);
    i++;
  }
  while (i++ < 16) lcd.print(' ');
}
void showScreen(const char *l1, const char *l2,
                const char *l3, const char *l4) {
  printLineChar(0, l1);
  printLineChar(1, l2);
  printLineChar(2, l3);
  printLineChar(3, l4);
}
void showScreenF(const __FlashStringHelper *l1,
                 const __FlashStringHelper *l2,
                 const __FlashStringHelper *l3,
                 const __FlashStringHelper *l4) {
  printLineF(0, l1);
  printLineF(1, l2);
  printLineF(2, l3);
  printLineF(3, l4);
}
void showScreenMixed(const char *l1,
                     const __FlashStringHelper *l2,
                     const __FlashStringHelper *l3,
                     const __FlashStringHelper *l4) {
  printLineChar(0, l1);
  printLineF(1, l2);
  printLineF(2, l3);
  printLineF(3, l4);
}
// Static screens (all Flash)
void showStartupScreen() {
  showScreenF(F("CARE BOX+ Sys"),
              F("Initializing..."),
              F("Loading modules"),
              F("Please wait"));
}

void showHomingScreen() {
  showScreenF(F("CARE BOX+ Sys"),
              F("Homing tray..."),
              F("Finding marker"),
              F("Please wait"));
}

void showRtcErrorScreen() {
  showScreenF(F("System error"),
              F("RTC not found"),
              F("Check wiring"),
              F("Restart device"));
}
// LCD hold control
// Keeps temporary state screens visible before returning to Idle.
void holdLCD(unsigned long durationMs) {
  lcdHoldUntil = millis() + durationMs;
}

void holdLCDLong() {
  lcdHoldUntil = millis() + 60000UL;
}

void releaseLCDHold() {
  lcdHoldUntil = 0;
  lastLcdUpdate = 0;
}
// Dynamic screens (line1 = time from lcdBuf)
static void fillTimeLine() {
  DateTime now = rtc.now();
  snprintf(lcdBuf, sizeof(lcdBuf), "Time: %02d:%02d",
           now.hour(), now.minute());
}

void showDispensingScreen() {
  fillTimeLine();
  showScreenMixed(lcdBuf,
                  F("Dispensing dose"),
                  F("Rotating tray.."),
                  F("Please wait"));
}

void showWaitingTakeScreen() {
  fillTimeLine();
  showScreenMixed(lcdBuf,
                  F("Medicine ready"),
                  F("Take your pill"),
                  F("Sensor waiting"));
}

void showTakenScreen() {
  fillTimeLine();
  showScreenMixed(lcdBuf,
                  F("Dose taken"),
                  F("Confirmed by IR"),
                  F("Thank you"));
}

void showMissedScreen() {
  fillTimeLine();
  showScreenMixed(lcdBuf,
                  F("Dose missed"),
                  F("No hand detect"),
                  F("Check patient"));
}
// CareBox+ LCD UI state screens
// These screens can be called locally or by Raspberry Pi serial commands.
void lcdSystemReadyScreen() {
  showScreenF(F("CARE BOX+"),
              F("System Ready"),
              F("Waiting..."),
              F("Caregiver mode"));
}

void lcdPiOfflineScreen() {
  showScreenF(F("Pi Offline"),
              F("Backup mode"),
              F("RTC active"),
              F("CareBox+"));
}

void lcdRefillStartScreen() {
  showScreenF(F("Refill Mode"),
              F("Preparing..."),
              F("Please wait"),
              F("Scan RFID"));
}

void lcdWaitRFIDScreen() {
  showScreenF(F("RFID Required"),
              F("Scan caregiver"),
              F("card to open"),
              F("the lid"));
}

void lcdRFIDOkScreen() {
  showScreenF(F("RFID Accepted"),
              F("Lid unlocked"),
              F("Starting refill"),
              F("Please wait"));
}

void lcdRFIDDeniedScreen() {
  showScreenF(F("RFID Denied"),
              F("Access rejected"),
              F("Try again"),
              F("or cancel"));
}

void lcdMovingToFillSlot(int slot) {
  printLineF(0, F("Moving Tray"));
  snprintf(lcdBuf, sizeof(lcdBuf), "To Slot:%2d", slot);
  printLineChar(1, lcdBuf);
  printLineF(2, F("Please wait"));
  printLineF(3, F("Refill mode"));
}

void lcdFillSlotScreen(int slot) {
  snprintf(lcdBuf, sizeof(lcdBuf), "Fill Slot %2d", slot);
  printLineChar(0, lcdBuf);
  printLineF(1, F("Place medicine"));
  printLineF(2, F("Then scan QR"));
  printLineF(3, F("Press *"));
}
void lcdFillSlotMedicineScreen(int slot, const char *medicine) {
  snprintf(lcdBuf, sizeof(lcdBuf), "Fill Slot %2d", slot);
  printLineChar(0, lcdBuf);

  printLineChar(1, medicine);

  printLineF(2, F("Scan QR"));
  printLineF(3, F("Then press #"));
}

void lcdQRScanningScreen() {
  showScreenF(F("QR Scanning"),
              F("Show medicine"),
              F("code to camera"),
              F("Please wait"));
}

void lcdQROkScreen() {
  showScreenF(F("QR Verified"),
              F("Medicine OK"),
              F("Press # to"),
              F("confirm slot"));
}

void lcdQRWrongScreen() {
  showScreenF(F("Wrong Medicine"),
              F("Check medicine"),
              F("Scan again"),
              F("Press *"));
}

void lcdQRRequiredScreen() {
  showScreenF(F("QR Required"),
              F("Scan medicine"),
              F("first"),
              F("Press *"));
}

void lcdSlotLoadedScreen() {
  showScreenF(F("Slot Loaded"),
              F("Saved"),
              F("Moving next"),
              F("Please wait"));
}

void lcdSlotSkippedScreen() {
  showScreenF(F("Slot Skipped"),
              F("Moving to next"),
              F("refill item"),
              F("Please wait"));
}

void lcdRefillFinishScreen() {
  showScreenF(F("Finishing"),
              F("Locking lid"),
              F("Sync schedules"),
              F("Please wait"));
}

void lcdRefillDoneScreen() {
  showScreenF(F("Refill Done"),
              F("Loaded doses"),
              F("synced"),
              F("System Ready"));
}

void lcdSOSAlertScreen() {
  showScreenF(F("SOS ALERT"),
              F("Emergency"),
              F("Calling"),
              F("caregiver"));
}

void lcdSOSSentScreen() {
  showScreenF(F("SOS Sent"),
              F("Caregiver"),
              F("notified"),
              F("Stay calm"));
}

void lcdCameraErrorScreen() {
  showScreenF(F("QR Error"),
              F("Camera issue"),
              F("Try again"),
              F("or cancel"));
}

void lcdHomeErrorScreen() {
  showScreenF(F("Tray Error"),
              F("Home failed"),
              F("Check sensor"),
              F("Restart"));
}
// Health functions
void initHealthSensors() {
  pinMode(PULSE_PIN, INPUT);
  tempSensor.begin();
  Serial.println(F("HEALTH_READY"));
}

void showHealthMenu() {
  healthMenuActive = true;
  healthMenuStart = millis();
  showScreenF(F("Health Menu"),
              F("1 Temp"),
              F("2 Heart BPM"),
              F("D Cancel"));
  Serial.println(F("HEALTH_MENU"));
}

void processHealthMenuKey(char key) {
  if (key == '1') {
    healthMenuActive = false;
    Serial.println(F("KEY_TEMP_CHECK"));
    measureTemperatureOnly();
  }
  else if (key == '2') {
    healthMenuActive = false;
    Serial.println(F("KEY_HEART_CHECK"));
    measureHeartRateOnly();
  }
  else if (key == 'D' || key == '*') {
    healthMenuActive = false;
    Serial.println(F("HEALTH_CANCELLED"));
    showScreenF(F("Health Check"),
                F("Cancelled"),
                F("Returning..."),
                F("Please wait"));
    delay(1200);
  }
  else {
    healthMenuStart = millis();
    showScreenF(F("Health Menu"),
                F("1 Temp"),
                F("2 Heart BPM"),
                F("D Cancel"));
  }
}

void measureTemperatureOnly() {
for (int sec = 3; sec > 0; sec--) {
  printLineF(0, F("Temp Check"));
  printLineF(1, F("Prepare sensor"));

  snprintf(lcdBuf, sizeof(lcdBuf), "Reading in %d", sec);
  printLineChar(2, lcdBuf);

  printLineF(3, F("Please wait"));
  delay(1000);
}

showScreenF(F("Temp Check"),
            F("Reading..."),
            F("Please wait"),
            F(""));

float sum = 0;
int count = 0;

for (int sec = 3; sec > 0; sec--) {
  printLineF(0, F("Temp Check"));
  printLineF(1, F("Measuring..."));

  snprintf(lcdBuf, sizeof(lcdBuf), "Please wait %d", sec);
  printLineChar(2, lcdBuf);

  printLineF(3, F("Hold sensor"));

  tempSensor.requestTemperatures();
  float t = tempSensor.getTempCByIndex(0);

  if (t != DEVICE_DISCONNECTED_C && t > -100) {
    sum += t;
    count++;
  }

  delay(1000);
}

float tempC;
if (count > 0) {
  tempC = sum / count;
} else {
  tempC = DEVICE_DISCONNECTED_C;
}

  const char *status;
  if (tempC == DEVICE_DISCONNECTED_C || tempC < -100) {
    status = "ERR";
  } else if (tempC >= 38.0) {
    status = "ALERT";
  } else {
    status = "NORMAL";
  }
  if (tempC == DEVICE_DISCONNECTED_C || tempC < -100) {
    snprintf(lcdBuf, sizeof(lcdBuf), "Temp: ERROR");
  } else {
    char tmp[7];
    dtostrf(tempC, 4, 1, tmp);
    snprintf(lcdBuf, sizeof(lcdBuf), "Temp:%s C", tmp);
  }
  printLineF(0, F("Temp Result"));
  printLineChar(1, lcdBuf);
  snprintf(lcdBuf, sizeof(lcdBuf), "Status:%s", status);
  printLineChar(2, lcdBuf);
  printLineF(3, F("CareBox+"));

if (tempC == DEVICE_DISCONNECTED_C || tempC < -100) {
  Serial.println(F("HEALTH_TEMP_ERROR"));
} else {
  Serial.print(F("HEALTH_TEMP "));
  Serial.println(tempC, 1);

  Serial.print(F("HEALTH_TEMP_STATUS "));
  Serial.println(status);
}

  delay(10000);
}

void measureHeartRateOnly() {
  showScreenF(F("Heart Check"),
              F("Place finger"),
              F("Hold still"),
              F("15 seconds"));
  delay(1000);
  unsigned long calibrationStart = millis();
  int calMin = 1023, calMax = 0;
  long calSum = 0;
  int calCount = 0;

  while (millis() - calibrationStart < HEART_CALIBRATION_TIME) {
    int value = analogRead(PULSE_PIN);
    if (value < calMin) calMin = value;
    if (value > calMax) calMax = value;
    calSum += value;
    calCount++;
    delay(10);
  }

  int calAvg  = calCount > 0 ? (int)(calSum / calCount) : 0;
  int calDiff = calMax - calMin;
  int threshold  = calAvg + max(5, calDiff / 4);
  int hysteresis = 3;

  showScreenF(F("Heart Check"),
              F("Measuring BPM"),
              F("Keep still"),
              F("Please wait"));
  unsigned long start = millis();
  unsigned long lastBeatTime = 0;
  long intervalSum = 0;
  int intervalCount = 0, beatCount = 0;
  int rawMin = 1023, rawMax = 0;
  bool aboveThreshold = false;

  while (millis() - start < HEART_MEASURE_TIME) {
    int value = analogRead(PULSE_PIN);
    if (value < rawMin) rawMin = value;
    if (value > rawMax) rawMax = value;

    unsigned long now = millis();

    if (value > threshold && !aboveThreshold) {
      if (lastBeatTime == 0) {
        lastBeatTime = now;
        beatCount++;
      } else {
        unsigned long interval = now - lastBeatTime;
        if (interval >= HEART_MIN_INTERVAL && interval <= HEART_MAX_INTERVAL) {
          intervalSum += interval;
          intervalCount++;
          beatCount++;
          lastBeatTime = now;
        }
      }
      aboveThreshold = true;
    }
    if (value < threshold - hysteresis) aboveThreshold = false;

    delay(10);
  }
  int bpm = 0;
  const char *status = "WEAK_SIGNAL";

  if (intervalCount >= HEART_MIN_INTERVALS) {
    long avgInterval = intervalSum / intervalCount;
    if (avgInterval > 0) {
      bpm = (int)(60000L / avgInterval);
      if      (bpm >= 50 && bpm <= 120) status = "NORMAL";
      else if (bpm >= 40 && bpm <= 160) status = "WARNING";
      else                               status = "ALERT";
    }
  }

  // Display result
  printLineF(0, F("Heart Result"));

  if (bpm > 0) {
    snprintf(lcdBuf, sizeof(lcdBuf), "Heart:%d BPM", bpm);
    printLineChar(1, lcdBuf);
    snprintf(lcdBuf, sizeof(lcdBuf), "Status:%s", status);
    printLineChar(2, lcdBuf);
    snprintf(lcdBuf, sizeof(lcdBuf), "Beats:%d", beatCount);
    printLineChar(3, lcdBuf);
  } else {
    printLineF(1, F("Heart: Retry"));
    printLineF(2, F("Weak signal"));
    printLineF(3, F("Hold still"));
  }

if (bpm > 0) {
  Serial.print(F("HEALTH_HEART "));
  Serial.println(bpm);

  Serial.print(F("HEALTH_HEART_STATUS "));
  Serial.println(status);
} else {
  Serial.println(F("HEALTH_HEART_ERROR"));
}

  delay(10000);
}
// Keypad functions
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

  if (healthMenuActive) {
    processHealthMenuKey(key);
    return;
  }

  if      (key == 'A') Serial.println(F("KEY_START_REFILL"));
  else if (key == '#') Serial.println(F("KEY_CONFIRM_LOADED"));
  else if (key == 'B') Serial.println(F("KEY_SKIP_SLOT"));
  else if (key == 'D') Serial.println(F("KEY_FINISH_REFILL"));
  else if (key == 'C') { Serial.println(F("KEY_HEALTH_MENU")); showHealthMenu(); }
  else if (key == '*') Serial.println(F("KEY_SCAN_QR"));
}

void checkKeypad() {
  if (!keypadReady) return;

  uint8_t index = keyPad.getKey();
  if (index < 16) {
    if (millis() - lastKeypadTime < 300) return;

    handleKeypadKey(keypadMap[index]);
    lastKeypadTime = millis();

    while (keyPad.getKey() < 16) delay(20);
  }
}
// EEPROM
void saveSchedulesToEEPROM() {
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC);
  EEPROM.update(EEPROM_COUNT_ADDR, (byte)scheduleCount);

  for (int i = 0; i < scheduleCount; i++) {
    EEPROM.update(EEPROM_DATA_ADDR + i * 3,     scheduleHours[i]);
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

  scheduleCount = (int)EEPROM.read(EEPROM_COUNT_ADDR);

  if (scheduleCount < 0 || scheduleCount > MAX_SLOTS) {
    scheduleCount = 0;
    return;
  }

  for (int i = 0; i < scheduleCount; i++) {
    scheduleHours[i]   = EEPROM.read(EEPROM_DATA_ADDR + i * 3);
    scheduleMinutes[i] = EEPROM.read(EEPROM_DATA_ADDR + i * 3 + 1);
    scheduleSlots[i]   = EEPROM.read(EEPROM_DATA_ADDR + i * 3 + 2);
  }
}
// Find next dose
bool findNextDose(int &nextHour, int &nextMinute) {
  if (scheduleCount == 0) {
    nextHour = nextMinute = -1;
    return false;
  }

  DateTime now = rtc.now();
  int nowMinutes = now.hour() * 60 + now.minute();

  int bestDiff  = 100000;
  int bestIndex = -1;

  for (int i = 0; i < scheduleCount; i++) {
    int h = scheduleHours[i];
    int m = scheduleMinutes[i];

    if (h > 23 || m > 59) continue;

    if (h == lastMoveHour && m == lastMoveMinute &&
        now.hour() == h   && now.minute() == m) continue;

    int diff = (h * 60 + m) - nowMinutes;
    if (diff <= 0) diff += 24 * 60;

    if (bestIndex == -1 || diff < bestDiff) {
      bestDiff  = diff;
      bestIndex = i;
    }
  }

  if (bestIndex == -1) {
    nextHour = nextMinute = -1;
    return false;
  }

  nextHour   = scheduleHours[bestIndex];
  nextMinute = scheduleMinutes[bestIndex];
  return true;
}
void updateIdleLCD() {
  if (healthMenuActive) return;

  if (millis() < lcdHoldUntil) return;

  if (millis() - lastLcdUpdate < 1000) return;
  lastLcdUpdate = millis();

  DateTime now = rtc.now();
  snprintf(lcdBuf, sizeof(lcdBuf), "Time: %02d:%02d",
           now.hour(), now.minute());
  printLineChar(0, lcdBuf);
  printLineF(1, currentMode == MODE_PRIMARY ? F("Mode: PRIMARY") : F("Mode: BACKUP"));

  int nh = -1, nm = -1;
  if (findNextDose(nh, nm)) {
    snprintf(lcdBuf, sizeof(lcdBuf), "Next: %02d:%02d", nh, nm);
  } else {
    snprintf(lcdBuf, sizeof(lcdBuf), "Next: --:--");
  }
  printLineChar(2, lcdBuf);
printLineF(3, F("Waiting dose"));
}
// Door control
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
// Homing
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
// Movement
void moveOneSlot() {
  digitalWrite(DIR_PIN, FORWARD);
  delay(50);

  for (int i = 0; i < STEPS_PER_SLOT; i++) {
   int d = stepDelay;
  if (i < 50) {
  d = stepDelay + (50 - i) * 15;
}
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(d);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(d);
  }

  currentSlot = (currentSlot + 1) % MAX_SLOTS;
  Serial.println(F("DONE"));
}

void moveToSlot(int targetSlot) {
  int diff = (targetSlot - currentSlot + MAX_SLOTS) % MAX_SLOTS;
  Serial.print(F("Moving to slot "));
  Serial.println(targetSlot);
  for (int i = 0; i < diff; i++) moveOneSlot();
  currentSlot = targetSlot;
}
// Hand detection
bool isHandDetected() {
  return digitalRead(TAKE_IR_PIN) == LOW;
}

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
// Schedule functions
void addSchedule(int h, int m, int s) {
  if (scheduleCount < MAX_SLOTS) {
    scheduleHours[scheduleCount]   = (byte)h;
    scheduleMinutes[scheduleCount] = (byte)m;
    scheduleSlots[scheduleCount]   = (byte)s;
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
  lastMoveHour = lastMoveMinute = -1;
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
// Dose cycle
void executeDoseCycle(int targetSlot) {
   Serial.println(F("DISPENSE_START"));
    showDispensingScreen();
      closeDoor();
       moveToSlot(targetSlot);
         openDoor(); 
          delay(1200);
           closeDoor(); 
           Serial.println(F("Please take medicine...")); 
           bool taken = waitForHandToTakePill(60000); 
           Serial.println(taken ? F("DOSE_CONFIRMED") : F("DOSE_NOT_TAKEN")); }

void executeMoveOnly(int targetSlot) {
  Serial.println(F("MOVE_ONLY"));
  closeDoor();
  moveToSlot(targetSlot);
  Serial.println(F("ARRIVED"));
}
// Backup mode RTC check
void runBackupScheduleCheck() {
  DateTime now = rtc.now();
  int h = now.hour(), m = now.minute();

  for (int i = 0; i < scheduleCount; i++) {
    if (h == scheduleHours[i] && m == scheduleMinutes[i]) {
      if (h != lastMoveHour || m != lastMoveMinute) {
        executeDoseCycle(scheduleSlots[i]);
        lastMoveHour   = h;
        lastMoveMinute = m;
      }
    }
  }
}
// Trim serial command
void trimCommand(char *cmd) {
  char *start = cmd;
  while (*start == ' ' || *start == '\t') start++;
  if (start != cmd) memmove(cmd, start, strlen(start) + 1);

  int len = strlen(cmd);
  while (len > 0 && (cmd[len-1] == ' ' || cmd[len-1] == '\t')) {
    cmd[--len] = '\0';
  }
}
// Serial command parser
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
  // LCD UI serial commands
  if (strcmp(cmd, "LCD_IDLE") == 0) { releaseLCDHold(); updateIdleLCD(); return; }
  if (strcmp(cmd, "LCD_READY") == 0) { lcdSystemReadyScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_PI_OFFLINE") == 0) { lcdPiOfflineScreen(); holdLCD(8000); return; }
  if (strcmp(cmd, "LCD_REFILL_START") == 0) { lcdRefillStartScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_WAIT_RFID") == 0) { lcdWaitRFIDScreen(); holdLCDLong(); return; }
  if (strcmp(cmd, "LCD_RFID_OK") == 0) { lcdRFIDOkScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_RFID_DENIED") == 0) { lcdRFIDDeniedScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_QR_SCAN") == 0) { lcdQRScanningScreen(); holdLCDLong(); return; }
  if (strcmp(cmd, "LCD_QR_OK") == 0) { lcdQROkScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_QR_WRONG") == 0) { lcdQRWrongScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_QR_REQUIRED") == 0) { lcdQRRequiredScreen(); holdLCD(5000); return; }
  if (strcmp(cmd, "LCD_SLOT_LOADED") == 0) { lcdSlotLoadedScreen(); holdLCD(4000); return; }
  if (strcmp(cmd, "LCD_SLOT_SKIPPED") == 0) { lcdSlotSkippedScreen(); holdLCD(4000); return; }
  if (strcmp(cmd, "LCD_REFILL_FINISH") == 0) { lcdRefillFinishScreen(); holdLCD(6000); return; }
  if (strcmp(cmd, "LCD_REFILL_DONE") == 0) { lcdRefillDoneScreen(); holdLCD(6000); return; }
  if (strcmp(cmd, "LCD_SOS") == 0) { lcdSOSAlertScreen(); holdLCDLong(); return; }
  if (strcmp(cmd, "LCD_SOS_SENT") == 0) { lcdSOSSentScreen(); holdLCD(8000); return; }
  if (strcmp(cmd, "LCD_CAMERA_ERROR") == 0) { lcdCameraErrorScreen(); holdLCD(6000); return; }
  if (strcmp(cmd, "LCD_HOME_ERROR") == 0) { lcdHomeErrorScreen(); holdLCDLong(); return; }

  if (strncmp(cmd, "LCD_MOVE_SLOT ", 14) == 0) {
    int slot;
    if (sscanf(cmd, "LCD_MOVE_SLOT %d", &slot) == 1) {
      lcdMovingToFillSlot(slot);
      holdLCDLong();
    } else {
      lcdCameraErrorScreen();
      holdLCD(5000);
    }
    return;
  }

if (strncmp(cmd, "LCD_FILL_SLOT ", 14) == 0) {
  int slot;
  char medicineName[17];

  medicineName[0] = '\0';

  if (sscanf(cmd, "LCD_FILL_SLOT %d %16[^\n]", &slot, medicineName) >= 1) {
    if (medicineName[0] != '\0') {
      lcdFillSlotMedicineScreen(slot, medicineName);
    } else {
      lcdFillSlotScreen(slot);
    }

    holdLCDLong();
  } else {
    lcdCameraErrorScreen();
    holdLCD(5000);
  }

  return;
}

  if (strcmp(cmd, "HEALTH_MENU") == 0 || strcmp(cmd, "HEALTH_CHECK") == 0) {
    showHealthMenu(); return;
  }
  if (strcmp(cmd, "TEMP_CHECK")  == 0) { measureTemperatureOnly(); return; }
  if (strcmp(cmd, "HEART_CHECK") == 0) { measureHeartRateOnly();   return; }
  if (strcmp(cmd, "HOME")        == 0) { goToHome();               return; }

  if (strcmp(cmd, "TEST") == 0 || strcmp(cmd, "DISPENSE") == 0) {
    executeDoseCycle((currentSlot + 1) % MAX_SLOTS);
    return;
  }

  if (strcmp(cmd, "CLEAR") == 0) { clearSchedules();       return; }
  if (strcmp(cmd, "LIST")  == 0) { listSchedules();        return; }
  if (strcmp(cmd, "SAVE")  == 0) { saveSchedulesToEEPROM(); return; }

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
    if (sscanf(cmd, "ADD %d %d %d", &h, &m, &s) == 3 &&
        h >= 0 && h <= 23 && m >= 0 && m <= 59 &&
        s >= 0 && s < MAX_SLOTS) {
      addSchedule(h, m, s);
    } else {
      Serial.println(F("ERROR: Bad ADD"));
    }
    return;
  }

  if (strncmp(cmd, "DISPENSE_SLOT ", 14) == 0) {
    int slot;
    if (sscanf(cmd, "DISPENSE_SLOT %d", &slot) == 1 &&
        slot >= 0 && slot < MAX_SLOTS) {
      executeDoseCycle(slot);
    } else {
      Serial.println(F("ERROR: Invalid slot"));
    }
    return;
  }

  if (strncmp(cmd, "MOVE_SLOT ", 10) == 0) {
    int slot;
    if (sscanf(cmd, "MOVE_SLOT %d", &slot) == 1 &&
        slot >= 0 && slot < MAX_SLOTS) {
      executeMoveOnly(slot);
    } else {
      Serial.println(F("ERROR: Invalid slot"));
    }
    return;
  }

  Serial.print(F("UNKNOWN "));
  Serial.println(cmd);
}
// Serial line reader
void readSerialLines() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      serialBuffer[serialIndex] = '\0';
      if (serialIndex > 0) handleSerialCommand(serialBuffer);
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
void loop() {
  readSerialLines();
  checkKeypad();

  if (healthMenuActive && millis() - healthMenuStart > HEALTH_MENU_TIMEOUT) {
    healthMenuActive = false;
    Serial.println(F("HEALTH_MENU_TIMEOUT"));
  }

  if (millis() - lastHeartbeat > HEARTBEAT_TIMEOUT) {
    if (currentMode != MODE_BACKUP) {
      currentMode = MODE_BACKUP;
      Serial.println(F("MODE BACKUP"));
      lcdPiOfflineScreen();
      holdLCD(8000);
    }
  }

  if (currentMode == MODE_BACKUP) runBackupScheduleCheck();

  updateIdleLCD();
  delay(50);
}
