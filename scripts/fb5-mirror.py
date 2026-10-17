#!/usr/bin/env python3
# Mirror frames to the FB5 FSMC display through the Klipper API socket.
# Only changed areas are sent, run length encoded (fsmc_display/draw_rle).
#
#   fb5-mirror.py --frames '/path/mp_*.rgb565' --seconds 10
#   fb5-mirror.py --xvfb /dev/shm/Xvfb_screen0      (Xvfb -fbdir /dev/shm
#                                                    -screen 0 480x320x16)
#
# Frames may be raw little endian RGB565 (480x320) or any image file.
import argparse, base64, glob, json, mmap, os, socket, struct, sys, time
import numpy as np

W, H = 480, 320
RLE_MAX_RUN = 128
RLE_MAX_LITERAL = 26        # keeps every item within one mcu message (54 bytes)


# Repository root (scripts/..): logs and touch-cal.json live there
FB5_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOCKETS = ("~/printer_data/comms/klippy.sock", "/tmp/klippy_uds")


def find_socket():
    # Klipper API socket: printer_data layout (KIAUH, MainsailOS) or the
    # older /tmp one (FluiddPi). Looked up on every connect, so klippy may
    # start after this script
    for path in SOCKETS:
        path = os.path.expanduser(path)
        if os.path.exists(path):
            return path
    return os.path.expanduser(SOCKETS[0])


class KlippyAPI:
    def __init__(self, path=None):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path or find_socket())
        self.buf = b""
        self.next_id = 0

    def call(self, method, params):
        self.next_id += 1
        req = {"id": self.next_id, "method": method, "params": params}
        self.sock.sendall(json.dumps(req).encode() + b"\x03")
        while True:
            while b"\x03" not in self.buf:
                data = self.sock.recv(65536)
                if not data:
                    raise RuntimeError("klippy closed the API socket")
                self.buf += data
            msg, self.buf = self.buf.split(b"\x03", 1)
            resp = json.loads(msg)
            if resp.get("id") != self.next_id:
                continue
            if "error" in resp:
                raise RuntimeError("%s: %s" % (method, resp["error"]))
            return resp.get("result")


def load_frame(path):
    if path.endswith(".rgb565"):
        return np.fromfile(path, dtype="<u2").reshape(H, W)
    from PIL import Image
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint16)
    return ((rgb[..., 0] & 0xf8) << 8) | ((rgb[..., 1] & 0xfc) << 3) \
        | (rgb[..., 2] >> 3)


class XvfbScreen:
    # Memory mapped Xvfb screen (XWD file written by "Xvfb -fbdir")
    def __init__(self, path):
        self.f = open(path, "rb")
        self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        hdr = struct.unpack(">25I", self.mm[:100])
        # XWDFileHeader: header_size, file_version, pixmap_format,
        # pixmap_depth, pixmap_width, pixmap_height, xoffset, byte_order,
        # bitmap_unit, bitmap_bit_order, bitmap_pad, bits_per_pixel,
        # bytes_per_line, ..., ncolors (19), ...
        header_size, width, height = hdr[0], hdr[4], hdr[5]
        byte_order, bpp, bytes_per_line, ncolors = hdr[7], hdr[11], hdr[12], hdr[19]
        if (width, height) != (W, H) or bpp != 16 or bytes_per_line != W * 2:
            raise SystemExit("Xvfb screen must be %dx%dx16 (got %dx%d, %d bpp)"
                             % (W, H, width, height, bpp))
        self.dtype = "<u2" if byte_order == 0 else ">u2"
        self.offset = header_size + ncolors * 12
        self.path = path
        self.ino = os.fstat(self.f.fileno()).st_ino

    def replaced(self):
        # True if Xvfb was restarted (new file) or the file is gone
        try:
            return os.stat(self.path).st_ino != self.ino
        except OSError:
            return True

    def grab(self):
        return np.frombuffer(self.mm, dtype=self.dtype, count=W * H,
                             offset=self.offset).reshape(H, W).copy()


