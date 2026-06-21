# Hardware Reference & Power Budget — Auto Chicken Coop

Researched specs for every component, how they're powered, and the key
gotchas. Read the **Power** section first — it's where the project will bite you.

---

## TL;DR — the things that matter most

1. **Three voltage domains, kept separate:**
   - **3.3V logic** (Pi GPIO, MCP3008, DHT22, PCA9685 *VCC*) — from the Pi.
   - **5–6V servo power** (PCA9685 shield *V+*, MG995 servos) — from a buck converter.
   - **12V power** (linear actuator via L298N, fan, LED strips via relays) — from the 12V PSU.
2. **Never put 12V on the servo shield's V+** — your board is rated **6V max**. MG995s are 4.8–6V parts; 12V destroys them.
3. **Your 12V 2A adapter is undersized for the full build.** It's fine for bench-testing a servo or two (bucked to 5–6V). It is **not** enough to run the linear actuator (3–6A at 12V) — the parts list calls for a **12V/5A** supply.
4. **Best practice: power the Pi 5 from its own official 5V/5A USB-C supply**, and use the 12V PSU only for actuator/fan/lights/servos. This avoids the Pi 5 under-voltage problem (below).

---

## Voltage domains diagram

```
                 ┌─────────────── 3.3V logic (from Pi) ───────────────┐
 Raspberry Pi ───┼─ PCA9685 VCC   ─ MCP3008 VDD/VREF ─ DHT22 ─ GPIO    │
                 └─────────────────────────────────────────────────────┘

 12V PSU ──┬─ L298N +12V ─ linear actuator (door)
           ├─ Fan relay COM ─ 12V fan
           ├─ Light relay COM ×2 ─ 12V LED strips
           └─ Buck converter (12V → 5–6V) ──┬─ PCA9685 V+ (servo power)
                                            └─ MG995 servos

 ALL grounds common (Pi GND ↔ PSU − ↔ buck − ↔ shield GND).
```

---

## Component specs

### Raspberry Pi 5 (controller)
- Wants a **5.1V / 5A (25W) USB-C PD** supply for full performance.
- If it doesn't detect a 5A PD supply at boot, it **caps total USB current to ~600mA** (1.6A with the official supply). ([Raspberry Pi / Pi Hut](https://support.thepihut.com/hc/en-us/articles/13852538984221-Which-power-supply-do-I-need-for-my-Raspberry-Pi-5))
- **Gotcha:** powering the Pi 5 from a buck converter through the 5V GPIO pins bypasses PD negotiation — the Pi can't tell how much current is available and may throw **under-voltage warnings or random reboots** under load. Prefer the official USB-C supply for the Pi.
- Pi 5 uses the **RP1 GPIO chip** → `RPi.GPIO` does not work; the code uses **lgpio**.

