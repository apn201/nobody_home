// Nobody Home - phase 3: calibration and the stillness state machine.
// Boot never moves the servo. Motion is still a stand-in with no PWM.

#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <M5Unified.h>

#include "config.h"
#include "secrets.h"
#include "csi.h"
#include "traffic.h"
#include "detector.h"
#include "haunt.h"
#include "calibrate.h"
#include "motion.h"
#include "store.h"
#include "telemetry.h"
#include "ui.h"

static uint32_t s_lastReport;
static uint32_t s_lastTick;
static uint32_t s_lastScreen;
static uint32_t s_seconds;
static uint16_t s_rate;  // callbacks in the last full second
static int8_t   s_rssi;

static Detector s_det;
static bool     s_calibrated;
static float    s_low, s_high;
static bool     s_holdHandled;
static uint32_t s_pressStart;
static bool     s_resetting;  // slow return to ANGLE_START in progress
static uint32_t s_nextGapMs = HAUNT_GAP_MIN_MS;  // haunt: pause after the current move

static void halt(const char *why) {
  Serial.printf("FATAL %s\n", why);
  uiShow("FATAL", why, TFT_RED);
  for (;;) delay(1000);
}

static void applyCalibration(float mean, float std) {
  detThresholds(mean, std, s_low, s_high);
  s_calibrated = true;
  Serial.printf("calibration mean=%.4f std=%.4f -> LOW=%.4f HIGH=%.4f\n", mean, std, s_low, s_high);
}

static bool waitConnected(uint32_t ms) {
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - t0 > ms) return false;
    delay(250);
    Serial.print('.');
  }
  return true;
}

// Thresholds only hold for the link they were measured on. A mesh has
// several APs with one SSID, and the default fast scan joins whichever it
// hears first. So: the AP saved with the calibration if it is there, else
// the strongest, and then the old calibration does not apply.
static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // a napping radio misses CSI frames
  WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);
  WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);

  uint8_t bssid[6], ch;
  bool haveAp = storeLoadAp(bssid, ch);
  if (s_calibrated && haveAp) {
    Serial.printf("joining the calibrated AP %02X:%02X:%02X:%02X:%02X:%02X ch %u\n",
                  bssid[0], bssid[1], bssid[2], bssid[3], bssid[4], bssid[5], ch);
    WiFi.begin(WIFI_SSID, WIFI_PASS, ch, bssid);
    if (waitConnected(10000)) return;
    Serial.println("\ncalibrated AP not found: joining the strongest, calibration does not apply");
    WiFi.disconnect();
    s_calibrated = false;
  }
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  if (!waitConnected(20000)) halt("no WiFi");
}

void setup() {
  auto cfg = M5.config();
  // The servo signal is on the Grove port, which doubles as external I2C.
  // No probing for external sensors there: I2C traffic would twitch the head.
  cfg.external_imu = false;
  cfg.external_rtc = false;
  cfg.external_display_value = 0;
  M5.begin(cfg);
  Serial.begin(115200);
  // With no host reading USB, each write blocked 100 ms and stalled the loop
  // to ~1 Hz. The prop runs on a charger, so drop serial output instead.
  Serial.setTxTimeoutMs(0);
  delay(1500);  // let USB CDC enumerate so the first lines are not lost
  Serial.println("\nNobody Home - phase 3");
  uiBegin(PAGE_SCOPE);
  uiShow("WiFi...", WIFI_SSID, TFT_WHITE);

  storeBegin();
  float mean, std;
  if (storeLoadCalibration(mean, std)) applyCalibration(mean, std);
  else Serial.println("not calibrated: hold the button 5 s, then leave the room");
  int16_t angle = ANGLE_START;
  storeLoadAngle(angle);
  motionBegin(angle);  // no move: the head is where it was left
  Serial.printf("head at %d deg (servo %s)\n", angle, SERVO_ENABLED ? "on" : "stand-in, no PWM");

  connectWifi();
  esp_wifi_set_ps(WIFI_PS_NONE);

  const uint8_t *bssid = WiFi.BSSID();
  Serial.printf("\nconnected ip=%s gw=%s bssid=%s ch=%d rssi=%d\n",
                WiFi.localIP().toString().c_str(), WiFi.gatewayIP().toString().c_str(),
                WiFi.BSSIDstr().c_str(), WiFi.channel(), WiFi.RSSI());

  // Google/Nest mesh here: follow roams so the MAC filter stays on our AP.
  WiFi.onEvent([](arduino_event_id_t, arduino_event_info_t info) {
    const uint8_t *b = info.wifi_sta_connected.bssid;
    csiSetBssid(b);
    Serial.printf("ROAM bssid=%02X:%02X:%02X:%02X:%02X:%02X ch=%u\n",
                  b[0], b[1], b[2], b[3], b[4], b[5], info.wifi_sta_connected.channel);
  }, ARDUINO_EVENT_WIFI_STA_CONNECTED);

  esp_err_t err = csiBegin(bssid);
  if (err != ESP_OK) {
    // Most likely CONFIG_ESP_WIFI_CSI_ENABLED is off in the prebuilt libs.
    Serial.printf("csiBegin failed: %s\n", esp_err_to_name(err));
    halt("CSI off");
  }
  err = trafficBegin(WiFi.gatewayIP(), PING_INTERVAL_MS);
  if (err != ESP_OK) {
    Serial.printf("trafficBegin failed: %s\n", esp_err_to_name(err));
    halt("no ping");
  }
  Serial.printf("CSI on, pinging gateway every %d ms\n", PING_INTERVAL_MS);

  telemetryBegin(PC_IP);
  telemetryEvent(EV_BOOT, motionAngle());
  Serial.printf("telemetry -> %s:20003 at %d Hz\n", PC_IP, 1000 / TELEMETRY_MS);

  s_lastReport = s_lastTick = millis();
  detInit(s_det, s_lastTick);  // ACTIVE and disarmed: whoever plugged it in is here
}

