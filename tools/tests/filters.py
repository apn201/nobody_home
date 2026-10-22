"""Compare feature pipelines on an every-frame recording.

    py tools/tests/filters.py logs/baselines_YYYYMMDD_HHMM_raw.csv
    py tools/tests/filters.py logs/scope_raw_x.csv --cal 200-235 --quiet 145-235 --motion 237-470

With a labelled recording (baselines.py), the first half of 'empty' is the
calibration and the second half is scored as quiet (out of sample); walking,
fidget, hallway and kids are scored as motion. Without labels, give spans
in seconds.

Per candidate, LOW/HIGH come from the calibration (K_LOW/K_HIGH), then:
  quiet>LOW %   time above LOW with nobody there
  LOW hits/h    upward crossings of LOW per hour of empty room: each one
                restarts the quiet timer, or freezes a turn
  <label> %     time above HIGH per motion label (sensitivity)
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from features import pipeline  # noqa: E402
from nh_config import C  # noqa: E402

CANDIDATES = [  # name, normalise, hampel k, hampel sigma
    ("no filter", False, 0, 0),
    ("Hampel k3 3sd (fw)", False, 3, 3.0),
    ("Hampel k3 5sd", False, 3, 5.0),
    ("Hampel k5 3sd", False, 5, 3.0),
    ("Hampel k2 4sd", False, 2, 4.0),
]
MOTION_LABELS = ("walking", "fidget", "hallway", "kids", "sitting-phone")


def span(s):
    a, b = s.split("-")
    return float(a), float(b)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--cal", type=span)
    ap.add_argument("--quiet", type=span, action="append", default=[])
    ap.add_argument("--motion", type=span, action="append", default=[])
    ap.add_argument("--plot", help="save a comparison PNG")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    t_ms = np.array([int(r["uptime_ms"]) for r in rows])
    t = (t_ms - t_ms[0]) / 1000
    amps = np.array([[int(r[f"a{i}"]) for i in range(51)] for r in rows])
    labels = np.array([r.get("label", "") for r in rows])
    fr = np.array([int(r["frames"]) for r in rows])
    missing = int(np.sum(np.diff(fr) - 1))
    print(f"{len(rows)} frames, {t[-1]:.0f} s, {missing} frames missing, K {C['K_LOW']}/{C['K_HIGH']}\n")

    groups = {}
    if a.cal:
        cal = (t >= a.cal[0]) & (t <= a.cal[1])
        quiet = np.zeros(len(t), bool)
        for lo, hi in a.quiet:
            quiet |= (t >= lo) & (t <= hi)
        mo = np.zeros(len(t), bool)
        for lo, hi in a.motion:
            mo |= (t >= lo) & (t <= hi)
        groups["motion"] = mo
    else:
        e = np.where(labels == "empty")[0]
        if len(e) < 1000:
            raise SystemExit("no 'empty' segment: pass --cal/--quiet/--motion spans")
        half = e[len(e) // 2]
        cal = (labels == "empty") & (np.arange(len(t)) < half)
        quiet = (labels == "empty") & (np.arange(len(t)) >= half)
        for lab in MOTION_LABELS:
            if (labels == lab).any():
                groups[lab] = labels == lab
        for lab in ("sitting-still",):
            if (labels == lab).any():
                groups[lab] = labels == lab

    quiet_h = (t[quiet].max() - t[quiet].min()) / 3600 if quiet.any() else 0
    head = f"{'candidate':<20}{'LOW':>8}{'HIGH':>8}{'quiet>LOW%':>11}{'hits/h':>8}"
    head += "".join(f"{g[:12]:>13}" for g in groups)
    print(head)
    results = []
    for name, norm, k, n in CANDIDATES:
        m = pipeline(t_ms, amps, norm, k, n)
        ok = ~np.isnan(m)
        c = m[cal & ok]
        low = c.mean() + C["K_LOW"] * c.std()
        high = c.mean() + C["K_HIGH"] * c.std()
        q = m[quiet & ok]
        above = q > low
        hits = int(np.sum(above[1:] & ~above[:-1]))
        line = f"{name:<20}{low:8.4f}{high:8.4f}{above.mean() * 100:11.1f}{hits / max(quiet_h, 1e-9):8.0f}"
        for sel in groups.values():
            line += f"{(m[sel & ok] > high).mean() * 100:12.1f}%"
        print(line)
        results.append((name, m, low, high))
    print(f"\n(quiet scored on {quiet_h * 60:.1f} min; motion columns = % of time above HIGH)")

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(len(results), 1, figsize=(15, 2.4 * len(results)), sharex=True)
        for ax, (name, m, low, high) in zip(axes, results):
            ax.plot(t, np.maximum(m, 1e-6), lw=0.5)
            ax.axhline(low, color="orange", ls="--", lw=0.8)
            ax.axhline(high, color="red", ls="--", lw=0.8)
            ax.fill_between(t, 1e-6, 10, where=quiet, color="green", alpha=0.08)
            ax.fill_between(t, 1e-6, 10, where=cal, color="blue", alpha=0.06)
            ax.set_yscale("log")
            ax.set_ylim(max(np.nanmin(m[m > 0]) / 2, 1e-5), np.nanmax(m) * 2)
            ax.set_title(name, loc="left", fontsize=9)
        if not a.cal:  # label names along the top
            for lab in dict.fromkeys(labels):
                idx = np.where(labels == lab)[0]
                if lab != "transition":
                    axes[0].text(t[idx[len(idx) // 2]], axes[0].get_ylim()[1], lab, ha="center",
                                 va="bottom", fontsize=8)
        axes[-1].set_xlabel("seconds (blue = calibration, green = empty room scored)")
        fig.tight_layout()
        fig.savefig(a.plot, dpi=110)
        print(f"plot -> {a.plot}")


if __name__ == "__main__":
    main()
