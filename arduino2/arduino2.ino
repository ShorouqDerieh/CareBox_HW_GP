#include <SPI.h>
#include <MFRC522.h>
// RFID + Lock + SOS Pins
#define RFID_SS_PIN 10
#define RFID_RST_PIN 9

#define LOCK_PIN 5
#define SOS_BUTTON_PIN 2
// RGB Relay Pins
#define RED_RELAY_PIN   6   // relay المنفصلة
#define GREEN_RELAY_PIN 3   // K1
#define BLUE_RELAY_PIN  4   // K2
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
byte allowedUID[4] = {0x24, 0x57, 0x94, 0x72};
bool lidUnlocked = false;
char serialBuffer[40];
byte serialIndex = 0;
// RGB / Light Functions
void setOff() {
  digitalWrite(RED_RELAY_PIN, RELAY_OFF);
  digitalWrite(GREEN_RELAY_PIN, RELAY_OFF);
  digitalWrite(BLUE_RELAY_PIN, RELAY_OFF);
}

void setRed() {
  digitalWrite(RED_RELAY_PIN, RELAY_ON);
  digitalWrite(GREEN_RELAY_PIN, RELAY_OFF);
  digitalWrite(BLUE_RELAY_PIN, RELAY_OFF);
}

void setGreen() {
  digitalWrite(RED_RELAY_PIN, RELAY_OFF);
  digitalWrite(GREEN_RELAY_PIN, RELAY_ON);
  digitalWrite(BLUE_RELAY_PIN, RELAY_OFF);
}

void setBlue() {
  digitalWrite(RED_RELAY_PIN, RELAY_OFF);
  digitalWrite(GREEN_RELAY_PIN, RELAY_OFF);
  digitalWrite(BLUE_RELAY_PIN, RELAY_ON);
}

void setYellow() {
  digitalWrite(RED_RELAY_PIN, RELAY_ON);
  digitalWrite(GREEN_RELAY_PIN, RELAY_ON);
  digitalWrite(BLUE_RELAY_PIN, RELAY_OFF);
}

void setPurple() {
  digitalWrite(RED_RELAY_PIN, RELAY_ON);
  digitalWrite(GREEN_RELAY_PIN, RELAY_OFF);
  digitalWrite(BLUE_RELAY_PIN, RELAY_ON);
}

void setCyan() {
  digitalWrite(RED_RELAY_PIN, RELAY_OFF);
  digitalWrite(GREEN_RELAY_PIN, RELAY_ON);
  digitalWrite(BLUE_RELAY_PIN, RELAY_ON);
}

void setWhite() {
  digitalWrite(RED_RELAY_PIN, RELAY_ON);
  digitalWrite(GREEN_RELAY_PIN, RELAY_ON);
  digitalWrite(BLUE_RELAY_PIN, RELAY_ON);
}

void blinkRed(int times, int delayMs) {
  for (int i = 0; i < times; i++) {
    setRed();
    delay(delayMs);
    setOff();
    delay(delayMs);
  }
}
// Lock Functions
void unlockLid() {
  Serial.println("TRY_UNLOCK_PIN_HIGH");

  digitalWrite(LOCK_PIN, HIGH);
  delay(50);

  Serial.print("LOCK_PIN_STATE ");
  Serial.println(digitalRead(LOCK_PIN));

  lidUnlocked = true;

  setBlue();
  Serial.println("LID_UNLOCKED");
}

void lockLid() {
  digitalWrite(LOCK_PIN, LOW);
  lidUnlocked = false;

  setGreen(); 
  Serial.println("LID_LOCKED");
}

// RFID Functions
bool isAllowedUID(byte *uid, byte size) {
  if (size != 4) return false;

  for (byte i = 0; i < 4; i++) {
    if (uid[i] != allowedUID[i]) return false;
  }

  return true;
}

void printUID() {
  Serial.print("UID ");

  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
    Serial.print(rfid.uid.uidByte[i], HEX);

    if (i < rfid.uid.size - 1) {
      Serial.print(" ");
    }
  }

  Serial.println();
}

