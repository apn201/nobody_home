"""Receive Nobody Home telemetry over UDP and write it to CSV.

    py tools/logger.py                     # logs/telemetry_YYYYMMDD_HHMM.csv
    py tools/logger.py --label empty       # start with a label
    py tools/logger.py --label empty --seconds 120

While it runs, type a label and press Enter. Rows are tagged with it from
then on. An empty line clears the label. Ctrl+C stops.
"""
import argparse
import csv
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from telemetry import HELLO_EVERY_S, PORT, decode, say_hello

FIELDS = ["wall_time", "unix_time", "kind", "session", "seq", "uptime_ms", "rate", "metric",
          "low", "high", "state", "armed", "quiet_ms", "angle", "rssi", "event", "label"]

label = ""

NSUB = 51
RAW_FIELDS = (["unix_time", "uptime_ms", "frames", "feature", "filtered", "metric", "rssi", "label"]
              + [f"a{i}" for i in range(NSUB)])


def raw_row(p, label, now):
    """Raw CSI packet -> list for a csv.writer with RAW_FIELDS."""
    return ([f"{now:.3f}", p["uptime_ms"], p["frames"], f"{p['feature']:.4f}", f"{p['filtered']:.4f}",
             f"{p['metric']:.5f}", p["rssi"], label] + p["amps"])


def to_row(p, label, now):
    """Decoded packet -> CSV row dict (adds wall clock and label)."""
    p = dict(p)
    p["wall_time"] = datetime.fromtimestamp(now).isoformat(timespec="milliseconds")
    p["unix_time"] = f"{now:.3f}"
    p["label"] = label
    if p["kind"] == "T":
        p["metric"] = f"{p['metric']:.5f}"
    return p


def read_labels():
    global label
    for line in sys.stdin:
        label = line.strip()
        print(f"\nlabel -> {label or '(none)'}")


def main():
    global label
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", help="CSV path (default logs/telemetry_<time>.csv)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--seconds", type=float, help="stop after this long (default: run until Ctrl+C)")
    ap.add_argument("--raw", action="store_true", help="also save every CSI frame to <out>_raw.csv")
    a = ap.parse_args()
    label = a.label

    out = Path(a.out) if a.out else (
        Path(__file__).resolve().parent.parent / "logs" / time.strftime("telemetry_%Y%m%d_%H%M.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", a.port))
    sock.settimeout(1.0)
    threading.Thread(target=read_labels, daemon=True).start()

    print(f"Listening on UDP {a.port}, writing {out}")
    print("Type a label + Enter to tag rows. Ctrl+C stops.")
    rows = 0
    last_print = 0
    last_seen = None
    end = time.time() + a.seconds if a.seconds else None
    raw_f = open(out.with_name(out.stem + "_raw.csv"), "w", newline="", encoding="utf-8") if a.raw else None
    raw_w = csv.writer(raw_f) if raw_f else None
    if raw_w:
        raw_w.writerow(RAW_FIELDS)
        print(f"every CSI frame -> {raw_f.name}")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        try:
            last_hello = 0
            while end is None or time.time() < end:
                if time.time() - last_hello >= HELLO_EVERY_S:
                    last_hello = time.time()
                    say_hello(sock, a.port)
                try:
                    data, _ = sock.recvfrom(256)
                except socket.timeout:
                    if last_seen and time.time() - last_seen > 3:
                        print("\rno packets for 3 s ...                                  ", end="", flush=True)
                    continue
                p = decode(data)
                if p is None:
                    continue
                now = time.time()
                if p["kind"] == "R":
                    if raw_w:
                        raw_w.writerow(raw_row(p, label, now))
                    continue
                last_seen = now
                p = to_row(p, label, now)
                w.writerow(p)
                rows += 1
                if p["kind"] == "E":
                    print(f"\nEVENT {p['event']} angle={p['angle']} session={p['session']}")
                elif now - last_print >= 1:
                    last_print = now
                    f.flush()
                    print(f"\r{p['rate']:4d}/s  metric {float(p['metric']):9.4f}  {p['state']:<13}"
                          f" rows {rows:6d}  label: {label or '-':<20}", end="", flush=True)
        except KeyboardInterrupt:
            pass
    if raw_f:
        raw_f.close()
    print(f"\n{rows} rows -> {out}")


if __name__ == "__main__":
    main()
