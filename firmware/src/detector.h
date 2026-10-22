// Stillness state machine. tools/detector.py is a line-for-line Python copy
// used for replay tests: change one, change both.
#pragma once
#include <stdint.h>

enum DetState : uint8_t {
  ST_STALE         = 0,
  ST_ACTIVE        = 1,
  ST_QUIET_PENDING = 2,
  ST_EMPTY         = 3,
  ST_TURNING       = 4,
  ST_SETTLING      = 5,
};

// Bitmask returned by detStep
enum DetEvent : uint8_t {
  DET_TURN_START = 1,
  DET_TURN_DONE  = 2,
  DET_STALE      = 4,
  DET_REARMED    = 8,
  DET_FROZEN     = 16,  // someone moved mid-turn: stop the head where it is
};

struct Detector {
  DetState state;
  bool     armed;
  uint32_t stateSince;
  uint32_t quietSince;
  bool     lowRate;
  uint32_t lowRateSince;
  bool     highRun;
  uint32_t highSince;
  bool     hasTurned;
  uint32_t lastTurnDone;
  uint32_t nextMoveAt;  // haunt: next move while EMPTY
  bool     hasStrong;   // haunt: someone surely moved in the room at lastStrong
  uint32_t lastStrong;
};

void detInit(Detector &d, uint32_t now);

// One 10 Hz tick. Returns DetEvent bits. gapMs (haunt): pause before the next
// move once the current one has settled.
uint8_t detStep(Detector &d, uint32_t now, float metric, uint16_t rate, float low, float high,
                bool calibrated, bool canTurn, bool moveBusy, uint32_t gapMs);

uint32_t detQuietMs(const Detector &d, uint32_t now);
const char *detStateName(DetState s);

// LOW and HIGH from a calibration, with a floor on std.
void detThresholds(float mean, float std, float &low, float &high);
