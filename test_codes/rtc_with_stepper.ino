#include <Wire.h>
#include "RTClib.h"

#define STEP_PIN 3
#define DIR_PIN 4
#define STEPS_PER_SLOT 160

RTC_DS3231 rtc;

int stepDelay = 800;

int lastMoveHour = -1;
int lastMoveMinute = -1;

void moveOneSlot() {
  for (int i = 0; i < STEPS_PER_SLOT; i++) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(stepDelay);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(stepDelay);
  }
  Serial.println("Moved one slot!");
}
char command;
void setup() {
  Serial.begin(9600);

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  digitalWrite(STEP_PIN, LOW);  
  digitalWrite(DIR_PIN, HIGH);

   if (!rtc.begin()) {
    Serial.println("RTC not found");
    while (1);
  } 
  rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
}

void loop() {
   DateTime now = rtc.now();
  Serial.print("Time: ");
  Serial.print(now.hour());
  Serial.print(":");
  Serial.print(now.minute());
  Serial.print(":");
  Serial.println(now.second());
  if (now.hour() == 13&& now.minute() ==26) {
    if (now.hour() != lastMoveHour || now.minute() != lastMoveMinute) {
      moveOneSlot();
      lastMoveHour = now.hour();
      lastMoveMinute = now.minute();
    } 
  } 
}

