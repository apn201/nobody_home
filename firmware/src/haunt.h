// Haunt mode move planner: where to, how fast, how long until the next.
// tools/detector.py plan_move() is the Python copy: change one, change both.
#pragma once
#include <stdint.h>

struct HauntMove {
  int16_t  target;   // degrees
  uint16_t msPerDeg; // speed
  uint32_t gapMs;    // pause after this move settles
};

HauntMove hauntPlan(int16_t angle);
