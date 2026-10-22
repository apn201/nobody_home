# Notes

What broke and why, written as we go.

## 2026-10-19 - toolchain

* Stock PlatformIO `espressif32` is still on arduino-esp32 2.x. Using pioarduino 55.03.311, which gives arduino-esp32 3.3.11 on ESP-IDF 5.5.
* CSI is compiled into the prebuilt WiFi libs (`CONFIG_ESP_WIFI_CSI_ENABLED=y` in the esp32s3 sdkconfig). No custom sdkconfig needed. Still to confirm on the device that `esp_wifi_set_csi()` returns OK.
* PlatformIO will not install its toolchain from Git Bash (MSYS). Use PowerShell or cmd.
* The project lives in Dropbox, so `firmware/.pio` is marked Dropbox-ignored (`com.dropbox.ignored` stream). Otherwise Dropbox syncs the whole build tree.
* Board definition: `m5stack-atoms3` (8 MB flash). PSRAM is off for now.

## 2026-10-20 - backup of the original firmware

* esptool reports: ESP32-S3-PICO-1 rev v0.2, 8 MB GD flash (quad), 8 MB **quad** PSRAM (AP_3v3). So when PSRAM is turned on, the memory type is `qio_qspi`, not OPI.
* The old UIFlow firmware runs its own TinyUSB stack (PID 816B), so esptool cannot auto-reset it. Hold reset 2 s for download mode (PID 1001, came up as COM9). Once our firmware is on (USB-Serial/JTAG), uploads should auto-reset.
* `read-flash` with the stub loader died consistently in 0x400000-0x4FFFFF. `--no-stub` read it fine. Full image and restore steps are in `backup/`.

## Phase 1 - rate test

Router: Google/Nest WiFi mesh
Channel: 11
Distance Atom to router: (fill in)

| Date | Interval | Minutes | Median /s | Min /s | Longest gap | Ping lost | Queue drops | Result |
|-|-|-|-|-|-|-|-|-|
| 2026-10-20 | 10 ms | 10.5 | 100 | 95 | 85 ms | 0 | 0 | PASS |

Empty room, RSSI -60 median, no roams during the run. Raw log: `logs/rate_20261020_1336.txt`.

What broke first: the first boot after flashing accepted 0 frames. CSI arrived at the full ping rate, but every frame failed the source-MAC filter. Probably a mesh roam: the Atom ended up on another node, while the filter still held the BSSID read at boot. Fix: `csiSetBssid()` on every `ARDUINO_EVENT_WIFI_STA_CONNECTED`, plus a `ROAM` serial line. Not reproduced since, so the cause is a best guess. If cb drops to 0 with `other` high, look at `src=` on the RATE line.

Also: after the forced download mode, USB serial was silent until the Atom was unplugged and plugged back in. Uploads to COM9 now auto-reset, no button.

## 2026-10-20 - phase 2 build

* Feature: amplitude of LLTF subcarriers -26..-1 and 2..26 (51 used). Subcarrier 1 is always skipped, since the S3 can flag the first word of the buffer invalid. Skipping it every time keeps the feature consistent. Per-frame spatial std, then moving variance over `MOTION_WINDOW_MS` (time-based ring, 512 slots).
* Telemetry: 35-byte packets as in the spec, 10 Hz, checked end to end: 301 packets in 30 s, no sequence gaps.
* Bug found on the way: with nothing reading the USB serial port, every `Serial.printf` blocked for the HWCDC default 100 ms TX timeout. The main loop dropped to about 1 Hz, telemetry came out in bursts, and the 1 s rate window counted 2 s of frames (showed 200/s). The prop will run on a charger with no reader, so this would have hit for real. Fix: `Serial.setTxTimeoutMs(0)`, plus timers that resync after a stall instead of bursting.
* Bench, person at the desk, 30 s: metric median 0.53, p95 1.5. First data point only, not a baseline.

## Phase 2 - baselines

### Run 1, 2026-10-20 14:05: INVALID, labels wrong

The cues played through the PC speaker, but nobody followed them: Juha was on a phone call at the desk the whole 9.4 min. So every label is really "one person sitting, talking on the phone". Nothing here about walking or an empty room. CSV `logs/baselines_20261020_1405.csv`, plot `docs/plots/baselines_20261020_1405_raw_amplitude.png`.

Still useful, as a long "sitting, talking" sample:

