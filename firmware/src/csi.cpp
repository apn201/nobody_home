#include "csi.h"
#include "config.h"

#include <string.h>
#include <math.h>
#include <esp_wifi.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

struct CsiFrame {
  int64_t t_us;
  int8_t  rssi;
  uint8_t channel;
  uint8_t len;
  int8_t  buf[CSI_BUF_MAX];
};

static uint8_t       s_bssid[6];
static QueueHandle_t s_queue;
static volatile uint32_t s_dropped;
static volatile uint32_t s_rejected;
static uint8_t s_otherMac[6];

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static uint32_t s_count;
static uint32_t s_maxGapUs;
static int64_t  s_lastUs;
static int8_t   s_rssi;
static uint8_t  s_channel;
static float    s_metric;
static CsiSnap  s_snap;  // latest full frame, for the scope views
static QueueHandle_t s_frameQ;  // every full frame, for the raw stream

// Moving variance window. Only the csi task touches these.
#define WIN_LEN 512  // > MOTION_WINDOW_MS at 200 frames/s (ping catch-up bursts)
static uint32_t s_winT[WIN_LEN];
static float    s_winF[WIN_LEN];
static uint16_t s_winHead, s_winCount;
static double   s_sum, s_sumSq;
static uint32_t s_sinceResum;

// LLTF, 20 MHz: buffer index k holds subcarrier k for k < 32 and k - 64 above.
// Used: -26..-1 and 2..26. Subcarrier 0 is DC, beyond +-26 are guards, and
// subcarrier 1 sits in the first word, which the S3 can flag invalid.
static inline bool usedSubcarrier(int k) {
  return (k >= 2 && k <= 26) || (k >= 38 && k <= 63);
}

// Spatial turbulence: std of amplitude across the used subcarriers.
// Also fills amps (CSI_NSUB, ordered -26..-1, 2..26) for the scope views.
static float spatialStd(const int8_t *buf, uint8_t *amps) {
  float sum = 0, sumSq = 0;
  int n = 0;
  for (int j = 0; j < 64; j++) {
    int k = (j + 38) % 64;  // walk -26..-1 first, then 0..37, so the spectrum reads left to right
    if (!usedSubcarrier(k)) continue;
    float i = buf[2 * k], q = buf[2 * k + 1];
    float a = sqrtf(i * i + q * q);
    amps[n] = (uint8_t)(a + 0.5f);  // max sqrt(2) * 128 = 181, fits
    sum += a;
    sumSq += a * a;
    n++;
  }
  float mean = sum / n;
  float var = sumSq / n - mean * mean;
  return var > 0 ? sqrtf(var) : 0;
}

static float windowAdd(uint32_t tMs, float f) {
  // Drop samples older than the window, and the oldest if full.
  while (s_winCount > 0) {
    uint16_t tail = (s_winHead + WIN_LEN - s_winCount) % WIN_LEN;
    if (s_winCount < WIN_LEN && tMs - s_winT[tail] <= MOTION_WINDOW_MS) break;
    s_sum   -= s_winF[tail];
    s_sumSq -= (double)s_winF[tail] * s_winF[tail];
    s_winCount--;
  }
  s_winT[s_winHead] = tMs;
  s_winF[s_winHead] = f;
  s_winHead = (s_winHead + 1) % WIN_LEN;
  s_winCount++;
  s_sum   += f;
  s_sumSq += (double)f * f;

  // Running sums drift, so rebuild them now and then.
  if (++s_sinceResum >= 4096) {
    s_sinceResum = 0;
    s_sum = s_sumSq = 0;
    for (uint16_t j = 0; j < s_winCount; j++) {
      float v = s_winF[(s_winHead + WIN_LEN - 1 - j) % WIN_LEN];
      s_sum += v;
      s_sumSq += (double)v * v;
    }
  }

  if (s_winCount < 2) return 0;
  double mean = s_sum / s_winCount;
  double var = s_sumSq / s_winCount - mean * mean;
  return var > 0 ? (float)var : 0;
}

// Runs in the WiFi task. No allocation, no logging, no blocking.
static void csiCallback(void *ctx, wifi_csi_info_t *info) {
  if (!info || !info->buf) return;
  if (memcmp(info->mac, s_bssid, 6) != 0) {
    s_rejected++;
    memcpy(s_otherMac, info->mac, 6);
    return;
  }

  CsiFrame f;
  f.t_us    = esp_timer_get_time();
  f.rssi    = info->rx_ctrl.rssi;
  f.channel = info->rx_ctrl.channel;
  f.len     = info->len < CSI_BUF_MAX ? info->len : CSI_BUF_MAX;
  memcpy(f.buf, info->buf, f.len);
  if (xQueueSend(s_queue, &f, 0) != pdTRUE) s_dropped++;
}

// Hampel filter: judge the middle of the last 2K+1 features and replace it
// with the median if it is an outlier. One glitch frame (e.g. received at a
// different gain) otherwise puts a 1.5 s step into the moving variance.
#define H_LEN (2 * HAMPEL_K + 1)
static float    s_hX[H_LEN > 1 ? H_LEN : 1];
static uint32_t s_hT[H_LEN > 1 ? H_LEN : 1];
static uint8_t  s_hHead, s_hCount;

static float median(float *v, int n) {  // sorts v in place, n is small
  for (int i = 1; i < n; i++) {
    float x = v[i];
    int j = i - 1;
    while (j >= 0 && v[j] > x) { v[j + 1] = v[j]; j--; }
    v[j + 1] = x;
  }
  return v[n / 2];
}

