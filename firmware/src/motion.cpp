#include "motion.h"
#include "config.h"
#include <Arduino.h>

#define SERVO_FREQ 50
#define SERVO_BITS 14

static float    s_from, s_to, s_pos;
static uint32_t s_start, s_duration;
static bool     s_moving;
static bool     s_attached;
static uint32_t s_holdUntil;  // 0 = no hold pending

static int16_t clampDeg(int32_t d) {
  return d < SERVO_MIN_DEG ? SERVO_MIN_DEG : d > SERVO_MAX_DEG ? SERVO_MAX_DEG : d;
}

static void writeAngle(float deg) {
  s_pos = deg;
#if SERVO_ENABLED
  if (!s_attached) {
    s_attached = ledcAttach(SERVO_PIN, SERVO_FREQ, SERVO_BITS);
    if (!s_attached) return;
  }
  float us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * deg / 180.0f;
  ledcWrite(SERVO_PIN, (uint32_t)(us * ((1 << SERVO_BITS) - 1) / (1000000.0f / SERVO_FREQ)));
#endif
}

void release() {
  s_moving = false;
  s_holdUntil = 0;
  s_from = s_to = s_pos;
#if SERVO_ENABLED
  if (s_attached) ledcDetach(SERVO_PIN);
#endif
  s_attached = false;
  pinMode(SERVO_PIN, OUTPUT);  // a floating signal line makes some servos twitch
  digitalWrite(SERVO_PIN, LOW);
}

void motionBegin(int16_t assumedAngle) {
  s_from = s_to = s_pos = assumedAngle;
  pinMode(SERVO_PIN, OUTPUT);  // LOW, no pulses: the servo stays where it is
  digitalWrite(SERVO_PIN, LOW);
}

void moveTo(int16_t deg, uint16_t stepMs) {
  s_from = s_pos;
  s_to = clampDeg(deg);
  s_start = millis();
  s_duration = (uint32_t)(fabsf(s_to - s_from) / DEG_PER_STEP * stepMs);
  s_moving = true;
  s_holdUntil = 0;
  writeAngle(s_from);  // first pulse at the current angle, so attaching does not jump
}

void stop() {
  if (!s_moving) return;
  s_moving = false;
  s_from = s_to = s_pos;  // stay exactly here
  s_holdUntil = millis() + SERVO_HOLD_MS;
}

bool isBusy() {
  return s_moving;
}

void motionUpdate(uint32_t now) {
  if (s_moving) {
    uint32_t el = now - s_start;
    if (el >= s_duration) {
      writeAngle(s_to);
      s_moving = false;
      s_holdUntil = now + SERVO_HOLD_MS;
    } else {
      float x = (float)el / s_duration;
      float e = x * x * (3 - 2 * x);  // smoothstep: slow start, slow stop
      writeAngle(s_from + (s_to - s_from) * e);
    }
  }
  // Hold the last pulse a moment, then stop the signal: no hum at rest.
  if (s_holdUntil && (int32_t)(now - s_holdUntil) >= 0) release();
}

int16_t motionAngle() {
  return (int16_t)lroundf(s_pos);
}