* Rate 100/s throughout (one dip to 23/s).
* Metric median about 0.03-0.1, with level steps and spikes up to about 1. RSSI stepped -62 -> -69 -> -64 around 470-500 s, and the metric spiked with it. The raw int8 amplitude feature is gain-sensitive. Worth checking whether gain steps happen in a truly empty room too.

Lesson: confirm the person is in place and ready before starting a cued recording.

Next: stream raw per-frame CSI (amplitudes + rx_ctrl: sig_mode, rate, noise floor) to the PC, record again, and compare features offline: gain-normalised amplitude, per-subcarrier temporal variance, frame-to-frame correlation. Note where the router is and the walking path.
### Run 2, 2026-10-20 15:13: GATE PASS

Same setup, cues followed this time. CSV `logs/baselines_20261020_1513.csv`, plot `docs/plots/baselines_20261020_1513.png`.

| Label | Median | p95 | Rate med | RSSI med |
|-|-|-|-|-|
| walking | 0.458 | 1.10 | 100 | -63 |
| sitting-still | 0.117 | 0.20 | 100 | -63 |
| sitting-phone | 0.075 | 0.11 | 100 (min 30) | -62 |
| empty | 0.091 | 0.20 | 100 (min 0) | -65 |
| pet | - | - | | not recorded |

Walking against empty: medians 5x apart, interquartile boxes do not overlap. Sitting still and sitting with the phone land on top of empty, as expected. That overlap is the prop.

Spec thresholds from this empty segment (K_LOW 3, K_HIGH 6; dropout rows excluded): LOW 0.230, HIGH 0.353.

| Label | above HIGH | below LOW |
|-|-|-|
| walking | 65.2% | 12.7% |
| sitting-still | 0.0% | 98.4% |
| sitting-phone | 0.0% | 99.5% |
| empty | 0.0% | 99.1% |

Empty never crosses HIGH. Walking dips below LOW 13% of the time, but QUIET_PENDING needs LOW continuously for 25 s, so it should not count as empty. The phase 3 replay will show whether that holds.

CSI dropout during empty, 473-488 s: rate below 50/s for about 15 s (down to 0), while telemetry kept flowing, so WiFi stayed up and only the ping replies thinned. The metric flatlines while it lasts. The cause is not known yet (Nest busy? interference?). This is the STALE case: the detector must not read it as quiet. Also a short dip to 30/s during sitting-phone. Worth logging ping replies in telemetry if it keeps happening.

## 2026-10-20 - phase 3

Detector in `firmware/src/detector.cpp`, Python copy in `tools/detector.py`. The constants are parsed from `config.h`, so the copies cannot drift on numbers. Logic changes still have to go into both.

Decisions where the spec left room:

* ACTIVE -> QUIET_PENDING as soon as the metric drops below LOW. In QUIET_PENDING only a value above HIGH resets the timer. The band between LOW and HIGH is the hysteresis.
* Re-arm needs the metric above HIGH *continuously* for T_REARM. A cumulative count would let a night of rare spikes add up and re-arm with nobody there. Fail still.
* STALE: rate below MIN_RATE for more than `T_STALE_MS` (2 s), checked in every state except TURNING and SETTLING. Leaving STALE goes to ACTIVE, so the quiet timer starts over.
* Not calibrated: never leaves ACTIVE, never turns.
* After a calibration the detector restarts disarmed. Otherwise the person who just left to calibrate would trigger a turn straight away.
* Std floor: `CAL_MIN_STD_FRAC` x mean, so a dead-quiet calibration cannot give a hair trigger.
* Motion is a stand-in that only takes the time a real move would (30 deg at 1 deg / 50 ms = 1.5 s). No PWM.

Unit tests: 14 rule tests on synthetic data, all pass.

Replay of baseline run 2, calibrated on its own empty segment (LOW 0.230, HIGH 0.353):

| Segment (starts armed) | Turns | First turn after |
|-|-|-|
| walking | 0 | - |
| sitting-still | 1 | 25.2 s (wanted) |
| sitting-phone | 1 | 25.1 s (wanted) |
| empty | 1 | 25.1 s |

Continuous (boot disarmed): a turn at 170 s while sitting still, then the walk out during the transition re-armed it, and it turned again 25 s into the empty room. **Gate passes.** Caveat: calibrated and tested on the same recording (in-sample).