// Button held 2-5 s: back to the start pose, slowly. Whoever pressed it is in
// the room, so the detector starts over disarmed.
static void startReset(uint32_t now) {
  s_resetting = true;
  calCancel();
  detInit(s_det, now);
  moveTo(ANGLE_START, RESET_STEP_MS);
  telemetryEvent(EV_RESET, motionAngle());
  Serial.printf("RESET: returning %d -> %d\n", motionAngle(), ANGLE_START);
}

static void handleButton(uint32_t now) {
  if (M5.BtnA.wasPressed()) s_pressStart = now;
  if (M5.BtnA.isPressed() && !s_holdHandled && M5.BtnA.pressedFor(CAL_HOLD_MS)) {
    s_holdHandled = true;
    calStart(now);
    Serial.printf("calibration: leave the room, recording starts in %d s\n", CAL_LEAVE_MS / 1000);
  }
  if (M5.BtnA.wasReleased()) {
    if (!s_holdHandled && now - s_pressStart >= RESET_HOLD_MS) startReset(now);
    s_holdHandled = false;
  }
  if (M5.BtnA.wasClicked()) {
    if (calPhase() != CAL_IDLE) {
      calCancel();
      Serial.println("calibration cancelled");
    } else {
      uiNextPage();
    }
  }
}

// 10 Hz: calibration, detector, telemetry, all on the same inputs.
static void tick(uint32_t now) {
  float metric = csiMetric();

  float mean, std;
  CalResult cr = calStep(now, metric, s_rate, mean, std);
  if (cr == CAL_DONE) {
    storeSaveCalibration(mean, std);
    storeSaveAp(WiFi.BSSID(), WiFi.channel());  // the link these thresholds belong to
    applyCalibration(mean, std);
    detInit(s_det, now);  // start over disarmed; the next turn needs someone to come and go
    telemetryEvent(EV_CALIBRATED, motionAngle());
  } else if (cr == CAL_FAILED) {
    Serial.println("calibration failed: too many ticks without CSI");
  }

  if (s_resetting && !isBusy()) {
    s_resetting = false;
    storeSaveAngle(motionAngle());
    Serial.printf("RESET done at %d\n", motionAngle());
  }

  int16_t angle = motionAngle();
  bool canTurn = calPhase() == CAL_IDLE && !s_resetting && (HAUNT || angle < ANGLE_END);
  uint8_t ev = detStep(s_det, now, metric, s_rate, s_low, s_high, s_calibrated, canTurn,
                       isBusy() && !s_resetting, s_nextGapMs);

  if (ev & DET_TURN_START) {
    int16_t target;
    uint16_t msPerDeg;
    if (HAUNT) {
      HauntMove hm = hauntPlan(angle);
      target = hm.target;
      msPerDeg = hm.msPerDeg;
      s_nextGapMs = hm.gapMs;  // used when this move has settled
    } else {
      target = angle + ANGLE_STEP > ANGLE_END ? ANGLE_END : angle + ANGLE_STEP;
      msPerDeg = STEP_MS;
    }
    moveTo(target, msPerDeg);
    telemetryEvent(EV_TURN_START, target);
    Serial.printf("TURN start %d -> %d at %u ms/deg\n", angle, target, msPerDeg);
  }
  if (ev & DET_FROZEN) {
    stop();  // stays in this pose; the rest of the turn is owed
    storeSaveAngle(motionAngle());
    telemetryEvent(EV_FROZEN, motionAngle());
    Serial.printf("FROZEN at %d, someone is near\n", motionAngle());
  }
  if (ev & DET_TURN_DONE) {
    storeSaveAngle(motionAngle());
    telemetryEvent(EV_TURN_DONE, motionAngle());
    Serial.printf("TURN done at %d\n", motionAngle());
  }
  if (ev & DET_STALE) {
    telemetryEvent(EV_STALE, motionAngle());
    Serial.println("STALE: CSI rate too low, holding still");
  }
  if (ev & DET_REARMED) {
    telemetryEvent(EV_REARMED, motionAngle());
    Serial.println("REARMED");
  }

  TelemetryData d = {};
  d.uptimeMs = now;
  d.rate     = s_rate;
  d.metric   = metric;
  d.low      = s_calibrated ? s_low : 0;
  d.high     = s_calibrated ? s_high : 0;
  d.state    = s_det.state;
  d.armed    = s_det.armed;
  d.quietMs  = detQuietMs(s_det, now);
  d.angle    = motionAngle();
  d.rssi     = s_rssi;
  telemetrySend(d);
}

