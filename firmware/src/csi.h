// CSI capture, rate monitor. Feature extraction lands here in phase 2.
#pragma once
#include <stdint.h>
#include <esp_err.h>

struct CsiStats {
  uint32_t count;      // accepted callbacks in the window
  uint32_t maxGapMs;   // longest gap between accepted frames (incl. time since last)
  uint32_t dropped;    // frames lost because the queue was full
  uint32_t rejected;   // frames from other MACs
  int8_t   rssi;       // last accepted frame
  uint8_t  channel;
  uint8_t  otherMac[6]; // source MAC of the last rejected frame
};

// Only frames whose source MAC equals bssid are accepted.
esp_err_t csiBegin(const uint8_t bssid[6]);

// Call on every (re)connect: a mesh can roam the Atom to another node.
void csiSetBssid(const uint8_t bssid[6]);

// The latest full frame, as measured. Feeds the scope on the screen and the
// raw UDP stream; nothing in it is smoothed or synthesised.
#define CSI_NSUB 51
struct CsiSnap {
  uint32_t frames;          // full frames since boot (a jump = frames not sent)
  uint32_t tMs;             // when the frame arrived
  float    feature;         // spatial std of this frame, as measured
  float    filtered;        // feature after the Hampel filter (HAMPEL_K frames older)
  float    metric;          // moving variance of the filtered feature
  int8_t   rssi;
  uint8_t  amps[CSI_NSUB];  // amplitude per subcarrier, -26..-1 then 2..26
};
void csiSnapshot(CsiSnap &out);  // latest frame
bool csiNextFrame(CsiSnap &out); // every frame in order, false when none waiting

// Motion metric: moving variance of the per-frame spatial std over
// MOTION_WINDOW_MS. 0 until the window has two frames.
float csiMetric();

// Returns stats since the previous call and starts a new window.
void csiTakeStats(CsiStats &out);