void checkRFID() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  printUID();

  if (isAllowedUID(rfid.uid.uidByte, rfid.uid.size)) {
    Serial.println("RFID_OK");
    setBlue();
    unlockLid();
  } else {
    Serial.println("RFID_DENIED");
    blinkRed(3, 200);
    setGreen();
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  delay(1000);
}

// SOS Function
void checkSOS() {
  static bool sosPressedBefore = false;
  static unsigned long lastSosTime = 0;

  bool pressed = (digitalRead(SOS_BUTTON_PIN) == LOW);

  if (pressed && !sosPressedBefore) {
    delay(50);

    if (digitalRead(SOS_BUTTON_PIN) == LOW) {
      unsigned long now = millis();

      if (now - lastSosTime > 5000) {
        Serial.println("SOS");
        blinkRed(6, 150);
        setRed();

        lastSosTime = now;
      }

      sosPressedBefore = true;
    }
  }

  if (!pressed) {
    sosPressedBefore = false;
  }
}
// Serial Commands
void handleCommand(char *cmd) {
  // Lock commands
  if (strcmp(cmd, "LOCK") == 0) {
    lockLid();
    return;
  }

  if (strcmp(cmd, "UNLOCK") == 0) {
    unlockLid();
    return;
  }

  if (strcmp(cmd, "STATUS") == 0) {
    Serial.print("SECURITY_STATUS ");
    Serial.println(lidUnlocked ? "UNLOCKED" : "LOCKED");
    return;
  }

  if (strcmp(cmd, "PING") == 0) {
    Serial.println("SECURITY_PONG");
    return;
  }
  if (strcmp(cmd, "LED_OFF") == 0) {
    setOff();
    Serial.println("LED_OFF_OK");
    return;
  }

  if (strcmp(cmd, "LED_RED") == 0) {
    setRed();
    Serial.println("LED_RED_OK");
    return;
  }

  if (strcmp(cmd, "LED_GREEN") == 0) {
    setGreen();
    Serial.println("LED_GREEN_OK");
    return;
  }

  if (strcmp(cmd, "LED_BLUE") == 0) {
    setBlue();
    Serial.println("LED_BLUE_OK");
    return;
  }

  if (strcmp(cmd, "LED_YELLOW") == 0) {
    setYellow();
    Serial.println("LED_YELLOW_OK");
    return;
  }

  if (strcmp(cmd, "LED_PURPLE") == 0) {
    setPurple();
    Serial.println("LED_PURPLE_OK");
    return;
  }

  if (strcmp(cmd, "LED_CYAN") == 0) {
    setCyan();
    Serial.println("LED_CYAN_OK");
    return;
  }

  if (strcmp(cmd, "LED_WHITE") == 0) {
    setWhite();
    Serial.println("LED_WHITE_OK");
    return;
  }

  if (strcmp(cmd, "LED_SOS") == 0) {
    blinkRed(6, 150);
    setRed();
    Serial.println("LED_SOS_OK");
    return;
  }

  Serial.print("SECURITY_UNKNOWN ");
  Serial.println(cmd);
}

void readSerialLines() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      serialBuffer[serialIndex] = '\0';

      if (serialIndex > 0) {
        handleCommand(serialBuffer);
      }

      serialIndex = 0;
    }
    else if (c != '\r') {
      if (serialIndex < sizeof(serialBuffer) - 1) {
        serialBuffer[serialIndex++] = c;
      } else {
        serialIndex = 0;
        Serial.println("SECURITY_ERROR_CMD_TOO_LONG");
      }
    }
  }
}
void setup() {
  Serial.begin(9600);

  pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);

  pinMode(LOCK_PIN, OUTPUT);

  pinMode(RED_RELAY_PIN, OUTPUT);
  pinMode(GREEN_RELAY_PIN, OUTPUT);
  pinMode(BLUE_RELAY_PIN, OUTPUT);
  setOff();

  lockLid();

  SPI.begin();
  rfid.PCD_Init();

  delay(500);

  setGreen();
  Serial.println("SECURITY_READY");
}
void loop() {
  readSerialLines();
  checkRFID();
  checkSOS();
}