#define SOS_BUTTON_PIN 2

void setup() {
  Serial.begin(9600);
  pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);

  Serial.println("SOS Button Test Started");
}

void loop() {
  if (digitalRead(SOS_BUTTON_PIN) == LOW) {
    Serial.println("SOS");
    delay(500);
  }
}