/*
 * coop_arduino — servo + sensor co-processor for the Auto Chicken Coop.
 *
 * The Raspberry Pi is the brain; this Arduino drives the MG995 vent servos and
 * reads the analog/DHT sensors, reporting back over USB serial.
 *
 * Serial protocol (115200 baud, newline-terminated):
 *   Pi  -> Arduino:
 *       "S<ch> <angle>"   set servo channel <ch> (0..1) to <angle> degrees
 *       "P"               ping -> replies "PONG"
 *   Arduino -> Pi (streamed ~3x/sec):
 *       "SENS <tempC> <hum> <ldrRaw> <foodRaw>"
 *
 * Libraries: Servo (built in), DHT sensor library by Adafruit (+ Adafruit
 * Unified Sensor). Install both via the Library Manager.
 *
 * Wiring:
 *   Servo 0 (vent 1) signal -> D9     Servo 1 (vent 2) signal -> D10
 *   Servo red -> external 5-6V,  servo brown -> GND (shared with Arduino GND)
 *   DHT22 data -> D2 (10k pull-up to 5V)
 *   LDR divider -> A0            Food pot wiper -> A1
 *   Arduino USB -> Raspberry Pi
 */

#include <Servo.h>
#include <DHT.h>

#define SERVO0_PIN  9
#define SERVO1_PIN  10
#define DHT_PIN     2
#define DHT_TYPE    DHT22
#define LDR_PIN     A0
#define FOOD_PIN    A1

Servo servo0;
Servo servo1;
DHT dht(DHT_PIN, DHT_TYPE);

unsigned long lastReport = 0;
const unsigned long REPORT_MS = 300;

void setup() {
  Serial.begin(115200);
  servo0.attach(SERVO0_PIN);
  servo1.attach(SERVO1_PIN);
  dht.begin();
  // Park servos at a known angle on boot.
  servo0.write(0);
  servo1.write(0);
}

void setServo(int ch, int angle) {
  angle = constrain(angle, 0, 180);
  if (ch == 0)      servo0.write(angle);
  else if (ch == 1) servo1.write(angle);
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.charAt(0) == 'S') {
    // "S<ch> <angle>"
    int sp = line.indexOf(' ');
    if (sp > 0) {
      int ch = line.substring(1, sp).toInt();
      int angle = line.substring(sp + 1).toInt();
      setServo(ch, angle);
    }
  } else if (line.charAt(0) == 'P') {
    Serial.println("PONG");
  }
}

void report() {
  float t = dht.readTemperature();   // Celsius
  float h = dht.readHumidity();
  int ldr = analogRead(LDR_PIN);
  int food = analogRead(FOOD_PIN);

  Serial.print("SENS ");
  if (isnan(t)) Serial.print("nan"); else Serial.print(t, 1);
  Serial.print(' ');
  if (isnan(h)) Serial.print("nan"); else Serial.print(h, 1);
  Serial.print(' ');
  Serial.print(ldr);
  Serial.print(' ');
  Serial.println(food);
}

void loop() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    handleCommand(line);
  }

  unsigned long now = millis();
  if (now - lastReport >= REPORT_MS) {
    lastReport = now;
    report();
  }
}
