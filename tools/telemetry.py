"""Decode Nobody Home UDP packets. Layout matches firmware/src/telemetry.cpp."""
import socket
import struct

PORT = 20003
MAGIC = 0x4E  # 'N'

HEADER = struct.Struct("<BBH")
TELEMETRY = struct.Struct("<IIHfffBBIhb")  # 31 bytes after the header
EVENT = struct.Struct("<IIBh")             # 11 bytes after the header
RAW = struct.Struct("<IIIfffbB")           # then nsub amplitude bytes

STATES = {0: "STALE", 1: "ACTIVE", 2: "QUIET_PENDING", 3: "EMPTY", 4: "TURNING", 5: "SETTLING"}
EVENTS = {1: "boot", 2: "calibrated", 3: "turn_start", 4: "turn_done", 5: "reset",
          6: "stale", 7: "rearmed", 8: "lifted", 9: "put_down", 10: "frozen"}


HELLO = bytes([MAGIC, 0x10, 0, 0])
HELLO_EVERY_S = 2  # the Atom drops a subscriber after 10 s of silence


def _hello_targets():
    """Global broadcast, plus the /24 broadcast of each LAN address of this PC."""
    targets = {"255.255.255.255"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("127.", "169.254.", "100.")):  # loopback, link-local, Tailscale
                continue
            targets.add(".".join(ip.split(".")[:3] + ["255"]))
    except OSError:
        pass
    return targets


def say_hello(sock, port=PORT):
    """Ask any Atom on the LAN to stream to this PC as well."""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for t in _hello_targets():
        try:
            sock.sendto(HELLO, (t, port))
        except OSError:
            pass


def decode(data):
    """Bytes -> dict, or None if it is not one of ours."""
    if len(data) < HEADER.size:
        return None
    magic, kind, session = HEADER.unpack_from(data)
    if magic != MAGIC:
        return None
    body = data[HEADER.size:]
    if kind == 0x01 and len(body) == TELEMETRY.size:
        seq, uptime, rate, metric, low, high, state, armed, quiet, angle, rssi = TELEMETRY.unpack(body)
        return dict(kind="T", session=session, seq=seq, uptime_ms=uptime, rate=rate, metric=metric,
                    low=low, high=high, state=STATES.get(state, str(state)), armed=armed,
                    quiet_ms=quiet, angle=angle, rssi=rssi)
    if kind == 0x03 and len(body) >= RAW.size:
        seq, uptime, frames, feature, filtered, metric, rssi, nsub = RAW.unpack_from(body)
        amps = body[RAW.size:RAW.size + nsub]
        if len(amps) != nsub:
            return None
        return dict(kind="R", session=session, seq=seq, uptime_ms=uptime, frames=frames,
                    feature=feature, filtered=filtered, metric=metric, rssi=rssi, amps=list(amps))
    if kind == 0x02 and len(body) == EVENT.size:
        seq, uptime, code, angle = EVENT.unpack(body)
        return dict(kind="E", session=session, seq=seq, uptime_ms=uptime,
                    event=EVENTS.get(code, str(code)), angle=angle)
    return None