### Adafruit 16-Channel 12-bit PWM/Servo Shield (PCA9685)
- **VCC (logic):** 3–5V (chip rated 2.3–5.5V). Fed from the Pi's **3.3V**. 5V-compliant, so 3.3V logic + 3.3V I2C pull-ups work fine.
- **V+ (servo/LED power):** **5–6V** for servos. *Your board's silkscreen says "V+ : 6V Max" — respect that* (the generic PCA9685 breakout tolerates up to ~12V on V+, but this shield does not).
- **I2C address:** **0x40** default (all A0–A5 jumpers open). Up to 62 boards chainable.
- **Output:** 12-bit (4096 steps), 40–1000Hz; servos run at **~60Hz**.
- ([Adafruit pinouts](https://learn.adafruit.com/16-channel-pwm-servo-driver/pinouts), [product page](https://www.adafruit.com/product/1411))

### MG995 metal-gear servo ×2 (vents)
- **Operating voltage:** **4.8–7.2V** (use 5–6V here).
- **Stall torque:** ~9.4 kg·cm @4.8V, ~11 kg·cm @6V.
- **Current:** idle ~10mA, no-load running ~170mA, **stall ~1.2A**.
- **Speed:** ~0.2 s/60° @4.8V, 0.16 s/60° @6V.
- Signal works at 3.3V logic even though the servo is powered at 5–6V.
- ([components101](https://components101.com/motors/mg995-servo-motor), [TowerPro datasheet](https://www.electronicoscaldas.com/datasheet/MG995_Tower-Pro.pdf))

### L298N dual H-bridge (door actuator driver)
- **Motor supply:** 5–35V (your 12V).
- **Up to 2A continuous per channel.**
- **Voltage drop across the bridge: ~2V at 1A, ~4V at 2A** — so a 12V actuator only sees ~8–10V through the L298N. Factor this into actuator speed/force.
- Onboard **78M05** regulator makes 5V (≤0.5A) **only if input >7V**; don't feed its logic from >12V.
- Logic inputs are **5V** TTL. The Pi's 3.3V on IN1/IN2 usually works but is marginal — if the driver misbehaves, that's why.
- ([lastminuteengineers](https://lastminuteengineers.com/l298n-dc-stepper-driver-arduino-tutorial/))
- **Note:** the L298N is inefficient for a 12V actuator. A **BTS7960** or a simple relay-reversing setup is a common upgrade, but the L298N is fine to start.

### 12V linear actuator (door)
- **Current:** no-load ~0.5–1A, **full load 3–6A** at 12V; ~5A max pushing hard.
- **Stroke:** typically 4–24" (match to door travel).
- **Cycle time:** ~10–30s; ~0.5–1.5 in/s.
- This is the **single biggest load** in the system and the reason you need a beefy 12V supply.
- ([Firgelli guide](https://www.firgelliauto.com/blogs/industrial-farming/the-ultimate-diy-automated-chicken-coop-door-guide))

### SONGLE SLA-05VDC-SL-C relay ×4 (fan + 2 lights, spare)
- **Coil: 5V**, ~**70–90mA** per relay when energized (direct-drive board, active-HIGH).
- **Contacts: up to 30A @250VAC / 30A** — massively overrated for 12V LED/fan loads, which is fine.
- ([Songle SLA datasheet](https://files.seeedstudio.com/wiki/Grove-SPDT_Relay_30A/res/SLA-05VDC-SL-C_Datasheet.pdf))

### MCP3008 ADC (LDR + food pot)
- **VDD/VREF: 2.7–5.5V** — tie both to the Pi's **3.3V** so a reading of 1023 = 3.3V.
- SPI: CLK→SCLK, DOUT→MISO, DIN→MOSI, CS→CE0.
- Negligible current (sub-mA).
- ([Things DAQ](https://thingsdaq.org/2022/01/24/mcp3008-with-raspberry-pi/))

### DHT22 / AM2302 (temp + humidity)
- **Voltage: 3.3–5.5V** (works on the Pi's 3.3V).
- **Current:** ~0.3–1.5mA measuring, ~60µA standby. Negligible.
- 10kΩ pull-up on the data line. ~0.5Hz max sample rate (read every ≥2s — your `POLL_INTERVAL` of 10s is safe).
- ([components101](https://components101.com/sensors/dht22-pinout-specs-datasheet))

### Float switches ×3, LDR, indicator LEDs
- **Float switches:** simple NO contacts to 3.3V, pull GPIO high when triggered. No power draw.
- **LDR:** in a voltage divider to MCP3008 CH0. Bright → ~1.0, dark → ~0.0.
- **LEDs:** ~20mA each through 220Ω; ~5 LEDs ≈ 0.1A total off the 3.3V/GPIO.

---

## Power budget

### 5–6V rail (buck converter output)
| Load | Typical | Peak |
|------|---------|------|
| 2× MG995 servos (moving → stall) | ~0.4A | **~2.4A** |
| PCA9685 logic | <0.01A | 0.01A |
| (relays/LEDs if run off 5V) | ~0.4A | 0.4A |
| **5V subtotal** | ~0.8A | **~2.8A (~16W)** |

### 12V rail (PSU)
| Load | Typical | Peak |
|------|---------|------|
| Linear actuator (while moving) | ~1.5A | **~5A** |
| 12V fan | ~0.3A | 0.5A |
| 12V LED strips ×2 | ~1–2A | 3A |
| Buck input (to make the 5V above) | ~1A | ~1.8A |
| **12V subtotal** | ~4A | **~10A (~120W peak)** |

### What this means for your supplies
- **Your 12V 2A (24W) adapter:** OK for **bench-testing servos** (buck → 5–6V, one or two MG995s). **Not enough** for the actuator or the full system.
- **For the real build:** the **12V/5A (60W)** in the parts list is the minimum, and even that assumes the actuator and LED strips don't peak together. A **12V/8–10A** supply gives comfortable headroom.
- **Recommended split:** Pi 5 on its **own official 5V/5A USB-C** supply; the 12V PSU drives everything else. Cleanest, avoids Pi under-voltage, and isolates the noisy motor loads from the Pi.

---

## Bench-test now (with what you have)

To move a servo today with the 12V 2A adapter:
1. **12V 2A → buck converter input.** Set the buck output to **5–6V** (verify with a multimeter *before* connecting anything).
2. Buck **OUT+ → shield V+**, buck **OUT− → shield GND and Pi GND** (common ground).
3. Shield **VCC → Pi 3.3V**, **SDA → GPIO2**, **SCL → GPIO3**, **GND → Pi GND**.
4. Servo into **channel 0**.
5. `sudo i2cdetect -y 1` → expect **0x40**.
6. `sudo GPIOZERO_PIN_FACTORY=lgpio python3 debug_panel.py` → Vents Open/Close moves it.

Do **not** connect the 12V adapter to the actuator yet — 2A isn't enough and it may stall/brown out.

---

## Sources
- MG995: [components101](https://components101.com/motors/mg995-servo-motor), [TowerPro datasheet (PDF)](https://www.electronicoscaldas.com/datasheet/MG995_Tower-Pro.pdf)
- PCA9685 shield: [Adafruit pinouts](https://learn.adafruit.com/16-channel-pwm-servo-driver/pinouts), [Adafruit product 1411](https://www.adafruit.com/product/1411)
- SONGLE relay: [SLA-05VDC-SL-C datasheet (PDF)](https://files.seeedstudio.com/wiki/Grove-SPDT_Relay_30A/res/SLA-05VDC-SL-C_Datasheet.pdf)
- L298N: [lastminuteengineers](https://lastminuteengineers.com/l298n-dc-stepper-driver-arduino-tutorial/), [BYU quick-start (PDF)](https://brightspotcdn.byu.edu/cd/87/bbf866d84c06a0c52fa995396f30/l298n-motor-driver-quick-start-v6.pdf)
- MCP3008: [Things DAQ](https://thingsdaq.org/2022/01/24/mcp3008-with-raspberry-pi/)
- DHT22: [components101](https://components101.com/sensors/dht22-pinout-specs-datasheet), [Adafruit AM2302 datasheet (PDF)](https://cdn-shop.adafruit.com/datasheets/Digital+humidity+and+temperature+sensor+AM2302.pdf)
- Linear actuator: [Firgelli DIY guide](https://www.firgelliauto.com/blogs/industrial-farming/the-ultimate-diy-automated-chicken-coop-door-guide)
- Raspberry Pi 5 power: [The Pi Hut](https://support.thepihut.com/hc/en-us/articles/13852538984221-Which-power-supply-do-I-need-for-my-Raspberry-Pi-5), [bret.dk](https://bret.dk/how-to-power-the-raspberry-pi-5-a-complete-guide/)
