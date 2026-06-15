# Wiring Reference — Raspberry Pi GPIO (BCM)

All pin numbers use BCM (Broadcom) numbering, which is what the code uses.
Pi GPIO is **3.3V logic**. The 12V fan, actuator, and LED strips are powered by the 12V PSU and switched via relays or the L298N — they never connect directly to Pi GPIO.

---

## Raspberry Pi 40-Pin Header Reference

```
           3V3  (1) (2)  5V
     SDA1 GPIO2 (3) (4)  5V
     SCL1 GPIO3 (5) (6)  GND
          GPIO4 (7) (8)  GPIO14  ← Food LED GREEN
           GND  (9) (10) GPIO15
         GPIO17 (11)(12) GPIO18  ← Water LED GREEN
         GPIO27 (13)(14) GND
         GPIO22 (15)(16) GPIO23
           3V3 (17)(18) GPIO24
    MOSI GPIO10 (19)(20) GND
    MISO GPIO9  (21)(22) GPIO25
    SCLK GPIO11 (23)(24) GPIO8   ← MCP3008 CE0
           GND  (25)(26) GPIO7
         GPIO0  (27)(28) GPIO1
          GPIO5 (29)(30) GND
          GPIO6 (31)(32) GPIO12  ← Servo 1 (HW PWM)
         GPIO13 (33)(34) GND     ← Servo 2 (HW PWM)
         GPIO19 (35)(36) GPIO16
         GPIO26 (37)(38) GPIO20
           GND  (39)(40) GPIO21
```

---

## Pin Assignment Summary

| GPIO (BCM) | Pi Pin | Connected To |
|-----------|--------|--------------|
| **GPIO4**  | 7  | DHT22 data line |
| **GPIO5**  | 29 | L298N IN1 (door motor forward) |
| **GPIO6**  | 31 | L298N IN2 (door motor backward) |
| **GPIO12** | 32 | Servo 1 signal (HW PWM) |
| **GPIO13** | 33 | Servo 2 signal (HW PWM) |
| **GPIO14** | 8  | Food LED GREEN |
| **GPIO16** | 36 | Door limit switch — OPEN end |
| **GPIO17** | 11 | Fan relay IN |
| **GPIO18** | 12 | Water LED GREEN (full) |
| **GPIO19** | 35 | Coop light relay IN |
| **GPIO20** | 38 | Door limit switch — CLOSED end |
| **GPIO21** | 40 | Food LED RED |
| **GPIO22** | 15 | Water float switch — LOW |
| **GPIO23** | 16 | Water float switch — MID |
| **GPIO24** | 18 | Water float switch — HIGH |
| **GPIO25** | 22 | Water LED RED (low/empty) |
| **GPIO26** | 37 | Run light relay IN |
| **GPIO27** | 13 | Water LED YELLOW (mid) |
| **GPIO8**  | 24 | MCP3008 CE0 (chip select) |
| **GPIO9**  | 21 | MCP3008 MISO |
| **GPIO10** | 19 | MCP3008 MOSI |
| **GPIO11** | 23 | MCP3008 CLK |

All GPIO inputs: add 220Ω–330Ω series resistor on LED anodes. Buttons/switches: configured with internal pull-ups in gpiozero.

---

## MCP3008 Wiring

```
MCP3008 Pin → Connect To
─────────────────────────────
VDD  (16)  → 3.3V (Pi pin 1)
VREF (15)  → 3.3V (Pi pin 1)
AGND (14)  → GND
CLK  (13)  → GPIO11 / SCLK (Pi pin 23)
DOUT (12)  → GPIO9  / MISO (Pi pin 21)
DIN  (11)  → GPIO10 / MOSI (Pi pin 19)
CS   (10)  → GPIO8  / CE0  (Pi pin 24)
DGND (9)   → GND

CH0  (1)   → LDR voltage divider output
CH1  (2)   → Potentiometer wiper (centre pin)
CH2–7      → Unused (leave floating or tie to GND)
```

---

## LDR Voltage Divider (to MCP3008 CH0)

```
3.3V ──┬──[LDR]──┬── CH0
       │         │
       │      [10kΩ]
       │         │
      GND ───────┘
```
In bright light → LDR resistance low → CH0 voltage HIGH → MCP3008 reads ~1.0
In darkness → LDR resistance high → CH0 voltage LOW → MCP3008 reads ~0.0

---

## Food Potentiometer (to MCP3008 CH1)

```
3.3V ── Left pin of pot
GND  ── Right pin of pot
CH1  ── Wiper (centre pin) of pot
```
Mount pot at the pivot point of the food lever arm.
Lever up (full hopper) → pot wiper towards 3.3V → reads ~1.0
Lever down (empty) → pot wiper towards GND → reads ~0.0

---

## DHT22

```
DHT22 Pin 1 (VCC) → 3.3V
DHT22 Pin 2 (DATA) → GPIO4 + 10kΩ pull-up to 3.3V
DHT22 Pin 3 (NC) → not connected
DHT22 Pin 4 (GND) → GND
```

---

## Servos (MG996R)

```
Servo red wire   → 5V (NOT 3.3V — use 5V rail from buck converter)
Servo brown wire → GND
Servo orange wire (signal) → GPIO12 (Servo 1) / GPIO13 (Servo 2)
```
Signal is 3.3V from Pi — MG996R accepts this fine.

---

## Fan Relay

```
Relay IN  → GPIO17
Relay VCC → 5V
Relay GND → GND
Relay NO  → 12V fan positive (+)
Relay COM → 12V PSU positive
Fan GND   → 12V PSU negative
```

---

## L298N Motor Driver (Door Actuator)

```
L298N +12V → 12V PSU positive
L298N GND  → 12V PSU negative (also tie to Pi GND)
L298N IN1  → GPIO5
L298N IN2  → GPIO6
L298N OUT1 → Actuator wire A
L298N OUT2 → Actuator wire B

(Swap OUT1/OUT2 if door moves in the wrong direction)
```

---

## Limit Switches

```
Each limit switch:
  One terminal → GPIOx (16 or 20)
  Other terminal → GND

(Code uses internal pull-up; switch closes to GND when triggered)
```

---

## Light Relay Modules (×2)

```
Relay 1 IN  → GPIO19 (coop light)
Relay 2 IN  → GPIO26 (run light)
Both VCC    → 5V
Both GND    → GND
NO terminal → 12V LED strip positive
COM terminal → 12V PSU positive
LED strip GND → 12V PSU negative
```

---

## Power Distribution

```
Mains → 12V/5A PSU
  12V rail → L298N, fan (via relay), LED strips (via relays)
  12V → Buck converter → 5V rail → Pi (via GPIO 5V pin or USB-C), servo VCC, relay VCC
  GND common across all devices
```