// Once a second: calibration countdown (always shown), or the status page.
static void showStatus(uint32_t now) {
  char l1[24], l2[24];
  CalPhase cp = calPhase();
  if (cp != CAL_IDLE) {
    snprintf(l1, sizeof l1, cp == CAL_LEAVE ? "LEAVE" : "CAL");
    snprintf(l2, sizeof l2, "%lus", calSecondsLeft(now));
    uiShow(l1, l2, cp == CAL_LEAVE ? TFT_WHITE : TFT_CYAN);
    return;
  }
  if (uiPage() != PAGE_STATUS) return;
  static const uint16_t colors[] = {TFT_RED, TFT_WHITE, TFT_YELLOW, TFT_GREEN, TFT_MAGENTA, TFT_MAGENTA};
  snprintf(l1, sizeof l1, "%s%s", detStateName(s_det.state), s_det.armed ? "*" : "");
  if (s_calibrated) snprintf(l2, sizeof l2, "m%.2f q%lu", csiMetric(), detQuietMs(s_det, now) / 1000);
  else snprintf(l2, sizeof l2, "uncal %u/s", s_rate);
  uiShow(l1, l2, colors[s_det.state]);
}

void loop() {
  M5.update();
  uint32_t now = millis();
  handleButton(now);
  telemetryPoll(now);
  motionUpdate(now);

  // After a stall, resync instead of catching up in a burst.
  if (now - s_lastTick >= TELEMETRY_MS) {
    s_lastTick = now - s_lastTick >= 2 * TELEMETRY_MS ? now : s_lastTick + TELEMETRY_MS;
    tick(now);
  }

  // Raw CSI for tools/scope.py: every frame, in order.
  CsiSnap frame;
  while (csiNextFrame(frame)) telemetryRaw(frame);

  if (now - s_lastScreen >= SCREEN_MS && calPhase() == CAL_IDLE && uiPage() == PAGE_SCOPE) {
    s_lastScreen = now;
    UiScope sc;
    csiSnapshot(sc.snap);
    sc.low    = s_calibrated ? s_low : 0;
    sc.high   = s_calibrated ? s_high : 0;
    sc.state  = s_det.state;
    sc.armed  = s_det.armed;
    sc.quietS = detQuietMs(s_det, now) / 1000;
    sc.rate   = s_rate;
    sc.angle  = motionAngle();
    uiScope(sc);
  }

  if (now - s_lastReport < 1000) { delay(2); return; }
  s_lastReport = now - s_lastReport >= 2000 ? now : s_lastReport + 1000;
  s_seconds++;

  CsiStats st;
  csiTakeStats(st);
  uint32_t replies, timeouts;
  trafficTakeStats(replies, timeouts);
  s_rate = st.count > 0xFFFF ? 0xFFFF : st.count;
  s_rssi = st.rssi;

  // One line per second. tools/csi_rate.py parses the key=value pairs.
  const uint8_t *m = st.otherMac;
  Serial.printf("RATE t=%lu cb=%lu gap=%lu rssi=%d ch=%u ping=%lu lost=%lu drop=%lu other=%lu wifi=%d "
                "metric=%.3f state=%s armed=%d src=%02X:%02X:%02X:%02X:%02X:%02X\n",
                s_seconds, st.count, st.maxGapMs, st.rssi, st.channel,
                replies, timeouts, st.dropped, st.rejected, WiFi.status() == WL_CONNECTED,
                csiMetric(), detStateName(s_det.state), s_det.armed,
                m[0], m[1], m[2], m[3], m[4], m[5]);
  showStatus(now);
}
