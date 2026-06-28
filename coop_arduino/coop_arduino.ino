/*
 * coop_arduino — servo + sensor co-processor for the Auto Chicken Coop.
 *
 * Hardware: Arduino Uno (R3/R4) + Adafruit 16-channel 12-bit PWM/Servo Shield
 * (PCA9685, I2C address 0x40 with all address jumpers open). The MG995 vent
 * servos plug directly into the shield's channel headers. The Raspberry Pi is
 * the brain and talks to this Arduino over USB serial.
 *
 * Serial protocol (115200 baud, newline-terminated):
 *   Pi  -> Arduino:
 *       "S<ch> <angle>"   set servo channel <ch> to <angle> degrees (0-180)
 *       "R<pin> <0|1>"    drive a digital pin LOW/HIGH (relays, e.g. fan on D7)
 *       "P"               ping -> replies "PONG"
 *   Arduino -> Pi (streamed ~3x/sec):
 *       "SENS <tempC> <hum> <ldrRaw> <foodRaw>"
 *
 * Libraries (install via Library Manager):
 *   - Adafruit PWM Servo Driver Library  (+ Adafruit BusIO dependency)
 *   - DHT sensor library by Adafruit      (+ Adafruit Unified Sensor)
 *
 * Wiring:
 *   Shield stacks on the Uno (uses the SCL/SDA pins for I2C).
 *   Vent servo 1 -> shield channel 0,   vent servo 2 -> shield channel 1
 *       (3-pin servo plugs straight onto the shield: signal / V+ / GND)
 *   Servo power: 5-6V into the shield's green "V+" screw terminal (NOT the Uno's
 *       5V — MG995 stall current would brown out the board). Max 6V on this shield.
 *   DHT22 data -> Uno D2 (10k pull-up to 5V), VCC -> 5V, GND -> GND
 *   LDR divider -> A0,   food pot wiper -> A1   (A4/A5 are used by the shield's I2C)
 *   Arduino USB -> Raspberry Pi
 */

// Set USE_DHT to 1 once a DHT22 is wired to D2 AND you've installed the
// "DHT sensor library" (+ Adafruit Unified Sensor). Leave 0 to compile with
// only the Adafruit PWM Servo Driver library — temp/humidity stream as "nan".
#define USE_DHT 0

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#if USE_DHT
#include <DHT.h>
#endif

// --- Servo shield (PCA9685) ---
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
#define SERVO_FREQ 60          // Hz — standard analog servo refresh rate

// Pulse-length counts (out of 4096) for the servo end stops. These MIRROR
// SERVOMIN / SERVOMAX in config.py on the Pi — keep the two in sync. Widen
// toward 150..600 if you want more travel; narrow if the servo strains.
#define SERVOMIN 150           // angle 0   — ~full travel low end
#define SERVOMAX 600           // angle 180 — ~full travel high end

// --- Sensors ---
#define DHT_PIN  2
#define DHT_TYPE DHT22
#define LDR_PIN  A0
#define FOOD_PIN A1
#if USE_DHT
DHT dht(DHT_PIN, DHT_TYPE);
#endif

unsigned long lastReport = 0;
const unsigned long REPORT_MS = 300;

void setup() {
  Serial.begin(115200);
  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQ);
#if USE_DHT
  dht.begin();
#endif
  // Park both vent servos closed on boot.
  setServo(0, 0);
  setServo(1, 0);
}

void setServo(int ch, int angle) {
  angle = constrain(angle, 0, 180);
  int pulse = map(angle, 0, 180, SERVOMIN, SERVOMAX);
  pwm.setPWM(ch, 0, pulse);
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
  } else if (line.charAt(0) == 'R') {
    // "R<pin> <0|1>"  -> drive a digital pin (relays: fan, etc.)
    int sp = line.indexOf(' ');
    if (sp > 0) {
      int rpin = line.substring(1, sp).toInt();
      int val  = line.substring(sp + 1).toInt();
      pinMode(rpin, OUTPUT);
      digitalWrite(rpin, val ? HIGH : LOW);
    }
  } else if (line.charAt(0) == 'P') {
    Serial.println("PONG");
  }

}

void report() {
#if USE_DHT
  float t = dht.readTemperature();   // Celsius
  float h = dht.readHumidity();
#else
  float t = NAN;                     // no DHT compiled in -> report "nan"
  float h = NAN;
#endif
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
