#include "store.h"
#include <Preferences.h>

static Preferences s_prefs;

void storeBegin() {
  s_prefs.begin("nobody", false);
}

bool storeLoadCalibration(float &mean, float &std) {
  if (!s_prefs.getBool("cal_ok", false)) return false;
  mean = s_prefs.getFloat("cal_mean", 0);
  std  = s_prefs.getFloat("cal_std", 0);
  return mean > 0;
}

void storeSaveCalibration(float mean, float std) {
  s_prefs.putFloat("cal_mean", mean);
  s_prefs.putFloat("cal_std", std);
  s_prefs.putBool("cal_ok", true);
}

bool storeLoadAngle(int16_t &deg) {
  if (!s_prefs.isKey("angle")) return false;
  deg = s_prefs.getShort("angle", 0);
  return true;
}

void storeSaveAngle(int16_t deg) {
  s_prefs.putShort("angle", deg);
}

bool storeLoadAp(uint8_t bssid[6], uint8_t &channel) {
  if (s_prefs.getBytes("ap_bssid", bssid, 6) != 6) return false;
  channel = s_prefs.getUChar("ap_ch", 0);
  return channel != 0;
}

void storeSaveAp(const uint8_t bssid[6], uint8_t channel) {
  s_prefs.putBytes("ap_bssid", bssid, 6);
  s_prefs.putUChar("ap_ch", channel);
}
