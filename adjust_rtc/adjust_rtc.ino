#include <Wire.h>
#include <RTClib.h>

RTC_DS3231 rtc;

void setup() {
  Serial.begin(9600);
  Wire.begin();

  if (!rtc.begin()) {
    Serial.println("RTC NOT FOUND");
    while (1);
  }

  if (rtc.lostPower()) {
    Serial.println("RTC LOST POWER!");
    // لا تعملي adjust هون
  } else {
    Serial.println("RTC power OK");
  }
}

void loop() {
  DateTime now = rtc.now();

  Serial.print(now.year());
  Serial.print("/");
  Serial.print(now.month());
  Serial.print("/");
  Serial.print(now.day());
  Serial.print("  ");

  Serial.print(now.hour());
  Serial.print(":");
  Serial.print(now.minute());
  Serial.print(":");
  Serial.println(now.second());

  delay(1000);
}