/* #define PULSE_PIN A1

void setup() {
  Serial.begin(9600);
  Serial.println("Pulse Sensor Test Started");
}

void loop() {
  int value = analogRead(PULSE_PIN);

  Serial.print("Pulse raw value: ");
  Serial.println(value);

  delay(50);
} */
#define PULSE_PIN A1

void setup() {
  Serial.begin(9600);
}

void loop() {
  int signal = analogRead(PULSE_PIN);
  Serial.println(signal);
  delay(20);
}