// Returns false until the window is full. tOut/xOut are HAMPEL_K frames old.
static bool hampel(uint32_t t, float x, uint32_t &tOut, float &xOut) {
  if (HAMPEL_K == 0) { tOut = t; xOut = x; return true; }
  s_hX[s_hHead] = x;
  s_hT[s_hHead] = t;
  s_hHead = (s_hHead + 1) % H_LEN;
  if (s_hCount < H_LEN) s_hCount++;
  if (s_hCount < H_LEN) return false;

  uint8_t mid = (s_hHead + HAMPEL_K) % H_LEN;  // oldest is at s_hHead
  float w[H_LEN], d[H_LEN];
  memcpy(w, s_hX, sizeof w);
  float med = median(w, H_LEN);
  for (int i = 0; i < H_LEN; i++) d[i] = fabsf(s_hX[i] - med);
  float mad = median(d, H_LEN);
  tOut = s_hT[mid];
  xOut = fabsf(s_hX[mid] - med) > HAMPEL_SIGMA * 1.4826f * mad ? med : s_hX[mid];
  return true;
}

static void csiTask(void *arg) {
  CsiFrame f;
  for (;;) {
    if (xQueueReceive(s_queue, &f, portMAX_DELAY) != pdTRUE) continue;

    // Short frames (no full LLTF) still count for the rate, not the metric.
    bool full = f.len >= 128;
    uint8_t amps[CSI_NSUB];
    float feature = 0, filtered = 0, metric = 0;
    bool haveMetric = false;
    if (full) {
      feature = spatialStd(f.buf, amps);
      uint32_t tF;
      if (hampel((uint32_t)(f.t_us / 1000), feature, tF, filtered)) {
        metric = windowAdd(tF, filtered);
        haveMetric = true;
      }
    }

    portENTER_CRITICAL(&s_mux);
    if (full) {
      if (haveMetric) s_metric = metric;
      s_snap.frames++;
      s_snap.tMs = (uint32_t)(f.t_us / 1000);
      s_snap.feature = feature;
      s_snap.filtered = filtered;
      s_snap.metric = s_metric;
      s_snap.rssi = f.rssi;
      memcpy(s_snap.amps, amps, CSI_NSUB);
    }
    if (s_lastUs != 0) {
      uint32_t gap = (uint32_t)(f.t_us - s_lastUs);
      if (gap > s_maxGapUs) s_maxGapUs = gap;
    }
    s_lastUs  = f.t_us;
    s_count++;
    s_rssi    = f.rssi;
    s_channel = f.channel;
    CsiSnap snap = s_snap;
    portEXIT_CRITICAL(&s_mux);

    // Every full frame to the main loop for the raw stream. Never block.
    if (full && s_frameQ) xQueueSend(s_frameQ, &snap, 0);
  }
}

bool csiNextFrame(CsiSnap &out) {
  return s_frameQ && xQueueReceive(s_frameQ, &out, 0) == pdTRUE;
}

esp_err_t csiBegin(const uint8_t bssid[6]) {
  memcpy(s_bssid, bssid, 6);
  s_queue = xQueueCreate(CSI_QUEUE_LEN, sizeof(CsiFrame));
  if (!s_queue) return ESP_ERR_NO_MEM;
  if (RAW_STREAM) s_frameQ = xQueueCreate(32, sizeof(CsiSnap));
  xTaskCreatePinnedToCore(csiTask, "csi", 4096, nullptr, 5, nullptr, 1);

  wifi_csi_config_t cfg = {};
  cfg.lltf_en           = true;
  cfg.htltf_en          = false;
  cfg.stbc_htltf2_en    = false;
  cfg.ltf_merge_en      = false;
  cfg.channel_filter_en = false;
  cfg.manu_scale        = false;
  cfg.shift             = 0;

  esp_err_t err = esp_wifi_set_csi_config(&cfg);
  if (err != ESP_OK) return err;
  err = esp_wifi_set_csi_rx_cb(csiCallback, nullptr);
  if (err != ESP_OK) return err;
  return esp_wifi_set_csi(true);
}

// A torn copy while the callback reads only rejects a frame or two.
void csiSetBssid(const uint8_t bssid[6]) {
  memcpy(s_bssid, bssid, 6);
}

void csiSnapshot(CsiSnap &out) {
  portENTER_CRITICAL(&s_mux);
  out = s_snap;
  portEXIT_CRITICAL(&s_mux);
}

float csiMetric() {
  portENTER_CRITICAL(&s_mux);
  float m = s_metric;
  portEXIT_CRITICAL(&s_mux);
  return m;
}

void csiTakeStats(CsiStats &out) {
  int64_t now = esp_timer_get_time();
  portENTER_CRITICAL(&s_mux);
  uint32_t gap = s_maxGapUs;
  // A gap still in progress counts too, so a dead link shows up immediately.
  if (s_lastUs != 0 && (uint32_t)(now - s_lastUs) > gap) gap = (uint32_t)(now - s_lastUs);
  out.count    = s_count;
  out.maxGapMs = gap / 1000;
  out.rssi     = s_rssi;
  out.channel  = s_channel;
  s_count    = 0;
  s_maxGapUs = 0;
  portEXIT_CRITICAL(&s_mux);

  out.dropped  = s_dropped;  s_dropped  = 0;
  out.rejected = s_rejected; s_rejected = 0;
  memcpy(out.otherMac, s_otherMac, 6);
}
