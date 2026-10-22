"""Run haunt mode over a telemetry CSV: what would the head have done?

    py tools/tests/haunt_sim.py logs/unattended_20261020.csv --mean 0.0158 --std 0.0029
    py tools/tests/haunt_sim.py logs/baselines_20261020_1513.csv          # calibrate on 'empty'

Uses the recorded metric and rate, the Python detector (haunt on), and the
move planner with a fixed seed. Prints moves, freezes and time spent
moving, per label if the CSV has labels.
"""
import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detector as d  # noqa: E402
from nh_config import C  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--mean", type=float)
    ap.add_argument("--std", type=float)
    ap.add_argument("--cal-label", default="empty")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeline", action="store_true", help="print every event")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a config.h constant, e.g. --set LOW_RATIO=2.5")
    ap.add_argument("--quiet", action="store_true", help="only the per-label table")
    a = ap.parse_args()
    cfg = dict(C, HAUNT=1)
    for kv in a.set:
        k, v = kv.split("=")
        cfg[k] = float(v) if "." in v else int(v)

    rows = [r for r in csv.DictReader(open(a.csv, encoding="utf-8")) if r["kind"] == "T"]
    t = np.array([int(r["uptime_ms"]) for r in rows])
    m = np.array([float(r["metric"]) for r in rows])
    rate = np.array([int(r["rate"]) for r in rows])
    lab = [r["label"] or "(none)" for r in rows]
    if a.mean is None:
        cal = np.array([x for x, l, rt in zip(m, lab, rate) if l == a.cal_label and rt >= C["MIN_RATE"]])
        a.mean, a.std = float(cal.mean()), float(cal.std())
    low, high = d.thresholds(a.mean, a.std, cfg)
    if not a.quiet:
        print(f"mean {a.mean:.4f} std {a.std:.4f} -> LOW {low:.4f} HIGH {high:.4f}; "
              f"T_EMPTY {cfg['T_EMPTY_MS'] / 1000:.0f} s, gaps {cfg['HAUNT_GAP_MIN_MS'] / 1000:.0f}-"
              f"{cfg['HAUNT_GAP_MAX_MS'] / 1000:.0f} s, presence at {'LOW' if cfg['PRESENCE_AT_LOW'] else 'HIGH'}\n")

    rng = random.Random(a.seed)
    det = d.Detector(t[0], cfg)
    angle, target, ms, gap = C["ANGLE_START"], None, 0, C["HAUNT_GAP_MIN_MS"]
    move_start = move_end = -1
    moves, freezes, moving_ticks = Counter(), Counter(), Counter()
    kinds = Counter()
    for i in range(len(t)):
        now = t[i]
        busy = move_start <= now < move_end
        ev = det.step(now, m[i], rate[i], low, high, True, True, busy, gap)
        if ev & d.EV_TURN_START:
            target, ms, gap = d.plan_move(angle, rng.random, cfg)
            start_angle = angle
            move_start, move_end = now, now + abs(target - angle) * ms
            moves[lab[i]] += 1
            kinds["snap/twitch" if ms == cfg["SNAP_MS"] else "creep"] += 1
            if a.timeline:
                print(f"{(now - t[0]) / 1000:8.1f} s  move {angle:3d} -> {target:3d} at {ms:3d} ms/deg  [{lab[i]}]")
        if ev & d.EV_FROZEN:
            frac = min(1.0, (now - move_start) / max(1, move_end - move_start))
            angle = int(round(start_angle + (target - start_angle) * frac))
            move_end = now
            freezes[lab[i]] += 1
            if a.timeline:
                print(f"{(now - t[0]) / 1000:8.1f} s  FROZEN at {angle} (metric {m[i]:.4f})  [{lab[i]}]")
        if ev & d.EV_TURN_DONE:
            angle = target
        if busy:
            moving_ticks[lab[i]] += 1

    dur = Counter()
    for l, a_, b_ in zip(lab, t, np.append(t[1:], t[-1])):
        dur[l] += (b_ - a_) / 1000
    print(f"{'label':<16}{'minutes':>8}{'moves':>7}{'moves/min':>10}{'freezes':>9}{'moving %':>10}")
    for l in dict.fromkeys(lab):
        mins = dur[l] / 60
        print(f"{l:<16}{mins:8.1f}{moves[l]:7d}{moves[l] / max(mins, 1e-9):10.1f}{freezes[l]:9d}"
              f"{moving_ticks[l] / max(1, sum(1 for x in lab if x == l)) * 100:9.1f}%")
    if not a.quiet:
        print(f"\nmove kinds: {dict(kinds)}")


if __name__ == "__main__":
    main()
