#include <Wire.h>
#include <I2CKeyPad.h>

#define KEYPAD_ADDR 0x20

I2CKeyPad keyPad(KEYPAD_ADDR);
char keyMap[19] = "D#0*C987B654A321NF";

void setup() {
  Serial.begin(9600);
  Wire.begin();

  if (!keyPad.begin()) {
    Serial.println("Keypad not found. Check wiring/address.");
    while (1);
  }

  keyPad.loadKeyMap(keyMap);

  Serial.println("Keypad Test Started");
}

void loop() {
  if (keyPad.isPressed()) {
    char key = keyPad.getChar();

    if (key != 'N' && key != 'F' && key != 0) {
      Serial.print("Pressed: ");
      Serial.println(key);
    }

    while (keyPad.isPressed()) {
      delay(20);
    }

    delay(150);
  }
}