def changed_rects(prev, cur, band=16, gap=24):
    # Rectangles covering the changed pixels: per band of rows, split
    # where more than `gap` unchanged columns separate two changes
    if prev is None:
        return [(0, 0, W - 1, H - 1)]
    diff = prev != cur
    rects = []
    for y0 in range(0, H, band):
        y1 = min(y0 + band, H) - 1
        cols = np.flatnonzero(diff[y0:y1 + 1].any(axis=0))
        if not cols.size:
            continue
        rows = np.flatnonzero(diff[y0:y1 + 1].any(axis=1))
        ya, yb = y0 + int(rows[0]), y0 + int(rows[-1])
        cut = np.flatnonzero(np.diff(cols) > gap)
        starts = np.concatenate(([cols[0]], cols[cut + 1]))
        ends = np.concatenate((cols[cut], [cols[-1]]))
        for xa, xb in zip(starts.tolist(), ends.tolist()):
            rects.append((xa, ya, xb, yb))
    return rects


def rle_encode(px):
    # px: 1-D uint16 array -> RLE item stream (fsmc_lcd_rle format)
    n = len(px)
    starts = np.concatenate(([0], np.flatnonzero(px[1:] != px[:-1]) + 1))
    lengths = np.diff(np.concatenate((starts, [n])))
    out = bytearray()
    lit_start = lit_len = 0

    def flush(start, count):
        while count:
            k = min(count, RLE_MAX_LITERAL)
            out.append(k - 1)
            out.extend(px[start:start + k].astype("<u2").tobytes())
            start += k
            count -= k

    for s, l in zip(starts.tolist(), lengths.tolist()):
        if l == 1:
            if not lit_len:
                lit_start = s
            lit_len += 1
            continue
        if lit_len:
            flush(lit_start, lit_len)
            lit_len = 0
        c = int(px[s])
        while l:
            k = min(l, RLE_MAX_RUN)
            out.extend((0x80 | (k - 1), c & 0xff, c >> 8))
            l -= k
    if lit_len:
        flush(lit_start, lit_len)
    return out


class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.start = time.monotonic()
        self.count = self.enc_t = self.draw_t = self.nbytes = self.nrects = 0

    def report(self, prefix=""):
        total = time.monotonic() - self.start
        n = max(self.count, 1)
        print("%s%d updates in %.1fs: %.1f/s, avg %d bytes in %.1f rects,"
              " encode %.1fms + draw %.1fms per update"
              % (prefix, self.count, total, self.count / total,
                 self.nbytes / n, self.nrects / n,
                 1000. * self.enc_t / n, 1000. * self.draw_t / n), flush=True)


def send_update(api, prev, cur, gap, stats):
    # Send the changes from prev to cur; returns the API response, or
    # None if nothing changed
    t0 = time.monotonic()
    rects = []
    for x0, y0, x1, y1 in changed_rects(prev, cur, gap=gap):
        stream = rle_encode(cur[y0:y1 + 1, x0:x1 + 1].ravel())
        stats.nbytes += len(stream)
        rects.append([x0, y0, x1, y1, base64.b64encode(stream).decode()])
    t1 = time.monotonic()
    if not rects:
        return None
    resp = api.call("fsmc_display/draw_rle", {"rects": rects})
    stats.enc_t += t1 - t0
    stats.draw_t += time.monotonic() - t1
    stats.nrects += len(rects)
    stats.count += 1
    return resp


def run_frames(args):
    paths = sorted(glob.glob(args.frames))
    if not paths:
        sys.exit("no frames match %s" % args.frames)
    frames = [load_frame(p) for p in paths]
    api = KlippyAPI(args.socket)
    stats = Stats()
    prev = None
    i = 0
    while time.monotonic() - stats.start < args.seconds:
        t0 = time.monotonic()
        cur = frames[i % len(frames)]
        send_update(api, prev, cur, args.gap, stats)
        prev = cur
        i += 1
        if args.fps:
            time.sleep(max(0., t0 + 1. / args.fps - time.monotonic()))
    stats.report()


