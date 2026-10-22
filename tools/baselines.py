"""Record the phase 2 baselines in one run, with spoken cues.

    py tools/baselines.py                 # all segments, about 15 minutes
    py tools/baselines.py --minutes 1     # shorter segments, for a dry run
    py tools/baselines.py --kids          # add a kids-playing segment at the end

Windows speaks each instruction aloud, so nobody has to watch the screen.
Rows between segments are labelled "transition"; plot.py shows them like
any other label. Output: logs/baselines_YYYYMMDD_HHMM.csv
"""
import argparse
import csv
import socket
import subprocess
import time
from pathlib import Path

from logger import FIELDS, RAW_FIELDS, raw_row, to_row
from telemetry import HELLO_EVERY_S, PORT, decode, say_hello


def say(text):
    """Speak without blocking the recording."""
    print(f"\n>> {text}")
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.Speak('{text.replace(chr(39), '')}')")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass  # no speech, the printed cue still works


def schedule(seg, kids):
    s = [
        ("transition", 15, "Baseline recording starts in 15 seconds. "
                           "Get ready to walk around the room, crossing between the doll and the router."),
        ("walking", seg, "Start walking now. Keep moving until I say stop."),
        ("transition", 15, "Stop. Sit down and stay perfectly still."),
        ("sitting-still", seg, "Recording. Sit perfectly still."),
        ("transition", 10, "Good. Keep sitting, breathe normally, and use your phone."),
        ("sitting-phone", seg, "Recording. Sit and scroll your phone."),
        ("transition", 10, "Now put the phone down. Stay seated, and make small movements: "
                           "shift in the chair, turn your head, move your hands."),
        ("fidget", seg, "Recording. Small movements only, stay seated."),
        ("transition", 20, "Now leave the room and close the door. Stay just outside it, "
                           "and walk around near the door until I say go."),
        ("hallway", seg, "Recording. Keep moving just outside the door."),
        ("transition", 45, "Done with you. Go well away from the door now. "
                           "The empty room recording starts in 45 seconds."),
        ("empty", seg, None),
    ]
    if kids:
        s += [("transition", 30, "Empty room done. Let the kids into the room to play as they normally do. "
                                 "Recording starts in 30 seconds."),
              ("kids", seg, None)]
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=2, help="length of each baseline segment")
    ap.add_argument("--kids", action="store_true", help="add a segment with the kids playing")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-raw", action="store_true", help="skip the every-frame CSV")
    a = ap.parse_args()

    plan = schedule(a.minutes * 60, a.kids)
    out = Path(__file__).resolve().parent.parent / "logs" / time.strftime("baselines_%Y%m%d_%H%M.csv")
    out.parent.mkdir(exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", a.port))
    sock.settimeout(0.5)

    total = sum(d for _, d, _ in plan)
    raw_out = out.with_name(out.stem + "_raw.csv")
    print(f"Writing {out}, about {total / 60:.1f} min")
    if not a.no_raw:
        print(f"Every CSI frame -> {raw_out}")
    counts = {}
    raw_f = None if a.no_raw else open(raw_out, "w", newline="", encoding="utf-8")
    raw_w = csv.writer(raw_f) if raw_f else None
    if raw_w:
        raw_w.writerow(RAW_FIELDS)
    last_hello = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for label, dur, cue in plan:
            if cue:
                say(cue)
            print(f"[{label}] {dur:.0f} s")
            end = time.time() + dur
            while time.time() < end:
                if time.time() - last_hello >= HELLO_EVERY_S:
                    last_hello = time.time()
                    say_hello(sock, a.port)
                try:
                    data, _ = sock.recvfrom(512)
                except socket.timeout:
                    continue
                p = decode(data)
                if p is None:
                    continue
                now = time.time()
                if p["kind"] == "R":
                    if raw_w:
                        raw_w.writerow(raw_row(p, label, now))
                    continue
                w.writerow(to_row(p, label, now))
                if p["kind"] == "T":
                    counts[label] = counts.get(label, 0) + 1
            f.flush()
    if raw_f:
        raw_f.close()
    say("Baseline recording complete. You can come back in.")
    print("\nrows per label:", counts)
    print(f"-> {out}")
    time.sleep(4)  # let the last cue finish speaking


if __name__ == "__main__":
    main()
