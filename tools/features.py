"""Python copy of the per-frame feature pipeline in firmware/src/csi.cpp,
for tuning on raw recordings (scope.py --raw). Same steps, same constants.

    amplitudes -> per-frame feature -> Hampel outlier filter -> moving variance
"""
from collections import deque

import numpy as np

from nh_config import C


def feature(amps, normalise):
    """Spatial std of subcarrier amplitudes. With normalise, divided by the
    frame's mean amplitude, so a frame received at a different gain gives
    the same value."""
    a = np.asarray(amps, dtype=float)
    m = a.mean()
    s = a.std()
    if normalise:
        return s / m if m > 0 else 0.0
    return s


class Hampel:
    """Causal Hampel filter: judges the middle of the last 2k+1 values and
    replaces it with the median if it is more than n_sigma robust deviations
    away. Output is delayed by k frames."""

    def __init__(self, k, n_sigma):
        self.k, self.n = k, n_sigma
        self.buf = deque(maxlen=2 * k + 1)

    def __call__(self, x):
        self.buf.append(x)
        if len(self.buf) < self.buf.maxlen:
            return None
        w = np.array(self.buf)
        med = np.median(w)
        mad = np.median(np.abs(w - med))
        mid = w[self.k]
        if abs(mid - med) > self.n * 1.4826 * mad:
            return med
        return mid


class MovingVar:
    """Variance over the last window_ms, like windowAdd() on the device."""

    def __init__(self, window_ms=None):
        self.w = window_ms or C["MOTION_WINDOW_MS"]
        self.q = deque()

    def __call__(self, t_ms, x):
        self.q.append((t_ms, x))
        while self.q and t_ms - self.q[0][0] > self.w:
            self.q.popleft()
        if len(self.q) < 2:
            return 0.0
        v = np.array([p[1] for p in self.q])
        return float(v.var())


def pipeline(t_ms, amps, normalise, hampel_k=0, hampel_n=3.0):
    """Metric per input frame (NaN until the Hampel window has filled)."""
    hf = Hampel(hampel_k, hampel_n) if hampel_k else None
    mv = MovingVar()
    out = np.full(len(t_ms), np.nan)
    for i, (t, a) in enumerate(zip(t_ms, amps)):
        f = feature(a, normalise)
        if hf:
            f = hf(f)
            if f is None:
                continue
            t = t_ms[i - hampel_k]  # the value judged is k frames old
        out[i] = mv(t, f)
    return out
