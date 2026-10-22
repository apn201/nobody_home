"""Figures and numbers for the element14 write-up, from the recorded logs only.

    py tools/post_figures.py            # writes docs/element14/img/*.png, prints numbers

Needs the logs in logs/ (not in git): baselines_20261020_2102(_raw).csv,
unattended_20261020.csv, empty_verified_20261020.csv, away_servo_20261021.csv.
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from scipy.signal import welch

sys.path.insert(0, os.path.dirname(__file__))
from nh_config import C  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs")
OUT = os.path.join(ROOT, "docs", "element14", "img")
os.makedirs(OUT, exist_ok=True)

BG = "#14121a"
PANEL = "#1c1925"
INK = "#e8e4ef"
MUTED = "#9a93a8"
GRID = "#2c2838"
ORANGE, BLUE, GREEN, PURPLE = "#D9691A", "#2196C8", "#3FA35E", "#A57BD6"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": PANEL, "savefig.facecolor": BG,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "grid.color": GRID,
    "axes.grid": True, "grid.linewidth": 0.6, "font.size": 10,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "font.family": "DejaVu Sans", "lines.linewidth": 1.4,
})

# LLTF, 20 MHz, channel 11: 51 subcarriers kept, -26..-1 and 2..26 (see csi.cpp)
SUBC = np.r_[np.arange(-26, 0), np.arange(2, 27)]
F_CENTER = 2462e6
DF = 312.5e3
LAMBDA = 3e8 / F_CENTER
ACOLS = [f"a{i}" for i in range(51)]
SEGS = ["walking", "sitting-still", "sitting-phone", "fidget", "hallway", "empty"]
SEG_NAMES = {"walking": "walking", "sitting-still": "sitting still",
             "sitting-phone": "phone", "fidget": "fidget",
             "hallway": "hallway\n(door shut)", "empty": "empty"}


def save(fig, name):
    p = os.path.join(OUT, name)
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(p, ROOT))


def run3():
    tel = pd.read_csv(os.path.join(LOGS, "baselines_20261020_2102.csv"))
    tel = tel[tel.kind == "T"].copy()
    raw = pd.read_csv(os.path.join(LOGS, "baselines_20261020_2102_raw.csv"))
    t0 = tel.unix_time.iloc[0]
    tel["t"] = tel.unix_time - t0
    raw["t"] = raw.unix_time - t0
    mean = float(np.median(tel.high / C["HIGH_RATIO"]))
    return tel, raw, mean


def seg_spans(df):
    spans = []
    lab = df.label.values
    t = df.t.values
    start = 0
    for i in range(1, len(lab) + 1):
        if i == len(lab) or lab[i] != lab[start]:
            if lab[start] in SEGS:
                spans.append((lab[start], t[start], t[i - 1]))
            start = i
    return spans


def fig_waterfall(tel, raw, mean):
    spans = seg_spans(tel)
    t_end = spans[-1][2]
    r = raw[raw.t <= t_end]
    step = max(1, len(r) // 3000)
    A = r[ACOLS].values[::step].T.astype(float)
    tt = r.t.values[::step]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True,
                                 gridspec_kw={"height_ratios": [1.5, 1]})
    fmhz = (F_CENTER + SUBC * DF) / 1e6
    a1.pcolormesh(tt, fmhz, A, shading="nearest", cmap="inferno", rasterized=True)
    a1.set_ylabel("subcarrier frequency (MHz)")
    a1.set_title("CSI amplitude |H(f,t)|, 51 subcarriers, channel 11, about 100 frames/s")
    a1.grid(False)
    for lab, s, e in spans:
        a1.text((s + e) / 2, fmhz[-1] + 0.6, SEG_NAMES[lab].replace("\n", " "),
                ha="center", va="bottom", color=INK, fontsize=9)
    a1.set_ylim(fmhz[0] - 0.3, fmhz[-1] + 2.2)
    x = tel.metric / mean
    a2.semilogy(tel.t, x.clip(lower=0.1), color=ORANGE, lw=1)
    a2.axhline(C["LOW_RATIO"], color=GREEN, ls="--", lw=1)
    a2.axhline(C["HIGH_RATIO"], color=BLUE, ls="--", lw=1)
    a2.text(tel.t.iloc[-1], C["LOW_RATIO"] * 0.78, "LOW 2.5x", color=GREEN, ha="right", fontsize=9)
    a2.text(tel.t.iloc[-1], C["HIGH_RATIO"] * 1.15, "HIGH 3.5x", color=BLUE, ha="right", fontsize=9)
    for lab, s, e in spans:
        a2.axvspan(s, e, color="#ffffff", alpha=0.04, lw=0)
    a2.set_ylabel("motion metric / empty mean")
    a2.set_xlabel("time (s)")
    a2.set_xlim(0, t_end)
    save(fig, "01_waterfall_run3.png")


def fig_segments(tel, mean):
    data, stats = [], []
    for s in SEGS:
        v = (tel[tel.label == s].metric / mean).values
        data.append(np.clip(v, 0.1, None))
        stats.append((s, np.median(v), np.percentile(v, 5), np.percentile(v, 95),
                      100 * np.mean(v > C["LOW_RATIO"])))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    bp = ax.boxplot(data, whis=(5, 95), showfliers=False, patch_artist=True, widths=0.5)
    for i, b in enumerate(bp["boxes"]):
        b.set(facecolor=GREEN if SEGS[i] == "empty" else ORANGE, alpha=0.85, edgecolor=BG)
    for k in ("whiskers", "caps"):
        for l in bp[k]:
            l.set(color=MUTED)
    for l in bp["medians"]:
        l.set(color=INK, lw=2)
    ax.set_yscale("log")
    ax.axhline(C["LOW_RATIO"], color=GREEN, ls="--", lw=1)
    ax.text(6.45, C["LOW_RATIO"], " LOW", color=GREEN, va="center", fontsize=9)
    ax.set_xticks(range(1, 7), [SEG_NAMES[s] for s in SEGS])
    ax.set_ylabel("motion metric / empty mean (log)")
    ax.set_title("Cued run 3: people against the empty room (box 25-75 %, whiskers 5-95 %)")
    ax.set_ylim(0.8, 400)
    for i, (s, med, lo, hi, pct) in enumerate(stats):
        ax.text(i + 1, hi * 1.35, f"{med:.1f}x", ha="center", color=INK, fontsize=9)
    save(fig, "02_segments_run3.png")
    return stats


def uniform(seg, fs=100.0):
    t = seg.unix_time.values
    tg = np.arange(t[0], t[-1], 1 / fs)
    A = seg[ACOLS].values.astype(float)
    return np.stack([np.interp(tg, t, A[:, k]) for k in range(51)])


def fig_spectrum(raw):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    out = {}
    for s, col in (("walking", ORANGE), ("fidget", PURPLE), ("sitting-still", BLUE), ("empty", GREEN)):
        seg = raw[raw.label == s]
        U = uniform(seg)
        U = U - U.mean(axis=1, keepdims=True)
        f, P = welch(U, fs=100.0, nperseg=512, axis=1)
        p = P.mean(axis=0)
        ax.semilogy(f, p, color=col, label=SEG_NAMES[s].replace("\n", " "))
        band = (f >= 0.3) & (f <= 10)
        out[s] = (0.0, float(np.trapezoid(p[(f > 0.3) & (f < 5)], f[(f > 0.3) & (f < 5)])),
                  float(np.trapezoid(p[f > 20], f[f > 20])))
    ax.set_xlim(0, 25)
    ax.set_xlabel("fluctuation frequency of |H| (Hz)")
    ax.set_ylabel("PSD, mean over subcarriers")
    ax.set_title("Where the motion lives: amplitude spectrum, Welch, 5.1 s segments")
    ax.axvspan(0.3, 5, color="#ffffff", alpha=0.04, lw=0)
    ax.text(2.6, ax.get_ylim()[1] * 0.4, "body motion band", color=MUTED, ha="center", fontsize=9)
    ax.legend(frameon=False, loc="upper right")
    save(fig, "03_spectrum.png")
    return out


def fig_profile(raw):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    fk = SUBC * DF / 1e6
    out = {}
    for s, col in (("empty", GREEN), ("walking", ORANGE)):
        A = raw[raw.label == s][ACOLS].values.astype(float)
        m, sd = A.mean(0), A.std(0)
        ax.plot(fk, m, color=col, lw=2, label=f"{s}: mean")
        ax.fill_between(fk, m - sd, m + sd, color=col, alpha=0.2, lw=0, label=f"{s}: +-1 std")
        out[s] = (m, sd)
    ax.set_xlabel("subcarrier offset from 2462 MHz (MHz)")
    ax.set_ylabel("|H| (raw int8 amplitude)")
    ax.set_title("Frequency-selective fading: multipath notches across the 20 MHz channel")
    ax.legend(frameon=False, ncol=2, loc="upper center")
    save(fig, "04_subcarrier_profile.png")
    return out


def crossings(x, ratios, rate_hz):
    hours = len(x) / rate_hz / 3600
    res = []
    for r in ratios:
        above = x > r
        res.append(np.sum(above[1:] & ~above[:-1]) / hours)
    return np.array(res)


def fig_exceedance(tel3, mean3):
    u = pd.read_csv(os.path.join(LOGS, "unattended_20261020.csv"))
    u = u[(u.kind == "T") & (u.rate >= C["MIN_RATE"])]
    mean_u = 0.0158  # calibration mean of that session (NOTES 2026-10-20 unattended hour)
    xu = (u.metric / mean_u).values
    ratios = np.geomspace(1, 20, 60)
    cu = crossings(xu, ratios, 10.0)
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.loglog(ratios, np.maximum(cu, 0.3), color=GREEN, lw=2, label="verified empty hour: upward crossings / h")
    ax.axvline(C["LOW_RATIO"], color=GREEN, ls="--", lw=1)
    ax.axvline(C["HIGH_RATIO"], color=BLUE, ls="--", lw=1)
    ax.text(C["LOW_RATIO"] * 1.03, ax.get_ylim()[1] * 0.6, "LOW", color=GREEN, fontsize=9)
    ax.text(C["HIGH_RATIO"] * 1.03, ax.get_ylim()[1] * 0.6, "HIGH", color=BLUE, fontsize=9)
    for s, col in (("walking", ORANGE), ("sitting-still", BLUE), ("hallway", PURPLE)):
        med = float(np.median(tel3[tel3.label == s].metric / mean3))
        ax.axvline(med, color=col, lw=2, alpha=0.8)
        ax.text(med * 1.03, 1.2, f"{SEG_NAMES[s].splitlines()[0]} median", color=col, fontsize=9, rotation=90, va="bottom")
    # Gaussian with the same mean and std, for comparison
    from scipy.stats import norm
    mu, sd = xu.mean(), xu.std()
    g = norm.sf(ratios, mu, sd) * 3600 * 10 * 0.5
    ax.loglog(ratios, np.maximum(g, 1e-3), color=MUTED, ls=":", label="Gaussian with same mean/std (rough)")
    ax.set_ylim(0.3, 3e3)
    ax.set_xlabel("threshold (x empty-room mean)")
    ax.set_ylabel("crossings per hour")
    ax.set_title("Heavy tails: how often an empty room crosses a threshold")
    ax.legend(frameon=False, loc="lower left")
    save(fig, "05_exceedance.png")
    return dict(zip([1.5, 2, 2.5, 3, 3.5, 5], crossings(xu, [1.5, 2, 2.5, 3, 3.5, 5], 10.0))), (mu, sd)


def fig_servo():
    d = pd.read_csv(os.path.join(LOGS, "away_servo_20261021.csv"))
    d = d[d.kind.isin(["T", "E"])]
    ev = d[d.event == "turn_start"].unix_time.values
    t = d[d.kind == "T"]
    x = (t.metric / t.low).values
    tt = t.unix_time.values
    lags = np.arange(-5, 8.01, 0.1)
    M = []
    for e in ev:
        M.append(np.interp(e + lags, tt, x, left=np.nan, right=np.nan))
    M = np.array(M)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    p5, p50, p95 = np.nanpercentile(M, [5, 50, 95], axis=0)
    ax.fill_between(lags, p5, p95, color=ORANGE, alpha=0.25, lw=0, label="5-95 % over all moves")
    ax.plot(lags, p50, color=ORANGE, lw=2, label="median")
    ax.axhline(1, color=GREEN, ls="--", lw=1)
    ax.text(7.9, 1.03, "LOW (freeze)", color=GREEN, ha="right", fontsize=9)
    ax.axvline(0, color=MUTED, lw=1)
    ax.text(0.1, 1.15, "move starts", color=MUTED, fontsize=9)
    ax.set_ylim(0, 1.3)
    ax.set_xlabel("time from move start (s)")
    ax.set_ylabel("metric / LOW")
    ax.set_title(f"Does the servo see itself? {len(ev)} moves, empty house, 75 min")
    ax.legend(frameon=False, loc="upper left")
    save(fig, "06_servo_self_noise.png")
    return len(ev), float(np.nanmax(p95)), float(np.nanmedian(M[:, lags < 0]))


def box(ax, xy, w, h, text, col, fs=10):
    ax.add_patch(FancyBboxPatch((xy[0] - w / 2, xy[1] - h / 2), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=PANEL, ec=col, lw=2))
    ax.text(xy[0], xy[1], text, ha="center", va="center", color=INK, fontsize=fs)


def arrow(ax, a, b, text="", col=MUTED, rad=0.0, off=(0, 0.12)):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, color=col,
                                 lw=1.5, connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1], text,
                ha="center", va="center", color=col, fontsize=8.5)


def fig_states():
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    P = {"ACTIVE": (1.3, 3.4), "QUIET": (4.3, 3.4), "EMPTY": (7.3, 3.4),
         "TURNING": (9.7, 1.4), "STALE": (1.3, 1.0), "HOLD": (4.3, 1.0)}
    box(ax, P["ACTIVE"], 1.9, 0.8, "ACTIVE\nsomeone moves", ORANGE)
    box(ax, P["QUIET"], 1.9, 0.8, "QUIET_PENDING\ncount 10 s", BLUE)
    box(ax, P["EMPTY"], 1.9, 0.8, "EMPTY\nhaunt allowed", GREEN)
    box(ax, P["TURNING"], 1.9, 0.8, "MOVING\ncreep / snap / twitch", PURPLE)
    box(ax, P["STALE"], 1.9, 0.8, "STALE\nno CSI = no move", MUTED)
    box(ax, P["HOLD"], 2.2, 0.8, "strong-event hold\n30 s after > 10x mean", ORANGE)
    arrow(ax, (2.25, 3.5), (3.35, 3.5), "m < LOW")
    arrow(ax, (3.35, 3.3), (2.25, 3.3), "m > LOW", col=ORANGE, off=(0, -0.15))
    arrow(ax, (5.25, 3.4), (6.35, 3.4), "10 s quiet\n+ hold over", off=(0, -0.48))
    arrow(ax, (7.9, 3.0), (9.3, 1.8), "random gap\n8-35 s", rad=-0.2, off=(0.95, 0.2))
    arrow(ax, (9.0, 1.1), (2.3, 3.05), "m > LOW: freeze in pose", col=ORANGE, rad=-0.25, off=(1.5, -0.9))
    arrow(ax, (9.7, 1.8), (8.1, 3.0), "done", rad=-0.2, off=(-0.55, -0.2))
    arrow(ax, (7.3, 3.8), (1.3, 3.8), "m > LOW", col=ORANGE, rad=0.25, off=(0, 0.95))
    arrow(ax, (1.3, 2.98), (1.3, 1.42), "rate < 20/s\nfor 2 s", off=(0.6, 0))
    arrow(ax, (1.55, 1.42), (1.55, 2.98), "", col=MUTED)
    arrow(ax, (2.3, 3.0), (3.4, 1.42), "m > 10x mean", col=ORANGE, rad=0.1, off=(0.5, 0.1))
    arrow(ax, (4.3, 1.42), (4.3, 2.98), "blocks EMPTY", col=ORANGE, off=(0.55, 0))
    ax.set_title("Detector and video-mode state machine (firmware/src/detector.cpp, haunt.cpp)")
    save(fig, "07_state_machine.png")


def fig_wiring():
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")
    box(ax, (2.0, 2.6), 2.6, 2.6, "M5Stack AtomS3R\nESP32-S3\n128x128 LCD, BMI270\n\nGrove port", BLUE)
    box(ax, (8.0, 2.6), 2.2, 1.6, "SG90\nmicro servo\ninside the doll,\nhead on the horn", ORANGE)
    box(ax, (2.0, 0.45), 2.6, 0.55, "5 V USB-C supply", MUTED, fs=9)
    ax.plot([2.0, 2.0], [0.72, 1.3], color=MUTED, lw=1.5)
    rows = [("GND", "#777777", 3.1, "brown"), ("5V", "#d64545", 2.6, "red"), ("G2  signal (LEDC 50 Hz)", "#e0c040", 2.1, "orange")]
    for name, col, y, wire in rows:
        ax.plot([3.3, 6.9], [y, y], color=col, lw=3)
        ax.text(3.45, y + 0.12, name, color=INK, fontsize=9)
        ax.text(6.75, y + 0.12, wire, color=MUTED, fontsize=9, ha="right")
    ax.plot([5.6, 5.6], [2.6, 3.1], color=INK, lw=1)
    ax.text(5.1, 3.45, "1000 uF across 5V/GND: in the spec, not needed so far", color=MUTED, fontsize=8, ha="center")
    ax.text(5.0, 4.6, "Pulse 500-2500 us = 0-180 deg, clamped to 5-175 deg in software", ha="center", color=MUTED, fontsize=9)
    ax.text(5.0, 4.2, "The router is the transmitter. There is no other sensor.", ha="center", color=MUTED, fontsize=9)
    ax.set_title("Wiring")
    save(fig, "08_wiring.png")


def fig_thumbnail(raw):
    r = raw[raw.label.isin(["walking", "transition", "sitting-still"])]
    A = r[ACOLS].values[:2400:2].T.astype(float)[1:-1]
    for size, name in ((300, "thumbnail_300.png"), (1200, "thumbnail_1200.png")):
        fig = plt.figure(figsize=(4, 4), dpi=size / 4)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(A, aspect="auto", cmap="inferno", origin="lower", interpolation="bilinear")
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), A.shape[1], A.shape[0], color=BG, alpha=0.45))
        fig.text(0.5, 0.60, "NOBODY", ha="center", color="#f2e9dc", fontsize=34, fontweight="bold")
        fig.text(0.5, 0.42, "HOME", ha="center", color=ORANGE, fontsize=34, fontweight="bold")
        fig.text(0.5, 0.12, "it only moves when you're gone", ha="center", color=INK, fontsize=10.5)
        p = os.path.join(OUT, name)
        fig.savefig(p, dpi=size / 4)
        plt.close(fig)
        print("wrote", os.path.relpath(p, ROOT))


def main():
    tel, raw, mean = run3()
    fr = raw.groupby(raw.unix_time.astype(int)).size()
    print(f"run3: calibration mean {mean:.4f}, frames {len(raw)}, median rate {fr.median():.0f}/s, "
          f"lambda {LAMBDA*100:.2f} cm")
    fig_waterfall(tel, raw, mean)
    for s, med, lo, hi, pct in fig_segments(tel, mean):
        print(f"  {s:14s} median {med:6.1f}x  p5 {lo:6.2f}  p95 {hi:7.1f}  above LOW {pct:5.1f}%")
    for s, (fpk, pmot, phi) in fig_spectrum(raw).items():
        print(f"  spectrum {s:14s} peak {fpk:.2f} Hz  power 0.3-5 Hz {pmot:.3f}  >20 Hz {phi:.4f}")
    prof = fig_profile(raw)
    m, sd = prof["empty"]
    print(f"  profile empty: max {m.max():.1f} min {m.min():.1f} (notch depth {20*np.log10(m.max()/max(m.min(),1e-3)):.1f} dB) "
          f"at {SUBC[np.argmin(m)]*DF/1e6:+.2f} MHz; mean std empty {sd.mean():.2f} walking {prof['walking'][1].mean():.2f}")
    cr, (mu, sdx) = fig_exceedance(tel, mean)
    print("  empty hour crossings/h:", {k: round(v, 1) for k, v in cr.items()}, f"mean {mu:.2f}x std {sdx:.2f}x")
    n, mx, pre = fig_servo()
    print(f"  servo: {n} moves, p95 max metric/LOW {mx:.2f}, median before {pre:.2f}")
    fig_states()
    fig_wiring()
    fig_thumbnail(raw)


if __name__ == "__main__":
    main()
