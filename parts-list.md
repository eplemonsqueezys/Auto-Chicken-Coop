# Automated Chicken Coop — Parts List (Raspberry Pi Edition)

---

## 🧠 Central Controller

| Qty | Part | Notes |
|-----|------|-------|
| 1 | Raspberry Pi 5 (2GB or 4GB) | Pi 5 uses RP1 GPIO chip — needs lgpio, not RPi.GPIO |
| 1 | MicroSD card, 32GB+ (Class 10 / A2) | OS storage — A2 rated card recommended for Pi 5 |
| 1 | Official Raspberry Pi 5 USB-C power supply (27W) | Pi 5 requires 5V/5A — standard Pi 4 supply is NOT enough |
| 1 | **GPIO breakout board + 40-pin ribbon cable** | Strongly recommended — you're using ~20 GPIOs; labeled breadboard pins save huge headaches. Get "Adafruit T-Cobbler Plus" or any 40-pin GPIO breakout |
| 1 | **MCP3008** 8-channel SPI ADC | Critical — Pi has NO analog inputs; needed for LDR and food potentiometer |
| 1 | Weatherproof project enclosure (IP65+) | Houses Pi + electronics |
| — | Waterproof cable glands (M12 or M16) | Feed wires into enclosure |
| — | Terminal block strips | Clean wiring |
| — | 22 AWG hookup wire, assorted colors | General wiring |
| — | Heat shrink tubing | Insulate connections |

> **Pi 5 note:** Uses a new RP1 GPIO chip. `RPi.GPIO` does NOT work — the code uses `lgpio` instead. `setup.sh` handles this automatically.

---

## ⚡ Power Supply

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 12V DC power supply, 5A | Drives actuator, fan, LED strips |
| 1 | Buck converter (12V → 5V, 3A) | Can power the Pi from the same 12V supply instead of a separate USB supply |

---

## 1. Temperature Sensor (inside coop)

| Qty | Part | Notes |
|-----|------|-------|
| 1 | DHT22 temperature & humidity sensor | Single-wire protocol; works directly with Pi GPIO |
| 1 | 10kΩ resistor | Pull-up on DHT22 data line |

---

## 2. Airflow Slider Servos (×2)

| Qty | Part | Notes |
|-----|------|-------|
| 2 | MG996R high-torque servo | Metal gear; 11 kg·cm — enough for vent sliders |
| — | Servo extension cables (30cm) | Routing flexibility |

> Pi GPIO is 3.3V signal; MG996R signal line works fine at 3.3V even though the servo itself runs on 5V.

---

## 3. PC Fan (temperature-triggered)

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 120mm PC case fan, 12V | Circulates air when temp threshold hit |
| 1 | 5V single-channel relay module | Pi GPIO triggers it |

---

## 4. Water Level Sensor + Indicator

| Qty | Part | Notes |
|-----|------|-------|
| 3 | Vertical float switches (NO — normally open) | Mount at Low / Mid / Full heights |
| 1 | Red LED | Low / empty indicator |
| 1 | Yellow LED | Mid level indicator |
| 1 | Green LED | Full indicator |
| 3 | 220Ω resistors | One per LED |
| — | Small weatherproof panel / project box | Mounts on outside of coop |

---

## 5. Automatic Chicken Door (dawn/dusk)

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 12V linear actuator, 4"–6" stroke, 50–100N | Self-locking when stopped; ideal for sliding door |
| 1 | L298N dual H-bridge motor driver module | Controls actuator direction from Pi GPIO |
| 2 | Micro limit switches (NO) | One at fully-open, one at fully-closed |
| 1 | LDR (photoresistor) + 10kΩ resistor | Voltage divider → MCP3008 CH0 for dawn/dusk sensing |

---

## 6. Automatic Lights (on timer)

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 12V warm white LED strip, 2–3m | Interior coop |
| 1 | 12V warm white LED strip, 3–5m | Run/outdoor |
| 2 | 5V single-channel relay module | One per light circuit |

---

## 7. Food Level Indicator (lever + potentiometer)

| Qty | Part | Notes |
|-----|------|-------|
| 1 | 10kΩ rotary potentiometer | Attaches at lever pivot; angle → voltage → MCP3008 CH1 |
| 1 | Red LED | "Needs food" |
| 1 | Green LED | "Food OK" |
| 2 | 220Ω resistors | One per LED |
| — | Weatherproof indicator panel | Mounts on coop exterior |

---

## Miscellaneous

| Qty | Part | Notes |
|-----|------|-------|
| — | Micro-USB or USB-C cable | Programming / SSH into Pi |
| — | Zip ties | Cable management |
| — | M3 standoffs + screws | Mount Pi inside enclosure |
| — | Silicone sealant | Weatherproof wire entries |
| 1 | CR2032 coin cell | Backup for Pi's RTC if fitted; otherwise Pi uses system clock synced via WiFi NTP |

---

## Summary

| System | Key Components |
|--------|----------------|
| Controller | Raspberry Pi 4, MCP3008 ADC |
| Power | 12V/5A PSU, buck converter |
| Temperature | DHT22 |
| Vent sliders | 2× MG996R servo |
| Fan | 120mm 12V fan, relay |
| Water level | 3× float switch, 3× LED |
| Chicken door | Linear actuator, L298N driver, 2× limit switch, LDR via MCP3008 |
| Lights | 2× LED strips, 2× relay |
| Food level | Potentiometer via MCP3008, 2× LED |

*Pi 4 → Pi Zero 2W swap is straightforward once the code runs — same GPIO layout, just solder headers on the Zero.*
