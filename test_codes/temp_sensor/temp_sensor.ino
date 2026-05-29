 #include <OneWire.h>
#include <DallasTemperature.h>

#define TEMP_PIN 2

OneWire oneWire(TEMP_PIN);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(9600);
  sensors.begin();

  Serial.println("DS18B20 test started");
}

void loop() {
  sensors.requestTemperatures();

  float tempC = sensors.getTempCByIndex(0);

  Serial.print("Temperature: ");
  Serial.print(tempC);
  Serial.println(" C");

  delay(1000);
} 