Run 1 (labels wrong, one person on a call throughout) with run 2's thresholds: never armed, so no turns in the continuous replay. Per segment, every segment turns, including the one labelled walking, since nobody walked.

On the device, uncalibrated: 20 s of telemetry, all ACTIVE, disarmed, LOW/HIGH 0. The metric read about 0.02, against the 0.11 empty mean an hour earlier. The baseline drifts, so calibrate in place, and expect to recalibrate.

## 2026-10-20 - freeze, scope, new baseline segments

Requirements from Juha after phase 3:

* The head only moves when nobody can see it. If someone is near, even outside the door, it must freeze. A still head in a new pose is creepier than one going back to zero.
* The video is shot in a different room: calibrate there.
* No pets. Test with the kids instead.
* A live oscilloscope view for the video, on real data only. Real or bust.

Done:

* Freeze mid-turn (`FREEZE_ON_MOTION`): in TURNING, metric > LOW (or > HIGH with `FREEZE_ABOVE_HIGH`) stops the head where it is. State goes to ACTIVE, the turn stays armed, event 10 `frozen`. This replaces "ignore CSI while turning" from the spec. SETTLING after a completed turn still ignores CSI. Unknown until phase 4: how much the head's own motion raises the metric. If it trips LOW, every turn freezes itself.
* Baselines: `pet` dropped, added `fidget` (seated, small movements), `hallway` (moving just outside the closed door) and `--kids`. The replay gate now requires zero turns in walking, fidget, hallway and kids.
* Raw CSI stream (UDP type 0x03, 50 Hz): latest frame's 51 subcarrier amplitudes, per-frame feature, metric. Drives `tools/scope.py`.
* Atom scope page (sprite, ~15 fps): CSI trace, motion metric with thresholds, subcarrier bars.
* 16 unit tests pass. Replay of run 2 still passes (no freezes there).

Seen on first light of the scope (`docs/plots/scope_first_light.png`): single-frame glitches (one frame much lower across all subcarriers) put a 1.5 s box step into the metric, the length of the moving window. Harmless at today's thresholds. But "freeze when someone is outside the door" needs lower thresholds, and then these glitches would block turns for nothing. Next: a Hampel/median outlier filter on the per-frame feature before the variance, tuned on `scope.py --raw` recordings.

## 2026-10-20 - live test, scope exe, ping timeout

* Live walk-in test in the lab, after button calibration (LOW 0.026, HIGH 0.038): it went to ACTIVE the moment Juha's 3-year-old stepped into the room. The scope on the Atom and on the PC both work on live data.
* Scope as `dist/NobodyHomeScope.exe` (PyInstaller, one file, about 40 MB), for a laptop in the video room without Python. `config.h` is bundled; logs go next to the exe.
* Any-PC streaming: the scope and logger broadcast a 4-byte hello (`N`, 0x10) every 2 s. The Atom streams to the last hello sender as well as to `PC_IP`, and drops it after 10 s of silence. Checked: the desktop subscribes as .195 (= PC_IP), so nothing is sent twice, and the rate stays at 100/s with a subscriber.
* Ping timeout 1000 -> 100 ms. esp_ping waits for each reply or its timeout before the next request, so every lost reply was a 1 s hole in the CSI (`gap=1004` in the serial output, rate down to 0-19/s, STALE). With 100 ms, a lossy patch (2 lost per second) still gives 75-110/s and about 200 ms gaps. The ping losses themselves come and go (third time seen). Router side, cause unknown.

## 2026-10-20 - Hampel, AP pinning, phase 4 prepared

* Calibration with the Hampel firmware (button, lab): LOW 0.0245, HIGH 0.0333. During the countdown the room reached EMPTY while armed, and calibration correctly blocked the turn. Re-armed when Juha came back.
* Unattended hour started 18:39 (`logs/unattended_20261020*.csv`, every frame). The room is not guaranteed empty (family at home). Use the device states to pick the quiet stretches.
* Phase 4 servo driver written, `SERVO_ENABLED 0` until the SG90 arrives. Both variants compile. Default travel is now 45 -> 135 deg, inside the 5-175 deg clamp; set the real angles after mounting. M5Unified external I2C probing on the Grove port is off, since the servo signal shares G1/G2.
* Not flashed yet: flashing would have cut the unattended recording.

## 2026-10-20 - unattended hour (18:39-19:39)

`logs/unattended_20261020.csv` plus `_raw.csv` (every frame, 69 MB). Family at home, so "quiet" means the device judged it quiet, not a verified empty room.

