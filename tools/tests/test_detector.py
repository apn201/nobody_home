"""Rule tests for the detector, on synthetic data.

    py -m unittest discover -s tools/tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detector as d  # noqa: E402
from nh_config import C  # noqa: E402

LOW, HIGH = 1.0, 2.0
QUIET, WALK = 0.5, 3.0
TICK = 100
MOVE_MS = C["ANGLE_STEP"] // C["DEG_PER_STEP"] * C["STEP_MS"]


class Sim:
    """Drives a Detector at 10 Hz with a fake motor."""

    def __init__(self, calibrated=True, can_turn=True, haunt=False, gap_ms=10000):
        self.t = 0
        self.det = d.Detector(0, dict(C, HAUNT=int(haunt)))
        self.calibrated, self.can_turn, self.gap_ms = calibrated, can_turn, gap_ms
        self.move_until = -1
        self.turns = []     # times of EV_TURN_START
        self.events = []

    def run(self, ms, metric, rate=100):
        for _ in range(int(ms // TICK)):
            self.t += TICK
            busy = self.t < self.move_until
            ev = self.det.step(self.t, metric, rate, LOW, HIGH, self.calibrated, self.can_turn, busy,
                               self.gap_ms)
            if ev & d.EV_TURN_START:
                self.turns.append(self.t)
                self.move_until = self.t + MOVE_MS
            if ev & d.EV_FROZEN:
                self.move_until = -1  # motor stopped where it was
            if ev:
                self.events.append((self.t, ev))
        return self


def sec(s):
    return s * 1000


class DetectorRules(unittest.TestCase):
    def test_boot_disarmed_never_turns(self):
        s = Sim().run(sec(600), QUIET)
        self.assertEqual(s.turns, [])
        self.assertFalse(s.det.armed)

    def test_walk_then_leave_turns_after_t_empty(self):
        s = Sim().run(sec(10), WALK)
        self.assertTrue(s.det.armed)
        left = s.t
        s.run(sec(60), QUIET)
        self.assertEqual(len(s.turns), 1)
        delay = s.turns[0] - left
        self.assertGreaterEqual(delay, C["T_EMPTY_MS"])
        self.assertLess(delay, C["T_EMPTY_MS"] + 1000)

    def test_walking_with_dips_never_turns(self):
        s = Sim()
        for _ in range(300):  # 10 min: 1.5 s moving, 0.5 s dip below LOW
            s.run(1500, WALK).run(500, QUIET)
        self.assertEqual(s.turns, [])

    def test_mid_band_does_not_reset_quiet(self):
        # Between LOW and HIGH is hysteresis: counts as still quiet.
        s = Sim().run(sec(10), WALK).run(sec(5), QUIET).run(sec(25), (LOW + HIGH) / 2)
        self.assertEqual(len(s.turns), 1)

    def test_rearm_needs_continuous_high(self):
        s = Sim()
        for _ in range(60):  # spikes above HIGH, never 3 s in a row
            s.run(2000, WALK).run(300, QUIET)
        self.assertFalse(s.det.armed)

    def test_stale_never_turns(self):
        s = Sim().run(sec(10), WALK).run(sec(120), QUIET, rate=0)
        self.assertEqual(s.turns, [])
        self.assertEqual(s.det.state, d.STALE)
        self.assertTrue(any(ev & d.EV_STALE for _, ev in s.events))

    def test_stale_restarts_quiet_timer(self):
        s = Sim().run(sec(10), WALK).run(C["T_EMPTY_MS"] - 3000, QUIET).run(sec(5), QUIET, rate=0)
        back = s.t
        s.run(sec(60), QUIET)
        self.assertEqual(len(s.turns), 1)
        self.assertGreaterEqual(s.turns[0] - back, C["T_EMPTY_MS"])

    def test_short_rate_dip_is_not_stale(self):
        s = Sim().run(sec(10), WALK)
        left = s.t
        s.run(C["T_EMPTY_MS"] - 3000, QUIET).run(1500, QUIET, rate=0).run(sec(30), QUIET)
        self.assertEqual(len(s.turns), 1)
        # the 1.5 s dip did not restart the quiet timer
        self.assertLess(s.turns[0] - left, C["T_EMPTY_MS"] + 1000)

    def test_one_turn_per_absence(self):
        s = Sim().run(sec(10), WALK).run(sec(1800), QUIET)
        self.assertEqual(len(s.turns), 1)

    def test_settling_ignores_own_motion(self):
        s = Sim().run(sec(10), WALK).run(C["T_EMPTY_MS"] + 200, QUIET)
        self.assertEqual(len(s.turns), 1)
        s.run(MOVE_MS, QUIET)  # turn completes undisturbed
        s.run(C["T_SETTLE_MS"] - 500, WALK)  # the head settling looks like walking
        self.assertFalse(s.det.armed)
        s.run(sec(60), QUIET)
        self.assertEqual(len(s.turns), 1)

    def test_cooldown_between_turns(self):
        s = Sim().run(sec(10), WALK).run(sec(30), QUIET)
        self.assertEqual(len(s.turns), 1)
        s.run(sec(5), WALK).run(sec(30), QUIET)  # back, moved, left again quickly
        done = s.turns[0] + MOVE_MS
        s.run(sec(120), QUIET)
        self.assertEqual(len(s.turns), 2)
        self.assertGreaterEqual(s.turns[1] - done, C["T_COOLDOWN_MS"])

    def test_freeze_mid_turn_and_resume_later(self):
        s = Sim().run(sec(10), WALK).run(C["T_EMPTY_MS"] + 200, QUIET)
        self.assertEqual(s.det.state, d.TURNING)
        s.run(500, WALK)  # someone at the door while the head moves
        self.assertTrue(any(ev & d.EV_FROZEN for _, ev in s.events))
        self.assertEqual(s.det.state, d.ACTIVE)
        self.assertTrue(s.det.armed)  # the turn is still owed
        s.run(sec(60), QUIET)  # they leave again
        self.assertEqual(len(s.turns), 2)

    def test_freeze_threshold_follows_config(self):
        # Mid-band (above LOW, below HIGH) freezes only when FREEZE_ABOVE_HIGH is 0.
        s = Sim().run(sec(10), WALK).run(C["T_EMPTY_MS"] + 200, QUIET)
        s.run(300, (LOW + HIGH) / 2)
        frozen = any(ev & d.EV_FROZEN for _, ev in s.events)
        self.assertEqual(frozen, not C["FREEZE_ABOVE_HIGH"])

    def test_cannot_turn_at_end_angle(self):
        s = Sim(can_turn=False).run(sec(10), WALK).run(sec(120), QUIET)
        self.assertEqual(s.turns, [])
        self.assertEqual(s.det.state, d.EMPTY)

    def test_uncalibrated_never_turns(self):
        s = Sim(calibrated=False).run(sec(10), WALK).run(sec(120), QUIET)
        self.assertEqual(s.turns, [])

    def test_thresholds_std_floor(self):
        low, high = d.thresholds(0.1, 0.0)
        self.assertGreater(low, 0.1)
        self.assertGreater(high, low)

    def test_thresholds_ratio_floor(self):
        # A tight calibration std must not put HIGH right on top of the mean.
        low, high = d.thresholds(0.0158, 0.0029)
        self.assertAlmostEqual(low, 0.0158 * C["LOW_RATIO"])
        self.assertAlmostEqual(high, 0.0158 * C["HIGH_RATIO"])


class HauntMode(unittest.TestCase):
    """Video mode: move soon after the room empties, keep moving, freeze on presence."""

    def test_first_move_soon_after_room_empties(self):
        s = Sim(haunt=True).run(sec(10), WALK)
        left = s.t
        s.run(sec(20), QUIET)
        self.assertGreaterEqual(len(s.turns), 1)
        delay = s.turns[0] - left
        self.assertGreaterEqual(delay, C["T_EMPTY_MS"])
        self.assertLess(delay, C["T_EMPTY_MS"] + 500)

    def test_no_arming_needed(self):
        # Plugged in and left alone: it starts haunting without anyone walking first.
        s = Sim(haunt=True).run(sec(30), QUIET)
        self.assertGreaterEqual(len(s.turns), 1)

    def test_keeps_moving_while_empty(self):
        gap = 10000
        s = Sim(haunt=True, gap_ms=gap).run(sec(300), QUIET)
        cycle = MOVE_MS + C["T_SETTLE_MS"] + gap
        expected = (300000 - C["T_EMPTY_MS"]) // cycle
        self.assertGreaterEqual(len(s.turns), expected)
        self.assertLessEqual(len(s.turns), expected + 1)
        gaps = [b - a for a, b in zip(s.turns, s.turns[1:])]
        self.assertTrue(all(g >= gap for g in gaps))

    def test_never_moves_while_someone_moves(self):
        s = Sim(haunt=True)
        for _ in range(150):  # 5 min of walking with short dips below LOW
            s.run(1500, WALK).run(500, QUIET)
        self.assertEqual(s.turns, [])

    def test_freeze_immediately_then_resume(self):
        s = Sim(haunt=True).run(C["T_EMPTY_MS"] + 200, QUIET)
        self.assertEqual(s.det.state, d.TURNING)
        s.run(TICK, WALK)  # someone comes near mid-move: one tick is enough
        self.assertTrue(any(ev & d.EV_FROZEN for _, ev in s.events))
        self.assertEqual(s.det.state, d.ACTIVE)
        n = len(s.turns)
        s.run(C["T_EMPTY_MS"] + 500, QUIET)  # they leave: it carries on
        self.assertEqual(len(s.turns), n + 1)

    def test_small_disturbance_blocks_moves(self):
        # Above LOW but below HIGH (fidgeting): with PRESENCE_AT_LOW no move, and a move freezes.
        mid = (LOW + HIGH) / 2
        s = Sim(haunt=True)
        for _ in range(60):  # 2 min: mostly quiet, a small disturbance every 5 s
            s.run(4500, QUIET).run(500, mid)
        self.assertEqual(len(s.turns) == 0, bool(C["PRESENCE_AT_LOW"]))

    def test_waits_longer_after_someone_surely_came_in(self):
        strong = HIGH * C["STRONG_X_HIGH"] * 1.5
        s = Sim(haunt=True).run(sec(3), strong)  # someone walks in, then sits perfectly still
        came = s.t
        s.run(sec(60), QUIET)
        self.assertGreaterEqual(len(s.turns), 1)
        self.assertGreaterEqual(s.turns[0] - came, C["T_AFTER_STRONG_MS"])

    def test_haunt_stale_never_moves(self):
        s = Sim(haunt=True).run(sec(120), QUIET, rate=0)
        self.assertEqual(s.turns, [])

    def test_haunt_uncalibrated_never_moves(self):
        s = Sim(haunt=True, calibrated=False).run(sec(120), QUIET)
        self.assertEqual(s.turns, [])

    def test_haunt_respects_can_turn(self):
        # Calibration countdown or button reset in progress: hold still.
        s = Sim(haunt=True, can_turn=False).run(sec(120), QUIET)
        self.assertEqual(s.turns, [])


if __name__ == "__main__":
    unittest.main()
