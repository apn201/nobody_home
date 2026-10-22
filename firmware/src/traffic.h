// Ping generator to the router. The replies are the frames CSI measures.
#pragma once
#include <stdint.h>
#include <esp_err.h>
#include <IPAddress.h>

esp_err_t trafficBegin(const IPAddress &target, uint32_t intervalMs);

// Ping replies and timeouts since the previous call.
void trafficTakeStats(uint32_t &replies, uint32_t &timeouts);