* Link: median 100/s, 11 s below 50/s in the hour, never STALE. AP pinning held (ch 11).
* One turn at 0.7 min: Juha left after re-arming it, and it turned 25 s later.
* States: ACTIVE 4%, QUIET_PENDING 43%, EMPTY 52%. Only 16 min came as unbroken quiet stretches of 2 min or more.
* 103 ACTIVE episodes: **90 weak and short** (peak < 1.5x HIGH, < 3 s), 2 strong (13x HIGH, people). Each weak one restarted the 25 s quiet timer.
* No drift: the median metric stayed at 0.012-0.016 per 5-min bin, same as the calibration mean of 0.0158. The **tails** are the problem: p99 is about 0.04, above HIGH 0.0333. The 60 s calibration's std (0.0029) does not describe an hour, and the metric is not Gaussian, so mean + 6 std is too tight.
* Upward crossings per hour: 1x HIGH 135, 1.25x 39, 1.5x 14, **2x 6**, 3x 6. The 6/h left at 2x are real events.
* Freeze at LOW would have frozen **10.9%** of turn-length windows inside EMPTY for nothing. Changed: `FREEZE_ABOVE_HIGH 1`. At HIGH, the estimate is about 5.6% per turn (135/h x 1.5 s); at 2x HIGH about 0.25%.

Next: the cued recording with the hallway segment. It is the only data that can show whether a HIGH of about 2x still catches someone outside the door. Then replace mean + K std with a robust calibration rule (longer recording, percentile-based HIGH).

## 2026-10-20 evening - video mode ("haunt")

Correction: the 18:39 unattended hour **was** an empty room (Juha confirmed). All 103 ACTIVE episodes were noise. My earlier "2 strong episodes = people" was a guess with no basis.

New brief from Juha for the video: move soon after the room empties, keep moving now and then (slow and fast), stop instantly if someone comes near. It need not be accurate, but it must look right. **A halt for nothing is harmless; a move with people in the room ruins it.**

* Thresholds: floors at LOW = 2x, HIGH = 3.5x the calibration mean. Empty hour, crossings per hour: 2x 158, 3x 21, 3.5x 9, 5x 3; nothing above 3x lasted over 1.5 s.
* Haunt mode (`HAUNT 1`): EMPTY after `T_EMPTY_MS` (now 10 s), first move at once, then every 8-35 s. Random pose 30-150 deg, 25% to the camera pose, 25% snap at 6 ms/deg, 15% twitch of 8 deg, the rest creep at 40-110 ms/deg. Planner in `firmware/src/haunt.cpp`, Python copy `plan_move()`.
* `PRESENCE_AT_LOW 1`: in haunt mode anything above LOW resets the quiet timer, leaves EMPTY and freezes a move.
* Simulation (`tools/tests/haunt_sim.py`):

| Setting | Empty hour: moves/min, false freezes | Run 2 walking moves | Run 2 sitting-still moves / 2 min |
|-|-|-|-|
| presence at HIGH | 2.3, 0 | 0 | 6 |
| presence at LOW, 2.5x | 2.3, 3 | 0 | 6 |
| presence at LOW, 2x | 2.5, 14 | 0 | 6 |
| presence at LOW, 1.6x | 2.5, 29 | 0 | 6 |
| presence at LOW, 2x, T_EMPTY 15 s | 2.0, 6 | 0 | 4 |

* Walking never gets a move. **Sitting perfectly still cannot be fixed by thresholds:** in run 2, sitting-still scores the same as the empty room. The levers left are placement (router-Atom line through where people are) and a longer quiet wait. Chosen: presence at LOW, 2x, T_EMPTY 10 s. The fidget segment of the next cued run will show what the LOW gate buys for people who are not perfectly still.

## 2026-10-20 - verified-empty recording, strong-event memory

`logs/empty_verified_20261020*.csv`: Juha calibrated by button, then went downstairs. 36.5 min logged; calibration done at 35 s; he came back at about 2095 s.

