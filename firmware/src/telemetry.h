// UDP telemetry to the PC. Fire-and-forget: if the PC is off, nothing changes.
#pragma once
#include <stdint.h>
#include "csi.h"

enum EventCode : uint8_t {
  EV_BOOT = 1, EV_CALIBRATED = 2, EV_TURN_START = 3, EV_TURN_DONE = 4,
  EV_RESET = 5, EV_STALE = 6, EV_REARMED = 7, EV_LIFTED = 8, EV_PUT_DOWN = 9,
  EV_FROZEN = 10,  // turn interrupted by motion, head left mid-pose
};

struct TelemetryData {
  uint32_t uptimeMs;  // the tick time the detector saw, so replays line up
  uint16_t rate;      // callbacks in the last second
  float    metric;
  float    low, high; // thresholds, 0 until calibrated
  uint8_t  state;     // DetState
  uint8_t  armed;
  uint32_t quietMs;
  int16_t  angle;
  int8_t   rssi;
};

void telemetryBegin(const char *pcIp);

// Call often: picks up scope hellos so any PC on the LAN can watch.
void telemetryPoll(uint32_t now);
void telemetrySend(const TelemetryData &d);
void telemetryEvent(EventCode code, int16_t angle);

// Latest CSI frame (amplitudes per subcarrier) for tools/scope.py. Type 0x03.
void telemetryRaw(const CsiSnap &s);
