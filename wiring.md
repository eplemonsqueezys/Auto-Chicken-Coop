# Wiring Reference — Raspberry Pi + PCA9685 + MCP3008

Pi GPIO is **3.3V logic**. 12V devices (fan, actuator, LED strips) are powered by the 12V PSU
and switched via relays or L298N — they never connect directly to Pi GPIO pins.

Servos are driven by the **PCA9685 board over I2C** (same board as your workshop dust collection
system). GPIO12 and GPIO13 are now free — I2C uses GPIO2/GPIO3 instead.

---

## Raspberry Pi 40-Pin Header

```
           3V3  (1) (2)  5V
   SDA1 → GPIO2 (3) (4)  5V
   SCL1 → GPIO3 (5) (6)  GND
   DHT22  GPIO4 (7) (8)  GPIO14 ← Food LED GREEN
           GND  (9) (10) GPIO15
  Fan Rly GPIO17(11)(12) GPIO18 ← Water LED GREEN
 WaterYEL GPIO27(13)(14) GND
  WaterLOW GPIO22(15)(16) GPIO23 ← WaterMID
           3V3 (17)(18) GPIO24 ← WaterHIGH
  MOSI GPIO10 (19)(20) GND
  MISO GPIO9  (21)(22) GPIO25 ← Water LED RED
  SCLK GPIO11 (23)(24) GPIO8  ← MCP3008 CE0
           GND (25)(26) GPIO7
         GPIO0  (27)(28) GPIO1
  DoorIN1 GPIO5 (29)(30) GND
  DoorIN2 GPIO6 (31)(32) GPIO12  [FREE — no longer used for servo]
         GPIO13 (33)(34) GND     [FREE — no longer used for servo]
CoopLight GPIO19(35)(36) GPIO16 ← DoorLimitOPEN
 RunLight GPIO26(37)(38) GPIO20 ← DoorLimitCLOSED
           GND (39)(40) GPIO21 ← Food LED RED
```

---

## GPIO Pin Assignment Summary

| GPIO (BCM) | Pi Pin | Connected To |
|-----------|--------|--------------|
| **GPIO2**  | 3  | PCA9685 SDA (I2C data) |
| **GPIO3**  | 5  | PCA9685 SCL (I2C clock) |
| **GPIO4**  | 7  | DHT22 data line |
| **GPIO5**  | 29 | L298N IN1 — door motor forward (open) |
| **GPIO6**  | 31 | L298N IN2 — door motor backward (close) |
| **GPIO8**  | 24 | MCP3008 CE0 chip select (SPI) |
| **GPIO9**  | 21 | MCP3008 MISO (SPI) |
| **GPIO10** | 19 | MCP3008 MOSI (SPI) |
| **GPIO11** | 23 | MCP3008 CLK (SPI) |
| **GPIO14** | 8  | Food LED GREEN |
| **GPIO16** | 36 | Door limit switch — OPEN end |
| **GPIO17** | 11 | Fan relay signal IN |
| **GPIO18** | 12 | Water LED GREEN (full) |
| **GPIO19** | 35 | Coop interior light relay IN |
| **GPIO20** | 38 | Door limit switch — CLOSED end |
| **GPIO21** | 40 | Food LED RED |
| **GPIO22** | 15 | Water float switch — LOW |
| **GPIO23** | 16 | Water float switch — MID |
| **GPIO24** | 18 | Water float switch — HIGH |
| **GPIO25** | 22 | Water LED RED (low/empty) |
| **GPIO26** | 37 | Run light relay IN |
| **GPIO27** | 13 | Water LED YELLOW (mid) |

GPIO12 and GPIO13 are now free (no longer needed for servo PWM).

---

## PCA9685 Servo Driver (I2C)

Same board as your workshop dust collection system.
Connects to the Pi via I2C — only 4 wires total.

```
PCA9685 Pin → Connect To
──────────────────────────────────────
VCC         → 5V (Pi pin 4)
GND         → GND (Pi pin 6)
SDA         → GPIO2 / SDA1 (Pi pin 3)
SCL         → GPIO3 / SCL1 (Pi pin 5)
V+          → 5V (servo power rail — from buck converter)

Servo channel assignments:
  CH0 → Vent slider servo 1 (signal wire)
  CH1 → Vent slider servo 2 (signal wire)
  CH2–15 → Available for future expansion
```

Verify it's detected after boot:  `i2cdetect -y 1`  → should show **0x40**

If you have multiple I2C devices (e.g. from your workshop system), check for address conflicts.
PCA9685 default address is 0x40; address pins A0–A5 can be soldered to change it.

---

## Servos (MG996R) via PCA9685

Each servo has 3 wires. Connect to the PCA9685 servo header for the assigned channel.

```
Servo red wire    → V+ on PCA9685 (5V servo power rail)
Servo brown wire  → GND on PCA9685
Servo orange wire → Signal pin on PCA9685 CH0 (vent 1) or CH1 (vent 2)
```

Pulse values (set in config.py — matches your workshop system):
- `SERVOMIN = 150` → vent closed
- `SERVOMAX = 325` → vent open

---

