#include "traffic.h"

#include <ping/ping_sock.h>
#include <lwip/ip_addr.h>

static esp_ping_handle_t s_ping;
static volatile uint32_t s_replies;
static volatile uint32_t s_timeouts;

static void onSuccess(esp_ping_handle_t h, void *arg) { s_replies++; }
static void onTimeout(esp_ping_handle_t h, void *arg) { s_timeouts++; }

esp_err_t trafficBegin(const IPAddress &target, uint32_t intervalMs) {
  esp_ping_config_t cfg = ESP_PING_DEFAULT_CONFIG();
  cfg.count       = ESP_PING_COUNT_INFINITE;
  cfg.interval_ms = intervalMs;
  // esp_ping waits for each reply (or the timeout) before the next request,
  // so one lost reply used to cost a 1 s hole in the CSI. Give up fast.
  cfg.timeout_ms  = 100;
  cfg.data_size   = 1;
  cfg.task_prio   = 4;
  if (!ipaddr_aton(target.toString().c_str(), &cfg.target_addr)) return ESP_ERR_INVALID_ARG;

  esp_ping_callbacks_t cbs = {};
  cbs.on_ping_success = onSuccess;
  cbs.on_ping_timeout = onTimeout;

  esp_err_t err = esp_ping_new_session(&cfg, &cbs, &s_ping);
  if (err != ESP_OK) return err;
  return esp_ping_start(s_ping);
}

void trafficTakeStats(uint32_t &replies, uint32_t &timeouts) {
  replies  = s_replies;  s_replies  = 0;
  timeouts = s_timeouts; s_timeouts = 0;
}
