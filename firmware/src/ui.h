// Screen. Pages: live CSI scope, status text, off. Short press cycles them.
// The scope only draws what the CSI task measured; nothing is synthesised.
#pragma once
#include <stdint.h>
#include "csi.h"

enum UiPage : uint8_t { PAGE_SCOPE, PAGE_STATUS, PAGE_OFF, PAGE_COUNT };

struct UiScope {
  CsiSnap  snap;
  float    low, high;   // 0 when not calibrated
  uint8_t  state;       // DetState
  bool     armed;
  uint32_t quietS;
  uint16_t rate;
  int16_t  angle;
};

void   uiBegin(UiPage first);
void   uiNextPage();
UiPage uiPage();

void uiShow(const char *line1, const char *line2, uint16_t color);  // big two-line text
void uiScope(const UiScope &s);                                      // one scope frame
