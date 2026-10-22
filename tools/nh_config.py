"""Read the #define constants from firmware/include/config.h, so the Python
detector always uses the same numbers as the device."""
import re
import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # PyInstaller exe: config.h is bundled next to the code
    CONFIG_H = Path(sys._MEIPASS) / "config.h"
else:
    CONFIG_H = Path(__file__).resolve().parent.parent / "firmware" / "include" / "config.h"


def load(path=CONFIG_H):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*#define\s+(\w+)\s+([-+0-9.]+)f?\b", line)
        if m:
            v = m.group(2)
            out[m.group(1)] = float(v) if "." in v else int(v)
    return out


C = load()
