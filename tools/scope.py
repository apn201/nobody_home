"""Live CSI scope: what the Atom measures, as it measures it.

    py tools/scope.py                        # also logs telemetry to logs/scope_<time>.csv
    py tools/scope.py --raw                  # also save every raw frame (bigger file)
    py tools/scope.py --seconds 20           # time window

Every pixel comes from UDP packets sent by the device: raw subcarrier
amplitudes (50 Hz) and the detector telemetry (10 Hz). Nothing is smoothed
or generated here. It binds the same port as logger.py, so run one or the
other; this one logs as well.
"""
import argparse
import csv
import socket
import sys
import threading
import time
from collections import deque
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FormatStrFormatter

from logger import FIELDS, NSUB, RAW_FIELDS, raw_row, to_row
from nh_config import C
from telemetry import HELLO_EVERY_S, PORT, decode, say_hello

BG, FG, GRID = "#000000", "#c8c8c8", "#103010"
GREEN, AMBER, CYAN, YELLOW, RED = "#30ff60", "#ffa020", "#30e0ff", "#ffe040", "#ff3030"
STATE_COLOR = {"STALE": RED, "ACTIVE": "#ffffff", "QUIET_PENDING": YELLOW,
               "EMPTY": GREEN, "TURNING": "#ff40ff", "SETTLING": "#ff40ff"}


class Feed:
    """Receives packets on a thread; the plot reads snapshots."""

    def __init__(self, port, window_s, log_path, raw_path):
        self.lock = threading.Lock()
        self.raw = deque(maxlen=int(window_s * 120))  # every frame, ~100/s
        self.tel = deque(maxlen=int(window_s * 12))
        self.events = deque(maxlen=50)
        self.last_tel = None
        self.session = None
        self.count = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(0.5)
        self.log_f = open(log_path, "w", newline="", encoding="utf-8")
        self.log = csv.DictWriter(self.log_f, fieldnames=FIELDS, extrasaction="ignore")
        self.log.writeheader()
        self.raw_f = self.raw_w = None
        if raw_path:
            self.raw_f = open(raw_path, "w", newline="", encoding="utf-8")
            self.raw_w = csv.writer(self.raw_f)
            self.raw_w.writerow(RAW_FIELDS)
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        last_hello = 0
        while self.running:
            if time.time() - last_hello >= HELLO_EVERY_S:
                last_hello = time.time()
                say_hello(self.sock)
            try:
                data, _ = self.sock.recvfrom(512)
            except socket.timeout:
                continue
            p = decode(data)
            if p is None:
                continue
            now = time.time()
            with self.lock:
                if p["session"] != self.session:  # device rebooted: start the traces over
                    self.session = p["session"]
                    self.raw.clear()
                    self.tel.clear()
                    self.events.clear()
                if p["kind"] == "R":
                    self.raw.append(p)
                    self.count += 1
                elif p["kind"] == "T":
                    self.tel.append(p)
                    self.last_tel = p
                else:
                    self.events.append(p)
            if p["kind"] == "R":
                if self.raw_w:
                    self.raw_w.writerow(raw_row(p, "", now))
            else:
                self.log.writerow(to_row(p, "", now))

    def snapshot(self):
        with self.lock:
            return list(self.raw), list(self.tel), list(self.events), self.last_tel

    def close(self):
        self.running = False
        self.log_f.close()
        if self.raw_f:
            self.raw_f.close()


