// Calibration: countdown to leave the room, then record the empty-room metric.
#pragma once
#include <stdint.h>

enum CalPhase : uint8_t { CAL_IDLE, CAL_LEAVE, CAL_RECORD };
enum CalResult : uint8_t { CAL_NONE, CAL_RUNNING, CAL_DONE, CAL_FAILED };

void calStart(uint32_t now);
void calCancel();
CalPhase calPhase();
uint32_t calSecondsLeft(uint32_t now);

// 10 Hz tick. On CAL_DONE, mean and std hold the result.
CalResult calStep(uint32_t now, float metric, uint16_t rate, float &mean, float &std);
