# Nobody Home

Video: https://www.youtube.com/watch?v=jTFQheh9W2k

A doll head that only turns when WiFi CSI says the room is empty. Entry for the element14 Community 2026 Halloween Hackathon. Full brief: [nobody-home-spec.md](nobody-home-spec.md).

Status: phases 1-3 gates passed (phase 3 on replayed data). Device calibration not yet run in the real room. Phase 4 (servo) next.

## Build and flash (Windows)

The firmware is C++ on PlatformIO with arduino-esp32 3.3.11 (pioarduino platform). You do not need the Arduino IDE or ESP-IDF.

### One-time setup

PlatformIO is installed as a Python package:

```
py -m pip install --user platformio pyserial numpy
```

Run PlatformIO from **PowerShell or cmd, not Git Bash**. It refuses MSYS/MinGW shells and the toolchain install breaks.

The first build downloads the compiler (about 1 GB, a few minutes). After that, builds take seconds.

### WiFi secrets

```
copy firmware\include\secrets.example.h firmware\include\secrets.h
```

Then edit `secrets.h`: SSID, password, PC IP. The file is gitignored. The ESP32-S3 only does 2.4 GHz, so use the 2.4 GHz SSID.

### Build

```
cd firmware
py -m platformio run
```

### Flash

1. Plug the AtomS3R into the PC with a USB-C **data** cable. Some cables only carry power.
2. Find the port: `py -m platformio device list`. It shows up as a USB JTAG/serial debug unit, for example `COM5`. No driver is needed on Windows 10/11.
3. Upload:

```
py -m platformio run -t upload
```

PlatformIO picks the port itself. If more than one device is connected, add `--upload-port COM5`.

**If the upload fails** with "No serial data received" or "port busy":

* Close anything holding the port: serial monitor, Arduino IDE, M5Burner, the rate tool.
* Put the Atom in download mode: press and hold the reset button on the side for about 2 s, until the green LED inside lights up. Let go and run the upload again. After the upload, press reset once to start the new firmware.

### Watch the output

```
py -m platformio device monitor
```

Ctrl+C to quit. The monitor and the upload cannot share the port, so close the monitor before uploading.

## Phase 1 rate test

Flash, put the Atom where it will live, leave the room, and run:

```
py tools\csi_rate.py --port COM5 --minutes 10
```

It saves a raw log in `logs/` and prints PASS or FAIL against the gate: median 50 callbacks/s or more, no gap longer than 500 ms. Write the numbers into [docs/NOTES.md](docs/NOTES.md).

Meanwhile the screen shows callbacks/s and the longest gap: green when that second passes the gate, orange when it does not. `FATAL` on screen means WiFi, CSI or ping failed to start, and the serial output says which.

Serial line format, one per second:

```
RATE t=12 cb=97 gap=31 rssi=-48 ch=6 ping=99 lost=0 drop=0 other=3 wifi=1
```

| key | meaning |
|-|-|
| cb | accepted CSI callbacks that second (source MAC = router) |
| gap | longest gap between accepted frames, ms |
| ping | ping replies that second |
| lost | ping timeouts |
| drop | frames lost because the processing task fell behind |
| other | CSI frames from other devices, discarded |

If the gate fails, follow the spec: `PING_INTERVAL_MS` 20 in `config.h`, check the router's power-save settings, check the channel.

## Phase 2 baselines