* Coming back: 67-189x the calibration mean, RSSI swinging. Unmistakable.
* Before that, unexplained clusters at 1187-1261, 1325-1362 and 1485-1540 s: long (3-18 s runs) but weak (2.6-4.0x), RSSI flat at -52. Cause unknown.
* Video-mode simulation on it found the failure that matters: from 2118 to 2141 s Juha was in the room but still (below 2x), so 10 s of quiet let a move start at 2138.9 s with him there. It froze 2.7 s later.
* Fix: strong-event memory. Above `STRONG_X_HIGH` x HIGH (about 10x the mean), someone was surely here, so wait `T_AFTER_STRONG_MS` (30 s) after the last such event before moving, on top of 10 s of quiet. Re-simulated: the move with him in the room is gone, 0 freezes. Cost: the first move after people leave comes about 30-45 s later (empty hour: 43 s, was 10 s).
* Flashed. Boot: LOW 0.0326, HIGH 0.0571 from the stored calibration with the new ratio floors.

## 2026-10-20 21:02 - cued run 3, video mode live: GATE PASS

`logs/baselines_20261020_2102.csv` + `_raw.csv` (every frame). Video mode was running live on the Atom (LOW 2x at the time). Calibration from about 1.5 h earlier (mean 0.0163). Plot: `docs/plots/baselines_20261020_2102.png`.

| Segment | median x mean | above 2.5x | what the Atom did |
|-|-|-|-|
| walking | 46 | 100% | held still |
| sitting-still | 4.1 | 100% | held still |
| sitting-phone | 3.7 | 83% | held still |
| fidget | 8.7 | 100% | held still |
| hallway (outside the door) | 75 | 100% | held still |
| empty | 1.6 | 0% | 2 moves |

**No move with anyone in or near the room.** This time sitting still was clearly visible (4x), unlike run 2 (about 1x). The geometry and placement made the difference. The hallway shows huge (75x), so someone at the door freezes it.

Weak spot: the first move came 131 s after Juha left the hallway. The empty room sat at 1.6x the stale calibration mean and kept crossing LOW (2.0x) by a hair: about 40 ACTIVE<->QUIET flips, each restarting the 10 s clock. Sweep on this run:

| LOW | moves with people | first move after leaving |
|-|-|-|
| 2.0x | 0 | 131 s |
| **2.5x** | **0** | **42 s** |
| 3.0x | 0 | 42 s |

Chosen 2.5x: the empty room never reaches it here. Re-checked on the return case (still 0 moves after Juha came back) and the empty hour (2.4 moves/min, 8 no-reason freezes/h). Flashed: LOW 0.0408, HIGH 0.0571.

Remaining 42 s = the strong-event hold (30 s after the last >10x) plus 10 s of quiet. Calibrate shortly before filming.

## 2026-10-20 - scope decision

* The video is shot in the **library area**. Place the Atom so the router-Atom line crosses the shot, and calibrate there shortly before filming.
* The spec's twist "sit perfectly still and it turns toward you" is **backburner, only if time**. Video mode is tuned the other way: never move with anyone around. If it comes back, the library would be the place to try it.

## 2026-10-21 - first real servo run, 75 min with nobody watching

SG90 wired to the Grove port, no capacitor, nothing on the horn. Signal on G2 (`SERVO_PIN 2`). Juha had to swap two wires before it moved; the Grove cable's colours may not match M5's table. Juha calibrated by button, then left the house. `logs/away_servo_20261021.csv` + `_raw.csv`; report: `py tools/tests/move_report.py logs/away_servo_20261021.csv`.

* **No reboots** in 75 min and 166 moves without the capacitor (no load on the horn). Recheck with the head mounted: the load raises the current.
* 166 moves, about 2.2/min, a mix of creeps (up to 11 s) and snaps (0.1 s). First move 10 s after calibration finished.
* **The servo's own motion barely shows in the CSI:** metric median 0.42x LOW in the 5 s before a move, max 0.48x during, 0.49x in the 2.5 s after. It does not freeze itself. Recheck with the head on, since a bigger moving mass near the antenna may show.
* 1 freeze (at 1914.9 s, angle 119) during a cluster of weak disturbances 1894-1922 s, peak 4.1x the calibration mean, cause unknown. Harmless: the head stopped mid-pose and carried on later.
* 23 short ACTIVE episodes in 75 min, all at most 5.8x, never "strong" (10x), so the 30 s strong hold never triggered. States: EMPTY 78%, TURNING 11%, SETTLING 7%, QUIET 4%, ACTIVE 0.4%.
* Link: median 100/s, 20 s below 50/s, never STALE.
* This calibration's mean is 0.0316, about 2x last night's 0.0163. Same AP; the Atom may have been placed differently. Thresholds follow the calibration, so this is fine.