def style(ax, title):
    ax.set_facecolor(BG)
    ax.set_title(title, color=FG, loc="left", fontsize=10, family="monospace")
    ax.tick_params(colors=FG, labelsize=8)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(True, color=GRID, lw=0.6)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--raw", action="store_true", help="save every raw frame to logs/scope_raw_<time>.csv")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--snapshot", help="save one frame to this PNG after --after seconds, then exit")
    ap.add_argument("--after", type=float, default=12)
    a = ap.parse_args()
    if a.snapshot:
        plt.switch_backend("Agg")

    if getattr(sys, "frozen", False):  # exe: logs next to it, not in the temp unpack dir
        logs = Path(sys.executable).resolve().parent / "logs"
    else:
        logs = Path(__file__).resolve().parent.parent / "logs"
    logs.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M")
    feed = Feed(a.port, a.seconds, logs / f"scope_{stamp}.csv", logs / f"scope_raw_{stamp}.csv" if a.raw else None)
    print(f"Nobody Home live CSI. Listening on UDP {a.port}, asking the Atom to stream here.")
    print(f"Logging to {logs}. Press F for full screen. Close the window to stop.")
    W = a.seconds

    plt.rcParams["toolbar"] = "None"
    fig = plt.figure(figsize=(16, 9), facecolor=BG)
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Nobody Home - live CSI")
    gs = fig.add_gridspec(4, 4, height_ratios=[0.35, 1.3, 1, 1], width_ratios=[3, 3, 3, 1.4],
                          hspace=0.45, wspace=0.25, left=0.05, right=0.98, top=0.97, bottom=0.05)
    head = fig.add_subplot(gs[0, :])
    head.axis("off")
    wf = fig.add_subplot(gs[1, :3])
    tr = fig.add_subplot(gs[2, :3], sharex=wf)
    mt = fig.add_subplot(gs[3, :3], sharex=wf)
    sp = fig.add_subplot(gs[1:, 3])

    style(wf, "CSI WATERFALL  amplitude per subcarrier (live frames)")
    img = wf.imshow(np.zeros((NSUB, 10)), aspect="auto", origin="lower", cmap="inferno",
                    extent=(-W, 0, -0.5, NSUB - 0.5), interpolation="nearest")
    wf.grid(False)
    wf.set_ylabel("subcarrier", color=FG, fontsize=8)
    wf.set_yticks([0, 25, 50], ["-26", "-1/+2", "+26"])

    style(tr, "CSI TRACE  per-frame spatial std: measured (green), after outlier filter (white)")
    tr_line, = tr.plot([], [], color=GREEN, lw=1)
    trf_line, = tr.plot([], [], color="#ffffff", lw=0.8, alpha=0.8)

    style(mt, "MOTION  moving variance, log scale")
    mt_line, = mt.plot([], [], color=AMBER, lw=1.4)
    low_line = mt.axhline(1e-9, color=YELLOW, ls="--", lw=1, visible=False)
    high_line = mt.axhline(1e-9, color=RED, ls="--", lw=1, visible=False)
    mt.set_yscale("log")
    mt.set_ylim(1e-3, 1)  # a valid log range before the first packet
    mt.yaxis.set_major_formatter(FormatStrFormatter("%.2g"))
    mt.yaxis.set_minor_formatter(FormatStrFormatter("%.2g"))
    mt.tick_params(which="minor", colors=FG, labelsize=7)
    mt.set_xlim(-W, 0)
    mt.set_xlabel("seconds", color=FG, fontsize=8)
    ev_artists = []

    style(sp, "SPECTRUM  latest frame")
    bars = sp.barh(np.arange(NSUB), np.zeros(NSUB), color=CYAN, height=0.8)
    sp.set_ylim(-0.5, NSUB - 0.5)
    sp.set_yticks([])

    state_txt = head.text(0.0, 0.5, "waiting for the Atom ...", color=FG, fontsize=26,
                          family="monospace", weight="bold", va="center")
    info_txt = head.text(1.0, 0.5, "", color=FG, fontsize=12, family="monospace", ha="right", va="center")

    def update(_):
        raw, tel, events, last = feed.snapshot()
        artists = []
        if raw:
            t_now = raw[-1]["uptime_ms"]
            t = np.array([(r["uptime_ms"] - t_now) / 1000 for r in raw])
            amps = np.array([r["amps"] for r in raw], dtype=float).T
            img.set_data(amps)
            img.set_extent((t[0], 0, -0.5, NSUB - 0.5))
            img.set_clim(*np.percentile(amps, [2, 98]))
            feat = np.array([r["feature"] for r in raw])
            tr_line.set_data(t, feat)
            trf_line.set_data(t, [r["filtered"] for r in raw])
            pad = max(0.2, (feat.max() - feat.min()) * 0.1)
            tr.set_ylim(feat.min() - pad, feat.max() + pad)
            for b, v in zip(bars, raw[-1]["amps"]):
                b.set_width(v)
            sp.set_xlim(0, max(raw[-1]["amps"]) * 1.1 + 1)
        else:
            t_now = tel[-1]["uptime_ms"] if tel else 0
        if tel:
            tt = np.array([(p["uptime_ms"] - t_now) / 1000 for p in tel])
            m = np.maximum(np.array([p["metric"] for p in tel]), 1e-4)
            mt_line.set_data(tt, m)
            lo, hi = last["low"], last["high"]
            top, bot = max(m.max() * 1.5, 2e-4), m.min() / 1.5
            if hi > 0:
                low_line.set_ydata([lo, lo])
                high_line.set_ydata([hi, hi])
                low_line.set_visible(True)
                high_line.set_visible(True)
                top, bot = max(top, hi * 2), min(bot, lo / 3)
            mt.set_ylim(bot, top)
        for art in ev_artists:
            art.remove()
        ev_artists.clear()
        for e in events:
            x = (e["uptime_ms"] - t_now) / 1000
            if x >= -W:
                ev_artists.append(mt.axvline(x, color="#ff40ff", lw=1))
                ev_artists.append(mt.text(x, mt.get_ylim()[1], f" {e['event']}", color="#ff40ff",
                                          fontsize=8, va="top", family="monospace"))
        if last:
            st = last["state"]
            line = st.replace("_", " ")
            if last["high"] <= 0:
                line = "NOT CALIBRATED"
            elif st == "QUIET_PENDING" and (last["armed"] or C["HAUNT"]):
                left = max(0, (C["T_EMPTY_MS"] - last["quiet_ms"]) / 1000)
                line += f"   moving in {left:4.0f} s" if left > 0 else "   holding still"
            elif st == "EMPTY" and C["HAUNT"]:
                line += "   nobody home"
            elif st == "TURNING":
                line += f"   -> {last['angle']}°"
            elif last["armed"] and not C["HAUNT"]:
                line += "   armed"
            state_txt.set_text(line)
            state_txt.set_color(STATE_COLOR.get(st, FG) if last["high"] > 0 else RED)
            rate = last["rate"]
            info_txt.set_text(f"{rate:3d} frames/s   RSSI {last['rssi']} dBm   angle {last['angle']}°   "
                              f"metric {last['metric']:.3f}   session {last['session']}")
        return artists

    if a.snapshot:
        time.sleep(a.after)
        update(0)
        fig.savefig(a.snapshot, facecolor=BG, dpi=100)
        feed.close()
        print(f"snapshot -> {a.snapshot}")
        return

    anim = FuncAnimation(fig, update, interval=50, cache_frame_data=False)  # noqa: F841
    try:
        plt.show()
    finally:
        feed.close()
        print(f"telemetry log -> {feed.log_f.name}")


if __name__ == "__main__":
    main()
