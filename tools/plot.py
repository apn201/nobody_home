"""Plot a telemetry CSV: metric over time coloured by label, thresholds,
events, and the metric distribution per label.

    py tools/plot.py logs/telemetry_20261020_1400.csv
    py tools/plot.py logs/telemetry_20261020_1400.csv --show

Writes a PNG next to the CSV.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
import numpy as np


def load(path):
    t, metric, low, high, labels, events = [], [], [], [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = float(r["unix_time"])
            if r["kind"] == "E":
                events.append((ts, r["event"]))
                continue
            t.append(ts)
            metric.append(float(r["metric"]))
            low.append(float(r["low"]))
            high.append(float(r["high"]))
            labels.append(r["label"] or "(none)")
    t = np.array(t)
    t0 = t[0] if len(t) else 0
    return (t - t0, np.array(metric), np.array(low), np.array(high), labels,
            [(ts - t0, name) for ts, name in events])


def segments(labels):
    """Runs of equal labels as (label, start, end) index ranges."""
    out, start = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            out.append((labels[start], start, i))
            start = i
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--show", action="store_true", help="open a window as well")
    a = ap.parse_args()
    if not a.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t, m, low, high, labels, events = load(a.csv)
    if not len(t):
        raise SystemExit("no telemetry rows")
    names = list(dict.fromkeys(labels))
    colors = {n: plt.cm.tab10(i % 10) for i, n in enumerate(names)}
    floor = max(m[m > 0].min() if (m > 0).any() else 1e-6, 1e-6)

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(15, 5.5), width_ratios=[3, 1], sharey=True)
    for name, s, e in segments(labels):
        ax.plot(t[s:e], np.maximum(m[s:e], floor), color=colors[name], lw=0.8)
    for name in names:
        ax.plot([], [], color=colors[name], label=name)
    if (high > 0).any():
        ax.plot(t, np.where(low > 0, low, np.nan), "k--", lw=0.8, label="LOW")
        ax.plot(t, np.where(high > 0, high, np.nan), "k:", lw=0.8, label="HIGH")
    for ts, name in events:
        ax.axvline(ts, color="grey", lw=0.6)
        ax.text(ts, m.max(), name, rotation=90, fontsize=7, va="top")
    ax.set_yscale("log")
    ax.set_xlabel("seconds")
    ax.set_ylabel("motion metric (moving variance)")
    ax.set_title(Path(a.csv).name)
    ax.legend(fontsize=8, loc="upper left")

    data = [np.maximum(m[[l == n for l in labels]], floor) for n in names]
    box = bx.boxplot(data, tick_labels=names, patch_artist=True, showfliers=False)
    for patch, n in zip(box["boxes"], names):
        patch.set_facecolor(colors[n])
    bx.tick_params(axis="x", rotation=30, labelsize=8)
    bx.set_title("per label")

    fig.tight_layout()
    out = Path(a.csv).with_suffix(".png")
    fig.savefig(out, dpi=130)
    print(f"plot -> {out}")

    print(f"\n{'label':<24}{'n':>7}{'median':>12}{'p95':>12}")
    for n, d in zip(names, data):
        print(f"{n:<24}{len(d):>7}{np.median(d):>12.4f}{np.percentile(d, 95):>12.4f}")
    if a.show:
        plt.show()


if __name__ == "__main__":
    main()
