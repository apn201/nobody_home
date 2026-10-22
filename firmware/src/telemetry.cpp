#include "telemetry.h"

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_random.h>

#define TELEMETRY_PORT 20003

// Little-endian on the wire, which is what the S3 is natively.
struct __attribute__((packed)) Header {
  uint8_t  magic;   // 'N'
  uint8_t  type;
  uint16_t session;
};

struct __attribute__((packed)) TelemetryPacket {
  Header   h;
  uint32_t seq, uptimeMs;
  uint16_t rate;
  float    metric, low, high;
  uint8_t  state, armed;
  uint32_t quietMs;
  int16_t  angle;
  int8_t   rssi;
};
static_assert(sizeof(TelemetryPacket) == 35, "telemetry layout");

struct __attribute__((packed)) EventPacket {
  Header   h;
  uint32_t seq, uptimeMs;
  uint8_t  code;
  int16_t  angle;
};
static_assert(sizeof(EventPacket) == 15, "event layout");

struct __attribute__((packed)) RawPacket {
  Header   h;
  uint32_t seq, uptimeMs;
  uint32_t frames;
  float    feature, filtered, metric;
  int8_t   rssi;
  uint8_t  nsub;
  uint8_t  amps[CSI_NSUB];
};
static_assert(sizeof(RawPacket) == 30 + CSI_NSUB, "raw layout");

static WiFiUDP   s_udp;
static IPAddress s_pc;
static uint16_t  s_session;
static uint32_t  s_seq;
static bool      s_ok;

// A scope anywhere on the LAN can subscribe by sending a hello ('N', 0x10)
// to port 20003 now and then. We stream to it as well as to PC_IP until
// the hellos stop.
#define SUB_TIMEOUT_MS 10000
static IPAddress s_sub;
static uint32_t  s_subUntil;
static bool      s_subOn;

void telemetryBegin(const char *pcIp) {
  s_ok = s_pc.fromString(pcIp);
  s_session = (uint16_t)esp_random();
  s_udp.begin(TELEMETRY_PORT);
}

void telemetryPoll(uint32_t now) {
  while (s_udp.parsePacket() > 0) {
    uint8_t b[4];
    int n = s_udp.read(b, sizeof b);
    if (n == 4 && b[0] == 'N' && b[1] == 0x10) {
      IPAddress ip = s_udp.remoteIP();
      if (!s_subOn || ip != s_sub) Serial.printf("scope subscribed: %s\n", ip.toString().c_str());
      s_sub = ip;
      s_subUntil = now + SUB_TIMEOUT_MS;
      s_subOn = true;
    }
  }
  if (s_subOn && (int32_t)(now - s_subUntil) > 0) {
    s_subOn = false;
    Serial.printf("scope %s gone\n", s_sub.toString().c_str());
  }
}

static void sendTo(const IPAddress &ip, const void *pkt, size_t len) {
  s_udp.beginPacket(ip, TELEMETRY_PORT);
  s_udp.write((const uint8_t *)pkt, len);
  s_udp.endPacket();
}

static void send(const void *pkt, size_t len) {
  if (WiFi.status() != WL_CONNECTED) return;
  if (s_ok) sendTo(s_pc, pkt, len);
  if (s_subOn && !(s_ok && s_sub == s_pc)) sendTo(s_sub, pkt, len);
}

void telemetrySend(const TelemetryData &d) {
  TelemetryPacket p;
  p.h = {'N', 0x01, s_session};
  p.seq = s_seq++;
  p.uptimeMs = d.uptimeMs;
  p.rate = d.rate;
  p.metric = d.metric;
  p.low = d.low;
  p.high = d.high;
  p.state = d.state;
  p.armed = d.armed;
  p.quietMs = d.quietMs;
  p.angle = d.angle;
  p.rssi = d.rssi;
  send(&p, sizeof p);
}

// Only to a subscribed scope: ~100 packets/s is airtime the pings need.
void telemetryRaw(const CsiSnap &s) {
  if (!s_subOn || WiFi.status() != WL_CONNECTED) return;
  RawPacket p;
  p.h = {'N', 0x03, s_session};
  p.seq = s_seq++;
  p.uptimeMs = s.tMs;
  p.frames = s.frames;
  p.feature = s.feature;
  p.filtered = s.filtered;
  p.metric = s.metric;
  p.rssi = s.rssi;
  p.nsub = CSI_NSUB;
  memcpy(p.amps, s.amps, CSI_NSUB);
  sendTo(s_sub, &p, sizeof p);
}

void telemetryEvent(EventCode code, int16_t angle) {
  EventPacket p;
  p.h = {'N', 0x02, s_session};
  p.seq = s_seq++;
  p.uptimeMs = millis();
  p.code = code;
  p.angle = angle;
  send(&p, sizeof p);
}
