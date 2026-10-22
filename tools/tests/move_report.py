"""What did the head actually do? Report from a telemetry CSV logged while
the servo was running.

    py tools/tests/move_report.py logs/away_servo_20261021.csv

Per move: start/end time, angle, duration, and whether it froze. Also:
reboots (a new session id = the Atom restarted, e.g. a servo brownout),
calibration events, and how much the head's own motion shows in the CSI
(metric during and right after moves vs the 5 s before).
"""
import csv
import sys
from collections import Counter

import numpy as np


def main():
    path = sys.argv[1]
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    tel = [r for r in rows if r["kind"] == "T"]
    if not tel:
        raise SystemExit("no telemetry")
    t0 = float(rows[0]["unix_time"])
    T = lambda r: float(r["unix_time"]) - t0  # noqa: E731

    sessions = list(dict.fromkeys(r["session"] for r in tel))
    print(f"{path}: {len(tel)} telemetry rows, {T(tel[-1]) / 60:.1f} min")
    if len(sessions) > 1:
        print(f"!! {len(sessions) - 1} reboot(s): sessions {sessions}")
        for s in sessions[1:]:
            first = next(r for r in tel if r["session"] == s)
            last_state = [r for r in tel if r["session"] != s and T(r) < T(first)][-1:]
            print(f"   reboot at {T(first):7.1f} s, last state before: "
                  f"{last_state[0]['state'] if last_state else '?'}")
    else:
        print("no reboots")

    events = [r for r in rows if r["kind"] == "E"]
    cal = [r for r in events if r["event"] == "calibrated"]
    for r in cal:
        print(f"calibrated at {T(r):.1f} s")
    print("event counts:", dict(Counter(r["event"] for r in events)))

    # pair turn_start with turn_done / frozen
    moves, cur = [], None
    for r in events:
        if r["event"] == "turn_start":
            cur = dict(start=T(r), target=int(r["angle"]))
        elif r["event"] in ("turn_done", "frozen") and cur:
            cur.update(end=T(r), angle=int(r["angle"]), how=r["event"])
            moves.append(cur)
            cur = None
    print(f"\n{len(moves)} moves")
    for mv in moves[:60]:
        print(f"  {mv['start']:7.1f} s  -> {mv['target']:4d}  ended {mv['how']:<9} at {mv['angle']:4d}  "
              f"{mv['end'] - mv['start']:5.1f} s")
    if len(moves) > 60:
        print(f"  ... {len(moves) - 60} more")

    # the head's own footprint in the CSI
    tt = np.array([T(r) for r in tel])
    m = np.array([float(r["metric"]) for r in tel])
    low = float(tel[-1]["low"])
    if moves and low > 0:
        before, during, after = [], [], []
        for mv in moves:
            sel = lambda a, b: m[(tt >= a) & (tt < b)]  # noqa: E731
            before.append(np.median(sel(mv["start"] - 5, mv["start"])) if len(sel(mv["start"] - 5, mv["start"])) else np.nan)
            during.append(np.max(sel(mv["start"], mv["end"] + 0.1)) if len(sel(mv["start"], mv["end"] + 0.1)) else np.nan)
            after.append(np.max(sel(mv["end"], mv["end"] + 2.5)) if len(sel(mv["end"], mv["end"] + 2.5)) else np.nan)
        b, d_, a = (np.nanmedian(x) / low for x in (before, during, after))
        print(f"\nhead's own footprint (x LOW = {low:.4f}): before median {b:.2f}, "
              f"during max {d_:.2f}, 2.5 s after max {a:.2f}")
        frozen = [mv for mv in moves if mv["how"] == "frozen"]
        print(f"frozen moves: {len(frozen)} of {len(moves)}")


if __name__ == "__main__":
    main()
