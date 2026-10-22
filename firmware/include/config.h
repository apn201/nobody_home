// Tunables, pins, thresholds
#pragma once

// --- Traffic (phase 1) ---
#define PING_INTERVAL_MS   10      // 100 Hz target. Try 20 if the router struggles.

// --- CSI (phase 1) ---
#define CSI_QUEUE_LEN      64      // frames buffered between callback and task
#define CSI_BUF_MAX        128     // LLTF only: 64 subcarriers x (I,Q)
#define HAMPEL_K           3       // outlier filter on the per-frame feature: window 2K+1, 0 = off
#define HAMPEL_SIGMA       3.0f    // replace a frame further than this many robust sigmas from the median
#define GATE_MIN_RATE      50      // phase 1 gate: median callbacks/s
#define GATE_MAX_GAP_MS    500     // phase 1 gate: longest gap

// --- Telemetry (phase 2) ---
#define TELEMETRY_MS       100     // 10 Hz UDP to PC_IP:20003
#define RAW_STREAM         1       // every CSI frame to tools/scope.py (~100/s, ~8 KB/s), 0 = off
#define SCREEN_MS          66      // scope page redraw, ~15 fps

// --- Detector (phase 3) ---
#define MOTION_WINDOW_MS   1500
#define MIN_RATE           20      // callbacks per second
#define T_STALE_MS         2000    // rate below MIN_RATE this long -> STALE
#define T_EMPTY_MS         10000   // quiet this long -> EMPTY (spec: 25000; shorter for the video)
#define T_SETTLE_MS        2000    // ignore CSI after a move: the head itself disturbs it
#define T_REARM_MS         3000
#define T_COOLDOWN_MS      60000
#define K_LOW              3.0f
#define K_HIGH             6.0f
// Floors as multiples of the empty-room mean. The empty metric has heavy
// tails, so mean + K*std alone was too tight: 158 false triggers/h at 2x mean,
// 9/h at 3.5x, none lasting over 1.5 s (verified-empty hour, NOTES). People
// walking reached 7-100x.
#define LOW_RATIO          2.5f    // 2.0 sat on the empty room's own level 1.5 h after calibration
#define HIGH_RATIO         3.5f

// --- Video mode ("haunt") ---
// 1: once the room is empty, move quickly, then keep moving now and then to
// random poses at random speeds, freezing instantly if anyone comes near.
// 0: the spec's story, one turn per absence toward the camera.
#define HAUNT              1
// Moving with someone in the room ruins the illusion; a halt for nothing does
// not. 1: in haunt mode anything above LOW counts as presence (resets the
// quiet timer, blocks moves, freezes a move). 0: only above HIGH.
#define PRESENCE_AT_LOW    1
// Someone surely came in (metric above STRONG_X_HIGH x HIGH, ~10x the empty
// mean; entering measured 67-189x, unexplained empty-room bumps at most 4x):
// then they may sit still, invisible. Wait this long after the last such
// event before moving, on top of T_EMPTY_MS of quiet.
#define STRONG_X_HIGH      3.0f
#define T_AFTER_STRONG_MS  30000
#define HAUNT_GAP_MIN_MS   8000    // pause between moves while empty
#define HAUNT_GAP_MAX_MS   35000
#define POSE_MIN_DEG       30      // random poses stay in here
#define POSE_MAX_DEG       150
#define CAMERA_DEG         135     // "stare into the camera" pose
#define P_CAMERA_PCT       25      // chance a move goes to CAMERA_DEG
#define P_SNAP_PCT         25      // chance of a fast snap instead of a creep
#define P_TWITCH_PCT       15      // chance of a small quick twitch
#define CREEP_MS_MIN       40      // creep speed: ms per degree
#define CREEP_MS_MAX       110
#define SNAP_MS            6       // snap speed: ms per degree (SG90 tops out near 2)
#define TWITCH_DEG         8       // twitch size, degrees
#define MIN_MOVE_DEG       12      // a move smaller than this looks like noise
// Freeze mid-turn when anyone moves: the head stops where it is and the turn
// stays owed. FREEZE_ABOVE_HIGH 1 freezes on what counts as presence (> HIGH).
// At LOW, 11% of turns in an empty room froze for nothing (unattended hour, NOTES).
#define FREEZE_ON_MOTION   1
#define FREEZE_ABOVE_HIGH  1

// --- Calibration (phase 3) ---
#define CAL_HOLD_MS        5000    // hold the button this long to start
#define CAL_LEAVE_MS       30000   // countdown: time to leave the room
#define CAL_RECORD_MS      60000   // then record the empty room this long
#define CAL_MIN_VALID      0.5f    // fraction of ticks with a good rate, else fail
#define CAL_MIN_STD_FRAC   0.1f    // std floor as a fraction of the mean

// --- Head angle (phase 4 moves it for real) ---
#define ANGLE_START        45      // set these once the head is mounted: START looks away,
#define ANGLE_STEP         30      // END stares into the camera. Keep within SERVO_MIN/MAX_DEG.
#define ANGLE_END          135
#define DEG_PER_STEP       1
#define STEP_MS            50

// --- Servo (phase 4) ---
#define SERVO_ENABLED      1       // SG90 on Grove: black GND, red 5V, yellow G2 (signal). 0 = timing-only stand-in, pin stays LOW
#define SERVO_PIN          2       // Grove signal, confirm against AtomS3R pinout
#define SERVO_MIN_US       500     // pulse at 0 deg
#define SERVO_MAX_US       2500    // pulse at 180 deg
#define SERVO_MIN_DEG      5       // clamp: never drive into the end stops (measure the real servo)
#define SERVO_MAX_DEG      175
#define SERVO_HOLD_MS      300     // keep the last pulse this long after a move, then stop the signal
#define RESET_HOLD_MS      2000    // button held 2-5 s: slow return to ANGLE_START
#define RESET_STEP_MS      100     // reset speed: 1 deg per this many ms (slower than a turn)
