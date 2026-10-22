// NVS: calibration and the AP it belongs to; angle in phase 4, diary in phase 6.
#pragma once
#include <stdint.h>

void storeBegin();
bool storeLoadCalibration(float &mean, float &std);
void storeSaveCalibration(float mean, float std);

// Head angle after the last completed or frozen move. Boot trusts it and never moves.
bool storeLoadAngle(int16_t &deg);
void storeSaveAngle(int16_t deg);

// The AP the calibration was made on. CSI thresholds only hold for that link.
bool storeLoadAp(uint8_t bssid[6], uint8_t &channel);
void storeSaveAp(const uint8_t bssid[6], uint8_t channel);
