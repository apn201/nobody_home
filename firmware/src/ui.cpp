#include "ui.h"
#include "detector.h"
#include <M5Unified.h>
#include <math.h>

#define W 128
#define H 128
#define HIST W  // one sample per pixel column

// Layout (y ranges): header, CSI trace, motion metric, spectrum
#define HDR_H   10
#define TR_Y0   11
#define TR_Y1   58
#define MT_Y0   61
#define MT_Y1   97
#define SP_Y0   100
#define SP_Y1   127

// Scope colours, RGB565
#define C_GRID   0x0120  // dim green
#define C_TRACE  0x07E0  // phosphor green
#define C_METRIC 0xFD20  // amber
#define C_LOW    0xFFE0  // yellow
#define C_HIGH   0xF800  // red
#define C_SPEC   0x07FF  // cyan
#define C_LABEL  0x4208  // grey

static M5Canvas s_canvas(&M5.Display);
static bool     s_spriteOk;
static UiPage   s_page;
static bool     s_asleep;

static float    s_feat[HIST], s_metric[HIST];
static uint16_t s_head, s_count;
static uint32_t s_lastFrames;

static void wake() {
  if (s_asleep) {
    M5.Display.wakeup();
    M5.Display.setBrightness(128);
    s_asleep = false;
  }
}

void uiBegin(UiPage first) {
  s_canvas.setColorDepth(16);
  s_spriteOk = s_canvas.createSprite(W, H) != nullptr;
  s_page = first;
}

UiPage uiPage() {
  return s_page;
}

void uiNextPage() {
  s_page = (UiPage)((s_page + 1) % PAGE_COUNT);
  if (s_page == PAGE_OFF) {
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setBrightness(0);
    M5.Display.sleep();
    s_asleep = true;
  } else {
    wake();
  }
}

void uiShow(const char *line1, const char *line2, uint16_t color) {
  wake();
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setTextColor(color, TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(4, 20);
  M5.Display.println(line1);
  M5.Display.setCursor(4, 60);
  M5.Display.println(line2);
}

static void grid(int y0, int y1) {
  for (int x = 0; x < W; x += 16)
    for (int y = y0; y <= y1; y += 3) s_canvas.drawPixel(x, y, C_GRID);
  for (int y = y0; y <= y1; y += (y1 - y0) / 4)
    for (int x = 0; x < W; x += 3) s_canvas.drawPixel(x, y, C_GRID);
}

static void hline(int y, uint16_t c) {
  for (int x = 0; x < W; x += 4) s_canvas.drawFastHLine(x, y, 2, c);
}

// Oldest sample at the left, newest at the right edge.
static float histAt(const float *buf, int i) {
  return buf[(s_head + HIST - s_count + i) % HIST];
}

void uiScope(const UiScope &s) {
  if (!s_spriteOk || s_page != PAGE_SCOPE) return;
  wake();

  // Only real new frames go into the traces. No new frame, no new sample.
  if (s.snap.frames != s_lastFrames) {
    s_lastFrames = s.snap.frames;
    s_feat[s_head] = s.snap.feature;
    s_metric[s_head] = s.snap.metric;
    s_head = (s_head + 1) % HIST;
    if (s_count < HIST) s_count++;
  }

  s_canvas.fillSprite(TFT_BLACK);

  // Header: state, armed, quiet time, CSI rate
  static const uint16_t stateColor[] = {TFT_RED, TFT_WHITE, TFT_YELLOW, TFT_GREEN, TFT_MAGENTA, TFT_MAGENTA};
  char hdr[32];
  if (s.high > 0)
    snprintf(hdr, sizeof hdr, "%s%s q%lu %u/s", detStateName((DetState)s.state), s.armed ? "*" : "",
             s.quietS, s.rate);
  else
    snprintf(hdr, sizeof hdr, "UNCAL %u/s %ddBm", s.rate, s.snap.rssi);
  s_canvas.setTextSize(1);
  s_canvas.setTextColor(stateColor[s.state <= ST_SETTLING ? s.state : 1]);
  s_canvas.setCursor(1, 1);
  s_canvas.print(hdr);

  // CSI trace: per-frame spatial std, autoscaled to what is on screen
  grid(TR_Y0, TR_Y1);
  if (s_count > 1) {
    float lo = 1e9f, hi = -1e9f;
    for (int i = 0; i < s_count; i++) {
      float v = histAt(s_feat, i);
      lo = fminf(lo, v);
      hi = fmaxf(hi, v);
    }
    float span = fmaxf(hi - lo, 0.5f);
    float mid = (hi + lo) / 2;
    lo = mid - span * 0.6f;
    span *= 1.2f;
    int x0 = W - s_count, prevY = 0;
    for (int i = 0; i < s_count; i++) {
      int y = TR_Y1 - (int)((histAt(s_feat, i) - lo) / span * (TR_Y1 - TR_Y0));
      if (i) s_canvas.drawLine(x0 + i - 1, prevY, x0 + i, y, C_TRACE);
      prevY = y;
    }
  }
  s_canvas.setTextColor(C_LABEL);
  s_canvas.setCursor(1, TR_Y0);
  s_canvas.print("CSI");

  // Motion metric on a log scale, with LOW and HIGH
  grid(MT_Y0, MT_Y1);
  if (s_count > 1) {
    float top = s.high > 0 ? s.high * 3 : 1.0f, bot = s.low > 0 ? s.low / 10 : 0.001f;
    for (int i = 0; i < s_count; i++) top = fmaxf(top, histAt(s_metric, i));
    float lt = log10f(top), lb = log10f(bot);
    auto ym = [&](float v) {
      float l = log10f(fmaxf(v, bot));
      return MT_Y1 - (int)((l - lb) / (lt - lb) * (MT_Y1 - MT_Y0));
    };
    if (s.low > 0) hline(ym(s.low), C_LOW);
    if (s.high > 0) hline(ym(s.high), C_HIGH);
    int x0 = W - s_count, prevY = 0;
    for (int i = 0; i < s_count; i++) {
      int y = ym(histAt(s_metric, i));
      if (i) s_canvas.drawLine(x0 + i - 1, prevY, x0 + i, y, C_METRIC);
      prevY = y;
    }
  }
  s_canvas.setTextColor(C_LABEL);
  s_canvas.setCursor(1, MT_Y0);
  s_canvas.print("MOTION");

  // Spectrum: amplitude of each subcarrier in the latest frame
  uint8_t peak = 1;
  for (int i = 0; i < CSI_NSUB; i++) peak = s.snap.amps[i] > peak ? s.snap.amps[i] : peak;
  for (int i = 0; i < CSI_NSUB; i++) {
    int x = 1 + i * (W - 2) / CSI_NSUB;
    int h = s.snap.amps[i] * (SP_Y1 - SP_Y0) / peak;
    s_canvas.fillRect(x, SP_Y1 - h, 2, h + 1, C_SPEC);
  }

  s_canvas.pushSprite(0, 0);
}
