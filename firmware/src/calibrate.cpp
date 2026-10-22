#include "calibrate.h"
#include "config.h"
#include <math.h>

static CalPhase s_phase = CAL_IDLE;
static uint32_t s_phaseSince;
static double   s_sum, s_sumSq;
static uint32_t s_n, s_ticks;

void calStart(uint32_t now) {
  s_phase = CAL_LEAVE;
  s_phaseSince = now;
}

void calCancel() {
  s_phase = CAL_IDLE;
}

CalPhase calPhase() {
  return s_phase;
}

uint32_t calSecondsLeft(uint32_t now) {
  uint32_t len = s_phase == CAL_LEAVE ? CAL_LEAVE_MS : s_phase == CAL_RECORD ? CAL_RECORD_MS : 0;
  uint32_t el = now - s_phaseSince;
  return el >= len ? 0 : (len - el + 999) / 1000;
}

CalResult calStep(uint32_t now, float metric, uint16_t rate, float &mean, float &std) {
  switch (s_phase) {
    case CAL_IDLE:
      return CAL_NONE;
    case CAL_LEAVE:
      if (now - s_phaseSince >= CAL_LEAVE_MS) {
        s_phase = CAL_RECORD;
        s_phaseSince = now;
        s_sum = s_sumSq = 0;
        s_n = s_ticks = 0;
      }
      return CAL_RUNNING;
    case CAL_RECORD:
      s_ticks++;
      if (rate >= MIN_RATE) {  // stale ticks say nothing about the room
        s_sum += metric;
        s_sumSq += (double)metric * metric;
        s_n++;
      }
      if (now - s_phaseSince < CAL_RECORD_MS) return CAL_RUNNING;
      s_phase = CAL_IDLE;
      if (s_n < 2 || s_n < s_ticks * CAL_MIN_VALID) return CAL_FAILED;
      mean = s_sum / s_n;
      double var = s_sumSq / s_n - (double)mean * mean;
      std = var > 0 ? sqrt(var) : 0;
      return mean > 0 ? CAL_DONE : CAL_FAILED;
  }
  return CAL_NONE;
}
