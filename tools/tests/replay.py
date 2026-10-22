"""Replay a telemetry CSV through the Python detector.

    py tools/tests/replay.py logs/baselines_20261020_1513.csv
    py tools/tests/replay.py logs/x.csv --cal logs/baselines_20261020_1513.csv
    py tools/tests/replay.py logs/x.csv --device    # thresholds as logged; compare states

Thresholds come from the "empty" rows of the --cal CSV (default: the same
CSV), the way the device calibrates: mean and std of the metric on ticks
with a good rate.

Two runs:
  continuous   the whole file as one evening, boot disarmed, as the device would.
  per segment  each labelled segment alone, starting armed ("someone just
               left"). This is the phase 3 gate: walking must never turn,
               empty must turn.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detector as d  # noqa: E402
from nh_config import C  # noqa: E402

MOVE_MS = abs(C["ANGLE_STEP"]) // C["DEG_PER_STEP"] * C["STEP_MS"]


def load(path):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["kind"] == "T"]
    sessions = {r["session"] for r in rows}
    if len(sessions) > 1:
        print(f"warning: {len(sessions)} device sessions in {path}, time may jump", file=sys.stderr)
    return [dict(t=int(r["uptime_ms"]), metric=float(r["metric"]), rate=int(r["rate"]),
                 label=r["label"] or "(none)", state=r["state"],
                 low=float(r["low"]), high=float(r["high"])) for r in rows]


def calibrate(rows, label):
    m = np.array([r["metric"] for r in rows if r["label"] == label and r["rate"] >= C["MIN_RATE"]])
    if len(m) < 50:
        raise SystemExit(f"not enough '{label}' rows to calibrate ({len(m)})")
    low, high = d.thresholds(m.mean(), m.std())
    return m.mean(), m.std(), low, high


def run(rows, low, high, armed=False, can_turn=True, fixed=None):
    """Returns (turn rows, list of replayed state names)."""
    det = d.Detector(rows[0]["t"])
    det.armed = armed
    move_until, turns, states = -1, [], []
    for r in rows:
        lo, hi = (r["low"], r["high"]) if fixed else (low, high)
        ev = det.step(r["t"], r["metric"], r["rate"], lo, hi, hi > 0, can_turn, r["t"] < move_until)
        if ev & d.EV_TURN_START:
            turns.append(r)
            move_until = r["t"] + MOVE_MS
        if ev & d.EV_FROZEN:
            move_until = -1
        states.append(d.NAMES[det.state])
    return turns, states


def segments(rows):
    out, start = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i]["label"] != rows[start]["label"]:
            out.append(rows[start:i])
            start = i
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--cal", help="CSV whose 'empty' rows set the thresholds (default: same CSV)")
    ap.add_argument("--cal-label", default="empty")
    ap.add_argument("--device", action="store_true", help="use logged LOW/HIGH, compare states with the device")
    a = ap.parse_args()

    rows = load(a.csv)
    t0 = rows[0]["t"]
    if a.device:
        low = high = None
        print("thresholds: as logged by the device")
    else:
        mean, std, low, high = calibrate(load(a.cal) if a.cal else rows, a.cal_label)
        print(f"calibration from '{a.cal_label}' in {Path(a.cal or a.csv).name}: "
              f"mean {mean:.4f} std {std:.4f} -> LOW {low:.4f} HIGH {high:.4f}")
    print(f"T_EMPTY {C['T_EMPTY_MS'] / 1000:.0f} s, T_REARM {C['T_REARM_MS'] / 1000:.0f} s, "
          f"T_COOLDOWN {C['T_COOLDOWN_MS'] / 1000:.0f} s, K {C['K_LOW']}/{C['K_HIGH']}\n")

    turns, states = run(rows, low, high, fixed=a.device)
    print("continuous (boot disarmed):")
    if not turns:
        print("  no turns")
    for r in turns:
        print(f"  turn at {(r['t'] - t0) / 1000:6.1f} s  during '{r['label']}'")

    if a.device:
        same = sum(1 for r, s in zip(rows, states) if r["state"] == s)
        print(f"\nstate match with device: {same}/{len(rows)} ticks ({same / len(rows) * 100:.1f}%)")
        bad = [(r, s) for r, s in zip(rows, states) if r["state"] != s][:5]
        for r, s in bad:
            print(f"  {(r['t'] - t0) / 1000:7.1f} s device {r['state']:<14} replay {s}")

    print("\nper segment (starts armed):")
    ok = True
    for seg in segments(rows):
        lab = seg[0]["label"]
        if lab == "transition":
            continue
        tt, _ = run(seg, low, high, armed=True, fixed=a.device)
        dur = (seg[-1]["t"] - seg[0]["t"]) / 1000
        first = f"first after {(tt[0]['t'] - seg[0]['t']) / 1000:5.1f} s" if tt else "-"
        verdict = ""
        if lab.startswith(("walk", "fidget", "kids", "hallway")):
            verdict = "ok" if not tt else "FAIL (turned while someone walked)"
            ok &= not tt
        elif lab.startswith("empty"):
            verdict = "ok" if tt else "FAIL (empty room, no turn)"
            ok &= bool(tt)
        elif lab.startswith("sitting"):
            verdict = "turned toward a still person (wanted)" if tt else "no turn"
        print(f"  {lab:<15} {dur:5.0f} s  turns {len(tt)}  {first:<20} {verdict}")

    print(f"\nGATE {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
