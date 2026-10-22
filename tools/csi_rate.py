"""Phase 1 gate: read RATE lines from the Atom and report rate and gaps.

Live from the device (saves a raw log too):
    py tools/csi_rate.py --port COM5 --minutes 10

From a saved log:
    py tools/csi_rate.py --file logs/rate_20261020_2100.txt
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

GATE_MIN_RATE = 50     # median callbacks/s, same as config.h
GATE_MAX_GAP_MS = 500  # longest gap, same as config.h


def parse(line):
    """'RATE t=1 cb=97 gap=31 ...' -> {'t': 1, 'cb': 97, ...} or None."""
    line = line.strip()
    if not line.startswith("RATE "):
        return None
    out = {}
    for part in line.split()[1:]:
        k, _, v = part.partition("=")
        try:
            out[k] = int(v)
        except ValueError:
            pass
    return out if "cb" in out and "gap" in out else None


def report(rows):
    if not rows:
        print("No RATE lines seen.")
        return False
    # The first seconds include WiFi/ping start-up, skip them.
    rows = rows[5:] if len(rows) > 20 else rows
    rates = [r["cb"] for r in rows]
    gaps = [r["gap"] for r in rows]
    med = statistics.median(rates)
    worst = max(gaps)
    long_gaps = sum(1 for g in gaps if g > GATE_MAX_GAP_MS)
    lost = sum(r.get("lost", 0) for r in rows)
    drop = sum(r.get("drop", 0) for r in rows)
    chans = sorted({r.get("ch") for r in rows})
    rssi = [r["rssi"] for r in rows if "rssi" in r]

    print()
    print(f"seconds          {len(rows)} ({len(rows) / 60:.1f} min)")
    print(f"callbacks/s      median {med:.0f}, min {min(rates)}, max {max(rates)}")
    print(f"longest gap      {worst} ms ({long_gaps} seconds with a gap > {GATE_MAX_GAP_MS} ms)")
    print(f"rssi             median {statistics.median(rssi):.0f}" if rssi else "rssi             -")
    print(f"channel(s)       {chans}")
    print(f"ping timeouts    {lost}")
    print(f"queue drops      {drop}")
    ok = med >= GATE_MIN_RATE and worst <= GATE_MAX_GAP_MS
    print()
    print(f"GATE {'PASS' if ok else 'FAIL'}  (need median >= {GATE_MIN_RATE}/s and no gap > {GATE_MAX_GAP_MS} ms)")
    return ok


def from_serial(port, minutes):
    try:
        import serial
    except ImportError:
        sys.exit("pyserial missing: py -m pip install pyserial")

    logdir = Path(__file__).resolve().parent.parent / "logs"
    logdir.mkdir(exist_ok=True)
    logpath = logdir / time.strftime("rate_%Y%m%d_%H%M.txt")
    rows = []
    end = time.time() + minutes * 60
    print(f"Reading {port} for {minutes} min, raw log -> {logpath}. Ctrl+C stops early.")
    with serial.Serial(port, 115200, timeout=1) as ser, open(logpath, "w", encoding="utf-8") as log:
        try:
            while time.time() < end:
                line = ser.readline().decode("utf-8", "replace")
                if not line:
                    continue
                log.write(line)
                r = parse(line)
                if r is None:
                    print(line.rstrip())  # boot messages, errors
                    continue
                rows.append(r)
                left = int(end - time.time())
                print(f"\r{r['cb']:4d}/s  gap {r['gap']:4d} ms  rssi {r.get('rssi', 0):4d}  "
                      f"{left // 60:2d}:{left % 60:02d} left ", end="", flush=True)
        except KeyboardInterrupt:
            pass
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial port, e.g. COM5")
    src.add_argument("--file", help="saved log to analyse")
    ap.add_argument("--minutes", type=float, default=10)
    a = ap.parse_args()

    if a.file:
        with open(a.file, encoding="utf-8", errors="replace") as f:
            rows = [r for r in map(parse, f) if r]
    else:
        rows = from_serial(a.port, a.minutes)
    sys.exit(0 if report(rows) else 1)


if __name__ == "__main__":
    main()
