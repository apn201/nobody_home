// Head motion behind an interface, so the SG90 or a 28BYJ-48 stepper can sit
// behind it. With SERVO_ENABLED 0 it only keeps time: no PWM ever reaches the pin.
#pragma once
#include <stdint.h>

void motionBegin(int16_t assumedAngle);    // boot never moves: trust where it was left
void moveTo(int16_t deg, uint16_t stepMs); // eased move at 1 deg per stepMs (DEG_PER_STEP scaled)
void stop();                               // halt where it is now (freeze), hold, then go limp
void release();                            // stop the signal immediately (phase 7: lifted)
bool isBusy();                             // true while moving; the hold after it does not count
void motionUpdate(uint32_t now);           // call every loop: steps the easing, ends the hold
int16_t motionAngle();                     // where the head is (commanded), degrees
