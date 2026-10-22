#include "detector.h"
#include "config.h"
#include <math.h>

static void enter(Detector &d, DetState s, uint32_t now) {
  d.state = s;
  d.stateSince = now;
}

void detInit(Detector &d, uint32_t now) {
  d = {};
  d.state = ST_ACTIVE;  // boot: whoever plugged it in is in the room
  d.armed = false;
  d.stateSince = d.quietSince = d.lowRateSince = d.highSince = d.lastTurnDone = d.nextMoveAt = now;
}

uint32_t detQuietMs(const Detector &d, uint32_t now) {
  return (d.state == ST_QUIET_PENDING || d.state == ST_EMPTY) ? now - d.quietSince : 0;
}

uint8_t detStep(Detector &d, uint32_t now, float metric, uint16_t rate, float low, float high,
                bool calibrated, bool canTurn, bool moveBusy, uint32_t gapMs) {
  uint8_t ev = 0;
  // Haunt + PRESENCE_AT_LOW: any disturbance above LOW counts as someone here.
  float presence = (HAUNT && PRESENCE_AT_LOW) ? low : high;

  // Someone is near while the head moves: stop dead in whatever pose it
  // has reached. The turn stays owed (armed), so it carries on next absence.
  if (d.state == ST_TURNING) {
    float freezeAt = fminf(presence, FREEZE_ABOVE_HIGH ? high : low);
    if (FREEZE_ON_MOTION && metric > freezeAt) {
      d.armed = true;
      d.highRun = false;
      enter(d, ST_ACTIVE, now);
      return ev | DET_FROZEN;
    }
    // The head settling is motion near the antenna: ignore CSI after it.
    if (!moveBusy) {
      d.hasTurned = true;
      d.lastTurnDone = now;
      enter(d, ST_SETTLING, now);
      ev |= DET_TURN_DONE;
    }
    return ev;
  }
  if (d.state == ST_SETTLING) {
    if (now - d.stateSince >= T_SETTLE_MS) {
      enter(d, ST_EMPTY, now);
      d.nextMoveAt = now + gapMs;
      d.highRun = false;
      d.lowRate = false;
    }
    return ev;
  }

  // Missing data is never an empty room. Fail safe means fail still.
  if (rate < MIN_RATE) {
    if (!d.lowRate) {
      d.lowRate = true;
      d.lowRateSince = now;
    }
  } else {
    d.lowRate = false;
  }
  if (d.state == ST_STALE) {
    if (!d.lowRate) enter(d, ST_ACTIVE, now);
    return ev;
  }
  if (d.lowRate && now - d.lowRateSince > T_STALE_MS) {
    enter(d, ST_STALE, now);
    d.highRun = false;
    return ev | DET_STALE;
  }

  if (!calibrated) return ev;  // no thresholds yet: stay as we are, never turn

  // A big disturbance means someone was surely here, and may now sit still.
  if (metric > high * STRONG_X_HIGH) {
    d.hasStrong = true;
    d.lastStrong = now;
  }
  bool strongRecent = HAUNT && d.hasStrong && now - d.lastStrong < T_AFTER_STRONG_MS;

  // Re-arm: someone came back and moved, above HIGH continuously for T_REARM.
  if (metric > high) {
    if (!d.highRun) {
      d.highRun = true;
      d.highSince = now;
    }
    if (!d.armed && now - d.highSince >= T_REARM_MS) {
      d.armed = true;
      ev |= DET_REARMED;
    }
  } else {
    d.highRun = false;
  }

  switch (d.state) {
    case ST_ACTIVE:
      if (metric < low) {
        enter(d, ST_QUIET_PENDING, now);
        d.quietSince = now;
      }
      break;
    case ST_QUIET_PENDING:
      if (metric > presence) enter(d, ST_ACTIVE, now);
      else if (now - d.quietSince >= T_EMPTY_MS && !strongRecent) {
        enter(d, ST_EMPTY, now);
        d.nextMoveAt = now;  // haunt: first move right away
      }
      break;
    case ST_EMPTY:
      if (metric > presence) {
        enter(d, ST_ACTIVE, now);
      } else if (HAUNT) {
        if (canTurn && (int32_t)(now - d.nextMoveAt) >= 0) {
          enter(d, ST_TURNING, now);
          ev |= DET_TURN_START;
        }
      } else if (d.armed && canTurn &&
                 (!d.hasTurned || now - d.lastTurnDone >= T_COOLDOWN_MS)) {
        d.armed = false;
        enter(d, ST_TURNING, now);
        ev |= DET_TURN_START;
      }
      break;
    default:
      break;
  }
  return ev;
}

void detThresholds(float mean, float std, float &low, float &high) {
  if (std < mean * CAL_MIN_STD_FRAC) std = mean * CAL_MIN_STD_FRAC;
  low  = fmaxf(mean + K_LOW * std, mean * LOW_RATIO);
  high = fmaxf(mean + K_HIGH * std, mean * HIGH_RATIO);
}

const char *detStateName(DetState s) {
  static const char *names[] = {"STALE", "ACTIVE", "QUIET", "EMPTY", "TURNING", "SETTLING"};
  return s <= ST_SETTLING ? names[s] : "?";
}
