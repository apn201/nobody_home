"""Python copy of firmware/src/detector.cpp. Same logic, same constants
(read from config.h). Keep the two in step: change one, change both.
"""
from nh_config import C

STALE, ACTIVE, QUIET_PENDING, EMPTY, TURNING, SETTLING = range(6)
NAMES = ["STALE", "ACTIVE", "QUIET_PENDING", "EMPTY", "TURNING", "SETTLING"]

EV_TURN_START, EV_TURN_DONE, EV_STALE, EV_REARMED, EV_FROZEN = 1, 2, 4, 8, 16


class Detector:
    def __init__(self, now, c=C):
        self.c = c
        self.state = ACTIVE        # boot: whoever plugged it in is in the room
        self.armed = False
        self.state_since = now
        self.quiet_since = now
        self.low_rate = False
        self.low_rate_since = now
        self.high_run = False
        self.high_since = now
        self.has_turned = False
        self.last_turn_done = now
        self.next_move_at = now   # haunt: when the next move is due while EMPTY
        self.last_strong = None   # haunt: last time someone surely moved in the room

    def _enter(self, s, now):
        self.state = s
        self.state_since = now

    def quiet_ms(self, now):
        return now - self.quiet_since if self.state in (QUIET_PENDING, EMPTY) else 0

    def step(self, now, metric, rate, low, high, calibrated, can_turn, move_busy, gap_ms=None):
        """One 10 Hz tick. Returns a bitmask of EV_* events. gap_ms: in haunt
        mode, the pause before the next move once this one has settled (the
        device passes a random value)."""
        c, ev = self.c, 0
        if gap_ms is None:
            gap_ms = c["HAUNT_GAP_MIN_MS"]
        # Haunt + PRESENCE_AT_LOW: any disturbance above LOW counts as someone here.
        presence = low if (c["HAUNT"] and c["PRESENCE_AT_LOW"]) else high

        # Someone is near while the head moves: stop dead in whatever pose it
        # has reached. The turn stays owed (armed), so it carries on next absence.
        if self.state == TURNING:
            freeze_at = min(presence, high if c["FREEZE_ABOVE_HIGH"] else low)
            if c["FREEZE_ON_MOTION"] and metric > freeze_at:
                self.armed = True
                self.high_run = False
                self._enter(ACTIVE, now)
                return ev | EV_FROZEN
            # The head settling is motion near the antenna: ignore CSI after it.
            if not move_busy:
                self.has_turned = True
                self.last_turn_done = now
                self._enter(SETTLING, now)
                ev |= EV_TURN_DONE
            return ev
        if self.state == SETTLING:
            if now - self.state_since >= c["T_SETTLE_MS"]:
                self._enter(EMPTY, now)
                self.next_move_at = now + gap_ms
                self.high_run = False
                self.low_rate = False
            return ev

        # Missing data is never an empty room. Fail safe means fail still.
        if rate < c["MIN_RATE"]:
            if not self.low_rate:
                self.low_rate = True
                self.low_rate_since = now
        else:
            self.low_rate = False
        if self.state == STALE:
            if not self.low_rate:
                self._enter(ACTIVE, now)
            return ev
        if self.low_rate and now - self.low_rate_since > c["T_STALE_MS"]:
            self._enter(STALE, now)
            self.high_run = False
            return ev | EV_STALE

        if not calibrated:
            return ev  # no thresholds yet: stay as we are, never turn

        # A big disturbance means someone was surely here, and may now sit still.
        if metric > high * c["STRONG_X_HIGH"]:
            self.last_strong = now
        strong_recent = (c["HAUNT"] and self.last_strong is not None
                         and now - self.last_strong < c["T_AFTER_STRONG_MS"])

        # Re-arm: someone came back and moved, above HIGH continuously for T_REARM.
        if metric > high:
            if not self.high_run:
                self.high_run = True
                self.high_since = now
            if not self.armed and now - self.high_since >= c["T_REARM_MS"]:
                self.armed = True
                ev |= EV_REARMED
        else:
            self.high_run = False

        if self.state == ACTIVE:
            if metric < low:
                self._enter(QUIET_PENDING, now)
                self.quiet_since = now
        elif self.state == QUIET_PENDING:
            if metric > presence:
                self._enter(ACTIVE, now)
            elif now - self.quiet_since >= c["T_EMPTY_MS"] and not strong_recent:
                self._enter(EMPTY, now)
                self.next_move_at = now  # haunt: first move right away
        elif self.state == EMPTY:
            if metric > presence:
                self._enter(ACTIVE, now)
            elif c["HAUNT"]:
                if can_turn and now >= self.next_move_at:
                    self._enter(TURNING, now)
                    ev |= EV_TURN_START
            elif (self.armed and can_turn and
                  (not self.has_turned or now - self.last_turn_done >= c["T_COOLDOWN_MS"])):
                self.armed = False
                self._enter(TURNING, now)
                ev |= EV_TURN_START
        return ev


def plan_move(angle, rnd, c=C):
    """Haunt mode: where to go, how fast, and how long to wait after.
    Mirrors hauntPlan() in firmware/src/haunt.cpp. rnd() -> uniform [0, 1).
    Returns (target_deg, ms_per_deg, gap_ms)."""
    lo, hi = c["POSE_MIN_DEG"], c["POSE_MAX_DEG"]
    if rnd() * 100 < c["P_TWITCH_PCT"]:
        step = c["TWITCH_DEG"] if angle + c["TWITCH_DEG"] <= hi else -c["TWITCH_DEG"]
        if rnd() < 0.5 and angle - c["TWITCH_DEG"] >= lo:
            step = -c["TWITCH_DEG"]
        target, ms = angle + step, c["SNAP_MS"]
    else:
        target = None
        if rnd() * 100 < c["P_CAMERA_PCT"] and abs(c["CAMERA_DEG"] - angle) >= c["MIN_MOVE_DEG"]:
            target = c["CAMERA_DEG"]
        for _ in range(8):
            if target is not None:
                break
            t = lo + int(rnd() * (hi - lo + 1))
            if abs(t - angle) >= c["MIN_MOVE_DEG"]:
                target = t
        if target is None:  # pathological range: go to the far end
            target = lo if angle - lo > hi - angle else hi
        if rnd() * 100 < c["P_SNAP_PCT"]:
            ms = c["SNAP_MS"]
        else:
            ms = c["CREEP_MS_MIN"] + int(rnd() * (c["CREEP_MS_MAX"] - c["CREEP_MS_MIN"] + 1))
    gap = c["HAUNT_GAP_MIN_MS"] + int(rnd() * (c["HAUNT_GAP_MAX_MS"] - c["HAUNT_GAP_MIN_MS"] + 1))
    return int(target), int(ms), int(gap)


def thresholds(mean, std, c=C):
    """LOW and HIGH from a calibration: mean + K * std, but never closer to
    the mean than LOW_RATIO / HIGH_RATIO times it (the empty-room metric has
    heavy tails that a 60 s std misses)."""
    std = max(std, mean * c["CAL_MIN_STD_FRAC"])
    low = max(mean + c["K_LOW"] * std, mean * c["LOW_RATIO"])
    high = max(mean + c["K_HIGH"] * std, mean * c["HIGH_RATIO"])
    return low, high