class PrintLimiter:
    # Byte budget for display updates while a print is running, so heavy
    # content (e.g. the camera panel) can't saturate the mcu link. Skipped
    # frames are not lost: the next diff is taken against the last frame
    # actually sent.
    def __init__(self, rate, always=False):
        self.rate = rate                # RLE bytes per second, 0 = off
        self.always = always            # limit even when not printing (tests)
        self.printing = False
        self.credit = self.last_t = 0.
        self.last_query = -1e9          # query right away

    def poll_state(self, api, now):
        if not self.rate or now - self.last_query < 2.:
            return
        self.last_query = now
        res = api.call("objects/query", {"objects": {"print_stats": ["state"]}})
        state = res["status"]["print_stats"]["state"]
        printing = state == "printing" or self.always
        if printing != self.printing:
            print("print state %s - limit %s" % (
                state, "%d B/s" % self.rate if printing else "off"), flush=True)
            self.credit = self.rate     # start with a one second burst
        self.printing = printing

    def may_send(self, now):
        if not self.printing:
            return True
        self.credit = min(self.credit + self.rate * (now - self.last_t),
                          self.rate)
        self.last_t = now
        return self.credit >= 0.

    def sent(self, nbytes):
        if self.printing:
            self.credit -= nbytes


def run_xvfb(args):
    screen = None
    stats = Stats()
    limiter = PrintLimiter(args.print_rate * 1024, args.limit_always)
    api = prev = epoch = None
    last_call = last_check = 0.
    end = time.monotonic() + args.seconds if args.seconds else None
    while end is None or time.monotonic() < end:
        t0 = time.monotonic()
        if screen is None or (t0 - last_check > 5. and screen.replaced()):
            # Wait for (a restarted) Xvfb; its file appears a bit later
            last_check = t0
            try:
                screen = XvfbScreen(args.xvfb)
            except (OSError, ValueError) as e:
                if screen is not None:
                    print("Xvfb screen lost: %s" % (e,), flush=True)
                screen = None
                time.sleep(1.)
                continue
            print("Xvfb screen opened", flush=True)
            prev = None
        elif t0 - last_check > 5.:
            last_check = t0
        try:
            if api is None:
                api = KlippyAPI(args.socket)
                prev = None             # redraw everything after (re)connect
                epoch = None            # a new klippy process restarts it
            limiter.poll_state(api, t0)
            if limiter.may_send(t0):
                cur = screen.grab()
                nbytes = stats.nbytes
                resp = send_update(api, prev, cur, args.gap, stats)
                limiter.sent(stats.nbytes - nbytes)
            else:
                cur, resp = prev, None  # over budget: keep accumulating
            if resp is None and t0 - last_call > 1.:
                # Nothing changed: still poll the panel init epoch
                resp = api.call("fsmc_display/draw_rle", {"rects": []})
            if resp is not None:
                last_call = t0
                if epoch is not None and resp.get("epoch") != epoch:
                    print("panel was re-initialized - full redraw",
                          flush=True)
                    cur = None          # forces a full frame next time
                epoch = resp.get("epoch")
            prev = cur
        except (OSError, RuntimeError) as e:
            print("klippy API error: %s - retrying" % (e,), flush=True)
            api = None
            time.sleep(2.)
            continue
        if time.monotonic() - stats.start >= args.report:
            stats.report("mirror: ")
            stats.reset()
        time.sleep(max(0., t0 + 1. / args.fps - time.monotonic()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--frames", help="glob of frame files (benchmark)")
    src.add_argument("--xvfb", help="Xvfb -fbdir screen file to mirror")
    ap.add_argument("--socket", help="Klipper API socket (default: found)")
    ap.add_argument("--seconds", type=float, default=None,
                    help="run time (frames default 10, xvfb forever)")
    ap.add_argument("--fps", type=float, default=None,
                    help="update rate limit (frames default unlimited, xvfb 20)")
    ap.add_argument("--report", type=float, default=10.,
                    help="xvfb stats interval in seconds")
    ap.add_argument("--gap", type=int, default=24)
    # 64: highest step with mcu_awake < 0.7 in rate-steps.sh (2026-10-16:
    # accel 5000, 150 mm/s, camera at 50% area; 96 KiB/s reached 0.92)
    ap.add_argument("--print-rate", type=float, default=64.,
                    help="xvfb: max KiB/s of RLE data while printing (0 = off)")
    ap.add_argument("--limit-always", action="store_true",
                    help="xvfb: apply --print-rate even when not printing")
    args = ap.parse_args()
    if args.frames:
        args.seconds = 10. if args.seconds is None else args.seconds
        args.fps = args.fps or 0.
        run_frames(args)
    else:
        args.fps = args.fps or 20.
        run_xvfb(args)


if __name__ == "__main__":
    main()
