#include "haunt.h"
#include "config.h"
#include <esp_random.h>
#include <stdlib.h>

static float rnd() {  // uniform [0, 1)
  return (esp_random() >> 8) / 16777216.0f;
}

HauntMove hauntPlan(int16_t angle) {
  HauntMove m;
  const int lo = POSE_MIN_DEG, hi = POSE_MAX_DEG;
  if (rnd() * 100 < P_TWITCH_PCT) {
    int step = angle + TWITCH_DEG <= hi ? TWITCH_DEG : -TWITCH_DEG;
    if (rnd() < 0.5f && angle - TWITCH_DEG >= lo) step = -TWITCH_DEG;
    m.target = angle + step;
    m.msPerDeg = SNAP_MS;
  } else {
    int target = -1;
    if (rnd() * 100 < P_CAMERA_PCT && abs(CAMERA_DEG - angle) >= MIN_MOVE_DEG) target = CAMERA_DEG;
    for (int i = 0; i < 8 && target < 0; i++) {
      int t = lo + (int)(rnd() * (hi - lo + 1));
      if (abs(t - angle) >= MIN_MOVE_DEG) target = t;
    }
    if (target < 0) target = angle - lo > hi - angle ? lo : hi;  // pathological range
    m.target = target;
    m.msPerDeg = rnd() * 100 < P_SNAP_PCT
                     ? SNAP_MS
                     : CREEP_MS_MIN + (int)(rnd() * (CREEP_MS_MAX - CREEP_MS_MIN + 1));
  }
  m.gapMs = HAUNT_GAP_MIN_MS + (uint32_t)(rnd() * (HAUNT_GAP_MAX_MS - HAUNT_GAP_MIN_MS + 1));
  return m;
}
