#define RED_RELAY_PIN   6   // relay المنفصلة
#define GREEN_RELAY_PIN 3   // K1
#define BLUE_RELAY_PIN  4   // K2

// Active LOW
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

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

void setup() {
  pinMode(RED_RELAY_PIN, OUTPUT);
  pinMode(GREEN_RELAY_PIN, OUTPUT);
  pinMode(BLUE_RELAY_PIN, OUTPUT);

  setOff();
}

void loop() {
  setRed();
  delay(1500);

  setGreen();
  delay(1500);

  setBlue();
  delay(1500);

  setYellow();
  delay(1500);

  setPurple();
  delay(1500);

  setCyan();
  delay(1500);

  setWhite();
  delay(1500);

  setOff();
  delay(1500);
}