# Nobody Home - build spec

Entry for the element14 Community 2026 Halloween Hackathon. Deadline 23:59 UK time, Sunday 15 November 2026.

A doll head on a shelf. It never moves while someone is in the room. When WiFi CSI says the room has gone quiet, it slowly turns its head. Each absence it turns a bit further, and it remembers. The last turn ends with it staring into the Home Assistant camera.

The twist: CSI sees motion, not people. Sit perfectly still and it decides the room is empty. It will turn toward you.

This document is the brief for building the firmware and the PC tooling. Scope is CSI and movement only. Screen, IMU and Home Assistant come after the core works, and are listed at the end so the code leaves room for them.

\---

## 1\. Hardware

Reused from Micro\_Arcade (https://github.com/apn201/Micro\_Arcade): the same M5Stack AtomS3R.

|Part|Notes|
|-|-|
|M5Stack AtomS3R|ESP32-S3, 8 MB flash, 8 MB PSRAM, 128x128 display, IMU (BMI270), button under the screen|
|SG90 micro servo|Signal from a GPIO, power from 5V. Never powered from a GPIO pin.|
|1000 uF electrolytic cap, 10V+|Across servo 5V and GND, close to the servo. Prevents brownout resets during WiFi TX + servo current spikes.|
|Grove cable (cut) or Grove-to-Dupont|Grove port carries 5V, GND and signal in one plug|
|5V 2A USB supply||
|Doll head, base, hot glue|Mechanics, not code|

Fallback motor: 28BYJ-48 stepper + ULN2003 board (4 GPIOs). Keep the motion module behind an interface so either works.

Wiring (verify against the M5 AtomS3R pinout before soldering, do not trust this table blindly):

|Servo wire|Atom|
|-|-|
|Brown / black|GND|
|Red|5V (Grove red)|
|Orange / yellow (signal)|Grove signal pin (G2 expected, confirm)|

Cap across red and brown at the servo end, minus leg to GND.

\---

## 2\. What to reuse from Micro\_Arcade and what not

Reuse:

* The device itself, and its known quirks.
* Lesson from NOTES.md: WiFi modem sleep must be disabled, or the radio naps. For CSI this matters even more, since a napping radio means missing frames. `WiFi.setSleep(false)` on boot.
* The gitignored secrets pattern (`config.py` there, `secrets.h` here).
* The split of "device sends readings" plus a Python tool on the PC for logging and tests. Same style: Python 3, numpy, a test harness, a viewer.
* The UDP header layout style (magic byte, type, session) for telemetry.

Do not reuse:

* The MicroPython client. UIFlow2 MicroPython does not expose the ESP-IDF CSI callback. This firmware must be C++ (Arduino framework on PlatformIO). That is a hard constraint, not a preference.
* The frame streaming protocol. Not needed.

Design difference worth stating in the write-up: Micro\_Arcade's device sends readings, not decisions. Nobody Home decides locally. The prop has to work with the PC off. The PC is only a recorder.

\---

## 3\. Toolchain

* PlatformIO, Arduino framework (arduino-esp32 3.x).
* Libraries: M5Unified (display, button, IMU), nothing else required. Servo PWM through LEDC directly, no servo library.
* Board: AtomS3R. If there is no exact PlatformIO board definition, use `m5stack-atoms3` or a generic `esp32-s3-devkitc-1` with 8 MB flash and PSRAM settings, and let M5Unified detect the board at runtime.
* CSI must be enabled in the WiFi driver (`CONFIG\_ESP\_WIFI\_CSI\_ENABLED`). Check the prebuilt arduino-esp32 libs have it on. If `esp\_wifi\_set\_csi()` returns an error, switch to pioarduino with a custom sdkconfig. Find this out in phase 1, not later.

Sketch of `platformio.ini` (adjust board and versions):

```ini
\[env:atoms3r]
platform = espressif32
board = m5stack-atoms3
framework = arduino
monitor\_speed = 115200
build\_flags =
  -DARDUINO\_USB\_CDC\_ON\_BOOT=1
  -DBOARD\_HAS\_PSRAM
lib\_deps =
  m5stack/M5Unified
```

\---

## 4\. Repository layout

New repo, `Nobody\_Home`, GPL-2.0 like Micro\_Arcade.

```
firmware/
  platformio.ini
  include/
    config.h          tunables, pins, thresholds
    secrets.example.h WiFi SSID/pass, PC IP for telemetry
  src/
    main.cpp          setup, loop, wiring of modules
    csi.cpp/.h        CSI capture, feature extraction, rate monitor
    traffic.cpp/.h    ping generator to the router
    detector.cpp/.h   stillness state machine
    motion.cpp/.h     servo (or stepper) with easing, detach, limits
    store.cpp/.h      NVS: angle, calibration, (later) diary
    telemetry.cpp/.h  UDP telemetry to the PC
    ui.cpp/.h         screen (phase 6), stub until then
tools/
  logger.py           receives telemetry, writes CSV
  plot.py             plots a CSV: feature, thresholds, state, turns
  csi\_rate.py         reads the rate test output, reports gaps
  tests/              replay a CSV through a Python copy of the detector
docs/
  NOTES.md            what broke and why, written as we go
README.md
```

`secrets.h` is gitignored.

\---

## 5\. Build phases

Each phase has a gate. Do not start the next one until the gate passes.

### Phase 1 - CSI bring-up and rate test (the gate for everything)

Goal: prove that CSI callbacks arrive steadily in a quiet room on this house's router.

* Connect to WiFi in STA mode. `WiFi.setSleep(false)`.
* Enable CSI: `esp\_wifi\_set\_csi\_config()` with LLTF on, then `esp\_wifi\_set\_csi\_rx\_cb()`, then `esp\_wifi\_set\_csi(true)`.
* In the callback, accept only frames whose source MAC equals the AP's BSSID. Drop everything else.
* Traffic: start an ICMP ping session to the gateway using the ESP-IDF ping component (`ping/ping\_sock.h`), interval 10 ms (100 Hz) target, infinite count. This is the same approach as Espressif's esp-csi `csi\_recv\_router` example. The replies are the frames we measure.
* Keep the callback tiny. Copy the I/Q buffer into a ring buffer and return. All maths in a task, not in the callback.
* Print once per second over serial: callbacks/s, longest gap in ms, RSSI, channel.

Gate: 10 minutes in an empty room. Median rate at least 50/s, no gap longer than 500 ms. Record the numbers in docs/NOTES.md. If it fails, fix the traffic source first (try 20 ms interval, UDP to the gateway, check router power saving, check channel). Nothing else gets built on a broken signal.

### Phase 2 - Feature extraction and logging

* For each accepted frame, compute amplitude per subcarrier from the int8 I/Q pairs: `sqrt(i\*i + q\*q)`. Skip guard and null subcarriers.
* Per-frame feature: standard deviation of amplitudes across the used subcarriers (spatial turbulence, as in ESPectre).
* Motion metric: moving variance of that feature over a window of about 1.5 s (`MOTION\_WINDOW\_MS`).
* Telemetry at 10 Hz over UDP to the PC (format below).
* `tools/logger.py` writes CSV with a wall-clock timestamp and a free-text label column set from the keyboard (type a label, it tags rows from then on).

Record five baselines, two minutes each, labelled:

1. empty room
2. one person walking
3. one person sitting still
4. one person sitting still, breathing normally, maybe scrolling a phone
5. pet in the room, if available

Gate: `plot.py` shows clear separation between 1 and 2. Expect 3 to sit close to 1. That overlap is the feature, not a bug. Save the plots for the write-up.

### Phase 3 - Calibration and stillness state machine

Calibration:

* Hold the button 5 s to start. Screen or serial counts down 30 s (time to leave), then records 60 s of the motion metric.
* Store baseline mean and standard deviation in NVS.
* `LOW = mean + K\_LOW \* std`, `HIGH = mean + K\_HIGH \* std`. Start with K\_LOW 3, K\_HIGH 6, tune from the phase 2 data.

States:

|State|Meaning|Exit|
|-|-|-|
|STALE|CSI rate below `MIN\_RATE` for more than 2 s|Rate recovers -> ACTIVE|
|ACTIVE|Someone moving|Metric below LOW continuously -> QUIET\_PENDING|
|QUIET\_PENDING|Quiet, counting|Metric above HIGH -> ACTIVE. Quiet for `T\_EMPTY` -> EMPTY|
|EMPTY|Room judged empty|If armed and cooldown passed -> TURNING. Else stay. Metric above HIGH -> ACTIVE|
|TURNING|Servo moving|Move done -> SETTLING|
|SETTLING|Ignore CSI for `T\_SETTLE`, the head itself is motion near the antenna|Timer -> EMPTY, disarmed|

Rules:

* Boot into ACTIVE and disarmed. Whoever just plugged it in is in the room.
* One turn per absence. After a turn, re-arm only after the metric has been above HIGH for at least `T\_REARM` (someone came back and moved).
* `T\_COOLDOWN` minimum time between turns.
* STALE never turns. Missing data must never be read as an empty room. Fail safe means fail still.
* Hysteresis is the two thresholds. Do not add a third.

Starting values in config.h:

```cpp
#define MOTION\_WINDOW\_MS   1500
#define MIN\_RATE           20      // callbacks per second
#define T\_EMPTY\_MS         25000
#define T\_SETTLE\_MS        5000
#define T\_REARM\_MS         3000
#define T\_COOLDOWN\_MS      60000
#define K\_LOW              3.0f
#define K\_HIGH             6.0f
```

* Write the detector so it can also run in Python against a recorded CSV (`tools/tests/`). Same logic, same constants. That way tuning happens on replayed data, not by walking in and out of the room 200 times.

Gate: replay the phase 2 CSVs. Zero turns while someone walks. Turns after `T\_EMPTY` in the empty segments. A turn during the still-sitting segment is expected and wanted.

### Phase 4 - Motion

* LEDC, 50 Hz, 14-bit resolution, pulse 500 to 2500 us mapped to 0 to 180 degrees. Confirm the real range of the bought servo and clamp with `SERVO\_MIN\_DEG` / `SERVO\_MAX\_DEG` so it never drives into its stops.
* Eased motion: cosine or smoothstep from current to target, about 1 degree per 50 ms. A 30 degree turn takes about 1.5 to 2 s plus easing. Make the speed a constant, `DEG\_PER\_STEP` and `STEP\_MS`.
* Attach PWM only while moving. After the move, hold the last pulse for 300 ms, then stop the signal. No hum at rest.
* Cumulative turn: `ANGLE\_START`, `ANGLE\_STEP` (30), `ANGLE\_END` (faces the camera). At `ANGLE\_END` it stays there forever until reset.
* Angle saved to NVS after each completed move. On boot, it does not move to the saved angle. It assumes the head is still where it was left. No boot twitch, ever.
* Button long press 2 s: move slowly back to `ANGLE\_START`, clear stored angle. This is the reset between takes.
* Motion behind an interface (`moveTo(deg)`, `isBusy()`, `release()`) so the 28BYJ-48 can replace the servo.

Gate: on the bench, with power from the real 5V supply and WiFi active, 50 cycles of start-to-end-to-reset with no Atom reset and no audible hum at rest.

### Phase 5 - Real room

* Mount the head, place the doll so people walk across the line between it and the router.
* Run an evening with the logger on. Count false turns and missed turns. Tune constants.
* Test the money shot: sit perfectly still in view of the camera, wait, it turns toward you.
* Keep every CSV and every camera clip. The write-up is the plot next to the footage.

Gate: a full night with no turn while someone is moving in the room.

\---

## 6\. Telemetry format

UDP to `PC\_IP:20003`, little-endian, 10 Hz. Header style borrowed from Micro\_Arcade.

```
header     magic 0x4E ('N') u8 | type u8 | session u16
TELEMETRY  0x01  seq u32 | uptime\_ms u32 | rate u16 | metric f32 | low f32 | high f32
                 state u8 | armed u8 | quiet\_ms u32 | angle i16 | rssi i8
EVENT      0x02  seq u32 | uptime\_ms u32 | code u8 | angle i16
```

Event codes: 1 boot, 2 calibration done, 3 turn started, 4 turn done, 5 reset, 6 stale, 7 rearmed. Later: 8 lifted, 9 put down.

Telemetry is fire-and-forget. If the PC is off, nothing changes on the device.

\---

## 7\. Later phases (do not build yet, leave room)

Phase 6 - Screen. Debug page: state, metric bar with LOW and HIGH marks, callbacks/s, quiet seconds, angle. Short press cycles pages. Then the diary page: last 16 events with local time (NTP, Europe/Helsinki), stored in NVS. "02:47 turned to the window." Screen off by default in the final prop.

Phase 7 - IMU lift. Lift detected from accelerometer deviation and gyro: servo released immediately, motion blocked, screen wakes showing the diary. Put down and still for 3 s: screen off, detector quiet timer reset so it does not turn the moment a hand leaves.

Phase 8 - Home Assistant. On turn done, POST to an HA webhook. HA does the rest: TV off via Flic Hub IR, a light changes in another room, maybe one breath from a speaker. Order: head first, house reacts after a few seconds. Device never waits for HA and never depends on it.

\---

## 8\. Known gotchas

* Brownout: servo current plus WiFi TX resets the Atom. The cap is not optional.
* The head is motion. Moving the doll near the antenna disturbs CSI. That is what SETTLING is for.
* No traffic, no CSI. If ping stops, rate drops, state goes STALE, nothing moves. Correct behaviour.
* Router channel changes and router reboots shift the baseline. Recalibrate after either.
* Pets are motion. A cat can keep it awake, or wake it up. Document, do not hide.
* Do not let anything in the callback allocate, log or block.
* Boot must never move the servo.

## 9\. Write-up evidence to collect along the way

* Phase 1 rate numbers.
* Phase 2 baseline plots, especially sitting still versus empty.
* Detector replay results.
* Camera clips of turns with timestamps that match telemetry events.
* The still-sitting test, on camera.
* docs/NOTES.md, honestly, including what failed.

