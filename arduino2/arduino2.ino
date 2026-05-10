#include <SPI.h>
#include <MFRC522.h>

#define RFID_SS_PIN 10
#define RFID_RST_PIN 9
#define LOCK_PIN 5
#define SOS_BUTTON_PIN 2
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);

// غيّري هذه القيم بعد ما تقرئي UID كرتك من Serial Monitor
byte allowedUID[4] = {0x24, 0x57, 0x94, 0x72};

bool lidUnlocked = false;

char serialBuffer[40];
byte serialIndex = 0;

void unlockLid() {
  Serial.println("TRY_UNLOCK_PIN_HIGH");
  digitalWrite(LOCK_PIN, HIGH);
  delay(50);

  Serial.print("LOCK_PIN_STATE ");
  Serial.println(digitalRead(LOCK_PIN));

  lidUnlocked = true;
  Serial.println("LID_UNLOCKED");
}

void lockLid() {
  digitalWrite(LOCK_PIN, LOW);
  lidUnlocked = false;
  Serial.println("LID_LOCKED");
}

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
    if (i < rfid.uid.size - 1) Serial.print(" ");
  }
  Serial.println();
}

void handleCommand(char *cmd) {
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
    } else if (c != '\r') {
      if (serialIndex < sizeof(serialBuffer) - 1) {
        serialBuffer[serialIndex++] = c;
      } else {
        serialIndex = 0;
        Serial.println("SECURITY_ERROR_CMD_TOO_LONG");
      }
    }
  }
}

void checkRFID() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  printUID();

  if (isAllowedUID(rfid.uid.uidByte, rfid.uid.size)) {
    Serial.println("RFID_OK");
    unlockLid();
  } else {
    Serial.println("RFID_DENIED");
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  delay(1000);
}
void checkSOS() {
  static bool sosPressedBefore = false;
  static unsigned long lastSosTime = 0;

  bool pressed = (digitalRead(SOS_BUTTON_PIN) == LOW);

  if (pressed && !sosPressedBefore) {
    delay(50); // debounce بسيط

    if (digitalRead(SOS_BUTTON_PIN) == LOW) {
      unsigned long now = millis();

      // حماية من تكرار SOS بسرعة
      if (now - lastSosTime > 5000) {
        Serial.println("SOS");
        lastSosTime = now;
      }

      sosPressedBefore = true;
    }
  }

  if (!pressed) {
    sosPressedBefore = false;
  }
}
void setup() {
  pinMode(SOS_BUTTON_PIN,INPUT_PULLUP);
  Serial.begin(9600);

  pinMode(LOCK_PIN, OUTPUT);
  lockLid();

  SPI.begin();
  rfid.PCD_Init();

  delay(500);
  Serial.println("SECURITY_READY");
}

void loop() {
  readSerialLines();
  checkRFID();
  checkSOS();
}