The Atom sends telemetry at 10 Hz over UDP to `PC_IP:20003` (set in `secrets.h`; this PC's Ethernet address). The metric is the moving variance, over 1.5 s, of the per-frame standard deviation of subcarrier amplitudes.

Record each baseline for 2 minutes with its own label:

```
py tools\logger.py --label empty --seconds 120
```

Use these labels: `empty`, `walking`, `sitting-still`, `sitting-phone`, `fidget`, `hallway`, `kids`. For `empty`, start the logger and leave. Each run writes `logs/telemetry_<time>.csv`. You can also run one long session and type a new label + Enter as you change activity.

The first time Python listens on UDP, Windows Firewall may ask. Allow it on private networks, or no packets arrive.

Plot one CSV:

```
py tools\plot.py logs\telemetry_20261020_1400.csv
```

It writes a PNG next to the CSV and prints the median and p95 of the metric per label. The gate: `empty` and `walking` clearly apart. `sitting-still` close to `empty` is expected.

## Phase 3: calibration and detector

**Calibrate** after placing the Atom, and again after a router reboot or channel change:

1. Hold the button under the screen for 5 s.
2. The screen shows `LEAVE` and a 30 s countdown. Leave the room.
3. It shows `CAL` and records the empty room for 60 s.
4. Thresholds are saved in NVS and survive power-off. A short press during the countdown cancels.

Screen afterwards: state on line 1 (`*` = armed), metric and quiet seconds on line 2. `uncal` means no calibration yet; it will never turn.

**Replay** recorded CSVs through the Python copy of the detector, which reads its constants from `config.h`:

```
py tools\tests\replay.py logs\baselines_20261020_1513.csv
py tools\tests\replay.py logs\some_night.csv --device
```

`--device` uses the thresholds the Atom logged and compares its state, tick by tick, with the Python replay.

**Unit tests**, one per rule in the spec:

```
py -m unittest discover -s tools/tests -v
```

## Live scope (real data only)

On the Atom: a short press cycles **scope -> status -> screen off**. The scope page shows the per-frame CSI value (green), the motion metric with LOW/HIGH (amber, log scale), and the amplitude of all 51 subcarriers in the latest frame (cyan bars). Every sample is a measured frame; when no frame arrives, the traces stop.

On the PC (full screen, for recording or a monitor in shot):

```
py tools\scope.py
py tools\scope.py --raw     # also keep every raw frame
```

It shows a subcarrier waterfall, the per-frame trace, the motion metric with thresholds and events, the spectrum, and a big state line ("EMPTY   turning in 7 s"). It logs telemetry to `logs/scope_<time>.csv` while it runs. It uses the same UDP port as `logger.py`, so run one or the other.

## Freeze mid-turn

If anything moves while the head is turning (metric above LOW), the head stops dead in whatever pose it has reached. It does not go back. The turn stays owed, so after the next absence it carries on from that pose. Event `frozen` (code 10). If the head's own motion trips this once the servo is in, set `FREEZE_ABOVE_HIGH 1` in `config.h`.

## Baselines (scripted)

```
py tools\baselines.py           # walking, sitting still, phone, fidget, hallway, empty (~15 min)
py tools\baselines.py --kids    # adds a kids-playing segment
```

Spoken cues play through the PC's audio output. `tools/tests/replay.py` then checks: no turn while walking, fidgeting, in the hallway or with kids; a turn in the empty room.

## Layout

```
firmware/   PlatformIO project (C++)
tools/      Python on the PC: csi_rate.py, logger.py, plot.py, telemetry.py (packet decoder)
docs/       NOTES.md, what broke and why
```

License: GPL-2.0.

## Scope on another PC (no Python)

`dist\NobodyHomeScope.exe` is the scope as one file (about 40 MB) with Python inside. Build it with:

```
powershell -ExecutionPolicy Bypass -File tools\build_scope.ps1
```

Copy it to any Windows PC on the same WiFi (the `dist` folder is in Dropbox, so a laptop with Dropbox already has it) and double-click. The first run may show:

* SmartScreen ("Windows protected your PC"): More info -> Run anyway. The exe is not signed.
* Windows Firewall: allow on private networks, or no data arrives.

Nothing needs reflashing. Every 2 s the scope broadcasts a hello on the LAN, and the Atom streams to whoever said hello (as well as to `PC_IP`) until the hellos stop for 10 s. Press F for full screen. Logs go to a `logs` folder next to the exe.

## Phase 4: servo (prepared, off until wired)

The driver is in `firmware/src/motion.cpp`. `SERVO_ENABLED 0` in `config.h` keeps the pin LOW and only keeps time. Set it to 1 once the hardware below is wired.

**Wiring**, power off and USB unplugged:

| SG90 wire | Goes to |
|-|-|
| brown / black | Grove black (GND) |
| red | Grove red (5V) |
| orange / yellow (signal) | Grove yellow (G2 expected) |

* **1000 uF cap** across red and brown, right at the servo, minus leg to brown/GND. Not optional: servo inrush plus WiFi TX resets the Atom without it.
* Check G2 against the AtomS3R pinout before soldering. If the signal ends up on G1, change `SERVO_PIN`.
* 5V 2A USB supply, not a PC port.

**Bench test** (head not on the servo yet, so a wrong angle cannot hit anything):

1. Set `SERVO_ENABLED 1`, flash. Boot must not move the servo. The serial monitor shows `head at 45 deg (servo on)`.
2. Hold the button 2-5 s: it eases slowly to `ANGLE_START`, then goes quiet. Listen: no hum at rest.
3. Find the real end stops: adjust `SERVO_MIN_DEG` / `SERVO_MAX_DEG` until it never buzzes against them.
4. Mount the head, then set `ANGLE_START` (looking away) and `ANGLE_END` (into the camera).
5. Spec gate: 50 cycles start -> end -> reset on the real 5V supply with WiFi on, no Atom reset, no hum.

Behaviour: each absence turns `ANGLE_STEP` (30 deg) with smoothstep easing at 1 deg / 50 ms. Anything moving mid-turn freezes the head in that pose. The angle is saved after every finished or frozen move, and boot trusts it and never moves. Button held 2-5 s: slow return to the start pose (1 deg / 100 ms). Held 5 s or more: calibration.

## Video mode ("haunt", `HAUNT 1`)

Once the room has been quiet for `T_EMPTY_MS` (10 s), the head moves at once, then keeps moving every 8-35 s to random poses: a slow creep, a fast snap, or a small twitch, sometimes to `CAMERA_DEG`. Anything above LOW stops it on the spot, mid-move, and it stays in that pose. It carries on 10 s after things go quiet again. A halt for no reason is harmless; a move while someone watches is not, so every trade-off leans toward stopping.

Thresholds: LOW = 2.5x and HIGH = 3.5x the empty-room mean from calibration (or mean + K std if larger).

**Placement matters more than any setting.** CSI sees motion near the line between the router and the Atom. A person sitting perfectly still off that line looks exactly like an empty room, and the head will move. Put the Atom so the router-Atom line crosses where people sit or stand in the shot, then calibrate there (button 5 s).

Check it on recordings before trusting it:

```
py tools\tests\haunt_sim.py logs\some_recording.csv --timeline
py tools\tests\haunt_sim.py logs\x.csv --set LOW_RATIO=2.5 --set T_EMPTY_MS=15000
```

**Before filming:** calibrate in place (button 5 s, leave for 90 s) shortly before the shoot. The empty room's own level drifts: 1.5 h after a calibration it sat at 1.6x the calibrated mean.