## MCP3008 Wiring (SPI analog input)

Reads the LDR (light sensor) and food level potentiometer.

```
MCP3008 Pin → Connect To
──────────────────────────────────────
VDD  (16)   → 3.3V (Pi pin 1 or 17)
VREF (15)   → 3.3V (Pi pin 1 or 17)
AGND (14)   → GND
CLK  (13)   → GPIO11 / SCLK (Pi pin 23)
DOUT (12)   → GPIO9  / MISO (Pi pin 21)
DIN  (11)   → GPIO10 / MOSI (Pi pin 19)
CS   (10)   → GPIO8  / CE0  (Pi pin 24)
DGND  (9)   → GND

CH0   (1)   → LDR voltage divider output
CH1   (2)   → Food potentiometer wiper (centre pin)
CH2–7       → Unused
```

---

## LDR Voltage Divider → MCP3008 CH0

```
3.3V ───[LDR]───┬─── CH0
                │
             [10kΩ]
                │
               GND
```

Bright light → LDR resistance drops → CH0 reads HIGH (~1.0) → dawn → door opens
Darkness     → LDR resistance rises → CH0 reads LOW  (~0.0) → dusk → door closes

---

## Food Level Potentiometer → MCP3008 CH1

```
3.3V ── Left terminal of pot
GND  ── Right terminal of pot
CH1  ── Wiper (centre terminal)
```

Mount pot at pivot point of food lever arm.
Lever up (full) → wiper near 3.3V → reads ~1.0
Lever down (empty) → wiper near GND → reads ~0.0

---

## DHT22 Temperature Sensor

```
DHT22 pin 1 (VCC)  → 3.3V
DHT22 pin 2 (DATA) → GPIO4  [+ 10kΩ pull-up resistor to 3.3V]
DHT22 pin 3 (NC)   → not connected
DHT22 pin 4 (GND)  → GND
```

---

## Fan Relay

```
Relay IN   → GPIO17
Relay VCC  → 5V
Relay GND  → GND
Relay COM  → 12V PSU +
Relay NO   → 12V fan positive
Fan GND    → 12V PSU −
```

Active LOW: Pi drives IN LOW to switch fan ON (same as your workshop relay modules).

---

## L298N Motor Driver (Linear Actuator / Door)

```
L298N +12V  → 12V PSU +
L298N GND   → 12V PSU − (also connect to Pi GND — common ground)
L298N IN1   → GPIO5
L298N IN2   → GPIO6
L298N OUT1  → Actuator wire A
L298N OUT2  → Actuator wire B
```

IN1=HIGH, IN2=LOW → motor extends → door opens
IN1=LOW, IN2=HIGH → motor retracts → door closes
Both LOW → stop (coast)

Swap OUT1/OUT2 if the door moves the wrong direction.

---

## Door Limit Switches (×2)

```
Switch A (door fully OPEN):
  Terminal 1 → GPIO16
  Terminal 2 → GND

Switch B (door fully CLOSED):
  Terminal 1 → GPIO20
  Terminal 2 → GND
```

Code uses internal pull-ups. Switch closes to GND when physically triggered → motor stops.

---

## Light Relays (×2)

```
Relay 1 IN   → GPIO19 (coop interior lights)
Relay 2 IN   → GPIO26 (run lights)
Both VCC     → 5V
Both GND     → GND
Both COM     → 12V PSU +
Relay 1 NO   → 12V LED strip A (coop)
Relay 2 NO   → 12V LED strip B (run)
Both strip − → 12V PSU −
```

---

## Water Level Float Switches (×3)

Each float switch is Normally Open — floats up when water reaches that level, closes circuit.

```
Float switch LOW:
  Terminal 1 → GPIO22
  Terminal 2 → 3.3V

Float switch MID:
  Terminal 1 → GPIO23
  Terminal 2 → 3.3V

Float switch HIGH:
  Terminal 1 → GPIO24
  Terminal 2 → 3.3V
```

Code sets pull_up=False — external pull to 3.3V lets switch drive the pin HIGH when active.

---

## Indicator LEDs (all)

All LEDs: anode (+) through a 220Ω resistor to the GPIO pin. Cathode (−) to GND.

```
Water RED    → 220Ω → GPIO25
Water YELLOW → 220Ω → GPIO27
Water GREEN  → 220Ω → GPIO18

Food RED     → 220Ω → GPIO21
Food GREEN   → 220Ω → GPIO14
```

---

## Power Distribution

```
Mains
  └─ 12V / 5A PSU
       ├─ 12V rail ──→ L298N (door actuator)
       │            ──→ Fan relay COM
       │            ──→ Coop light relay COM
       │            ──→ Run light relay COM
       │
       └─ Buck converter (12V → 5V)
            ├─ 5V rail ──→ Raspberry Pi (GPIO 5V pin 4, or USB-C)
            │           ──→ PCA9685 VCC + V+ (servo power)
            │           ──→ All relay VCC pins
            │
            └─ GND common ── Pi GND, L298N GND, PCA9685 GND, all relay GND
```

Single common GND across the entire system is essential for reliable I2C and SPI communication.
